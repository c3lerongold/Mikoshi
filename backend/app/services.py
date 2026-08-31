import hashlib, json, math, re
from collections import Counter
from datetime import datetime
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import settings
from .models import Chunk, Memory, PersonalityTrait, Source, Document, Fact, Preference, Opinion

class EmbeddingService:
    """Deterministic local fallback. Replace while retaining embed(text)->list[float]."""
    def embed(self, text: str) -> list[float]:
        values = [0.0] * settings.embedding_dimensions
        for word in re.findall(r"\w+", text.lower(), re.UNICODE):
            digest = hashlib.sha256(word.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % len(values)
            values[index] += 1 if digest[4] % 2 else -1
        norm = math.sqrt(sum(x*x for x in values)) or 1
        return [x / norm for x in values]
    @staticmethod
    def similarity(a: list[float], b: list[float]) -> float:
        return sum(x*y for x, y in zip(a, b))
embeddings = EmbeddingService()

def clean_text(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()

WHATSAPP_LINE = re.compile(r"^(?:\[(?P<bracket>[^\]]+)\]\s*|(?P<date>\d{1,4}[/.\-]\d{1,2}[/.\-]\d{1,4},?\s+\d{1,2}:\d{2}(?::\d{2})?)\s*[-–]\s*)(?P<speaker>[^:]{1,120}):\s?(?P<content>.*)$")

def speaker_key(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return digits if len(digits) >= 7 else re.sub(r"\s+", " ", value).strip().casefold()

def parse_conversation(text: str) -> list[dict]:
    """Parses common WhatsApp export lines without contacting any platform."""
    messages: list[dict] = []
    for raw_line in text.splitlines():
        match = WHATSAPP_LINE.match(raw_line.strip())
        if match:
            # Some exports use `Nome:: mensagem`; the first colon separates the
            # speaker and the second is formatting, not part of the message.
            messages.append({"speaker": match.group("speaker").strip(), "content": match.group("content").lstrip(": ").strip(), "timestamp": match.group("bracket") or match.group("date")})
        elif messages and raw_line.strip():
            messages[-1]["content"] += "\n" + raw_line.strip()
    return [message for message in messages if message["content"] and "<Media omitted>" not in message["content"]]

def persona_messages_from_conversation(text: str, owner_label: str | None) -> tuple[list[dict], dict]:
    messages = parse_conversation(text)
    if not messages or not owner_label:
        return [], {"recognized": False, "reason": "owner_label_required" if messages else "format_not_recognized"}
    owner = speaker_key(owner_label)
    own: list[dict] = []
    for index, message in enumerate(messages):
        if speaker_key(message["speaker"]) != owner: continue
        previous = [entry for entry in messages[max(0, index - 3):index] if speaker_key(entry["speaker"]) != owner]
        context = "\n".join(f"{entry['speaker']}: {entry['content']}" for entry in previous)
        own.append({**message, "context": context})
    return own, {"recognized": True, "total_messages": len(messages), "persona_messages": len(own), "owner_label": owner_label}

def chunk_text(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    text = clean_text(text)
    if not text: return []
    chunks, pos = [], 0
    while pos < len(text):
        end = min(len(text), pos + size)
        if end < len(text):
            boundary = max(text.rfind(". ", pos, end), text.rfind("\n", pos, end))
            if boundary > pos + size // 2: end = boundary + 1
        chunks.append(text[pos:end].strip())
        if end >= len(text):
            break
        pos = max(end - overlap, pos + 1)
    return chunks

def ingest_text(db: Session, persona_id, text: str, source: Source) -> dict:
    cleaned = clean_text(text)
    document = Document(source_id=source.id, content=cleaned)
    db.add(document)
    own_messages, conversation_metadata = persona_messages_from_conversation(cleaned, (source.metadata_json or {}).get("owner_label"))
    # Only the nominated owner's turns are training material. Other speakers are
    # retained in the raw document, never treated as persona statements.
    persona_corpus = "\n".join(message["content"] for message in own_messages) if own_messages else cleaned
    parts = chunk_text(persona_corpus)
    training_parts = parts if own_messages or not conversation_metadata["recognized"] else []
    for i, content in enumerate(training_parts):
        db.add(Chunk(persona_id=persona_id, source_id=source.id, content=content, chunk_index=i, embedding=embeddings.embed(content), metadata_json={"speaker_scope": "persona" if own_messages else "unverified"}))
    # For a recognized conversation, only the owner messages may become memories.
    # Otherwise the imported text remains unverified and is not treated as persona knowledge.
    for content in training_parts[:50]:
        db.add(Memory(persona_id=persona_id, source_id=source.id, content=content, memory_type="semantic", importance=.4, confidence=.6, tags=["imported", "unverified_speaker"], embedding=embeddings.embed(content)))
    if own_messages:
        for message in own_messages[:200]:
            example = (f"Contexto recebido:\n{message['context']}\n\nResposta da persona:\n{message['content']}" if message["context"] else message["content"])
            db.add(Memory(persona_id=persona_id, source_id=source.id, content=example, memory_type="writing_example", importance=.35, confidence=.8, tags=["conversation", "persona_message"], embedding=embeddings.embed(example)))
    extracted = extract_declared_evidence(db, persona_id, source.id, persona_corpus) if own_messages or not conversation_metadata["recognized"] else {"preferences": 0, "opinions": 0, "facts": 0, "traits": 0}
    if own_messages or not conversation_metadata["recognized"]:
        examples_for_analysis = "\n\n".join(
            f"INTERLOCUTOR/CONTEXTO:\n{message['context']}\nPESSOA-ALVO:\n{message['content']}"
            for message in own_messages[:80]
        )
        extracted.update(extract_llm_evidence(db, persona_id, source.id, persona_corpus, examples_for_analysis))
    source.metadata_json = {**(source.metadata_json or {}), "processing_status": "complete", "processing_version": 3, "conversation_analysis": conversation_metadata, "derived_evidence": extracted}
    db.commit()
    return {"chunks": len(training_parts), "memories": len(own_messages) if own_messages else min(len(training_parts), 50), "conversation": conversation_metadata, "evidence": extracted}

def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.strip()) >= 5]

def add_evidence(db: Session, model, persona_id, source_id, key: str, value: str, classification: str, evidence: str, confidence: float) -> None:
    """Stores only explicit statements or explicitly labelled inferences with their verbatim evidence."""
    db.add(model(persona_id=persona_id, source_id=source_id, key=key, value=value[:1000], classification=classification, confidence=confidence, evidence=[evidence[:1000]]))

def extract_declared_evidence(db: Session, persona_id, source_id, text: str) -> dict:
    counts = {"preferences": 0, "opinions": 0, "facts": 0, "traits": 0}
    for sentence in sentences(text):
        normalized = sentence.lower()
        if re.search(r"\b(eu )?(gosto|adoro|prefiro|detesto|odeio|não gosto|nao gosto)\b", normalized):
            add_evidence(db, Preference, persona_id, source_id, "declared_preference", sentence, "FACT", sentence, .86); counts["preferences"] += 1
        elif re.search(r"\b(eu )?(acho|acredito|penso|considero|discordo|concordo)\b", normalized):
            add_evidence(db, Opinion, persona_id, source_id, "declared_opinion", sentence, "FACT", sentence, .78); counts["opinions"] += 1
        elif re.search(r"\beu (sou|tenho|trabalho|trabalhei|moro|morei|nasci|estudei|fiz)\b", normalized):
            add_evidence(db, Fact, persona_id, source_id, "declared_personal_fact", sentence, "FACT", sentence, .75); counts["facts"] += 1
    analyze_style(db, persona_id, source_id, text); counts["traits"] = 2
    return counts

def extract_llm_evidence(db: Session, persona_id, source_id, text: str, conversation_context: str = "") -> dict:
    """Optional local analysis pass; only target utterances can support an extraction."""
    result = {"llm_items": 0, "llm_available": False}
    if not settings.analysis_with_llm or len(text) < 20: return result
    prompt = (
        "Você analisa uma conversa para construir uma persona textual. A PESSOA-ALVO já foi identificada pelo sistema. "
        "Use somente as MENSAGENS DA PESSOA-ALVO para extrair padrões; as mensagens do interlocutor são contexto "
        "de tema e continuidade e nunca são evidência sobre a persona. Analise vocabulário, gírias e expressões recorrentes, "
        "abreviações, grafia, letras maiúsculas/minúsculas, pontuação ou ausência dela, risadas, emojis, estrutura, tamanho, tom, "
        "humor, reticências e interjeições. Gere traits separados e específicos para essas marcas quando houver evidência. "
        "Padrões de estilo devem ser trait com classification INFERENCE. Fatos, "
        "preferências e opiniões só podem ser FACT quando a pessoa-alvo os declarou literalmente. Nunca diagnostique "
        "saúde mental, crenças clínicas ou esquemas cognitivos. Retorne JSON puro: "
        '{"items":[{"category":"fact|preference|opinion|trait","key":"curto","value":"resumo",'
        '"classification":"FACT|INFERENCE","evidence":"citação exata de uma mensagem da pessoa-alvo",'
        '"confidence":0.0}]}. Sem evidência, use items vazio.\n\nMENSAGENS DA PESSOA-ALVO:\n' + text[:12000]
        + "\n\nCONTEXTO DE CONVERSA (não extrair traços/fatos daqui):\n" + conversation_context[:6000]
    )
    try:
        with httpx.Client(timeout=8) as client:
            raw = client.post(f"{settings.ollama_base_url}/api/generate", json={"model": settings.ollama_model, "prompt": prompt, "stream": False, "format": "json", "options": {"temperature": 0}}).json().get("response", "{}")
        payload = json.loads(raw); result["llm_available"] = True
    except (httpx.HTTPError, ValueError, json.JSONDecodeError):
        return result
    models = {"fact": Fact, "preference": Preference, "opinion": Opinion, "trait": PersonalityTrait}
    for item in payload.get("items", [])[:30]:
        category, evidence = item.get("category"), str(item.get("evidence", "")).strip()
        classification = item.get("classification", "INFERENCE")
        if category not in models or classification not in {"FACT", "INFERENCE"} or not evidence or evidence.lower() not in text.lower(): continue
        confidence = min(.9, max(.1, float(item.get("confidence", .5))))
        add_evidence(db, models[category], persona_id, source_id, str(item.get("key", category)), str(item.get("value", evidence)), classification, evidence, confidence)
        result["llm_items"] += 1
    return result

def analyze_style(db: Session, persona_id, source_id, text: str) -> None:
    # Conversation exports commonly contain one short message per line, often
    # without punctuation. Treat each line as a response unit for style stats.
    sentences = [s.strip() for s in re.split(r"[.!?]+|\n+", text) if s.strip()]
    if not sentences: return
    avg = sum(len(s.split()) for s in sentences) / len(sentences)
    emoji_count = len(re.findall(r"[😀-🙏🌀-🫿]", text))
    traits = [("average_response_length", f"{avg:.1f} palavras por frase", "INFERENCE"), ("emoji_usage", "frequente" if emoji_count > 2 else "pouco observado", "INFERENCE")]
    for key, value, classification in traits:
        db.add(PersonalityTrait(persona_id=persona_id, source_id=source_id, key=key, value=value, classification=classification, confidence=.45, evidence=[text[:280]]))

def search_memories(db: Session, persona_id, query: str, limit: int = 6) -> list[Memory]:
    q = embeddings.embed(query)
    rows = db.scalars(select(Memory).where(Memory.persona_id == persona_id, Memory.active == True)).all()
    return sorted(rows, key=lambda m: embeddings.similarity(q, m.embedding), reverse=True)[:limit]

def contradictions(db: Session, persona_id, content: str) -> list[Memory]:
    words = set(re.findall(r"\w+", content.lower()))
    candidates = db.scalars(select(Memory).where(Memory.persona_id == persona_id, Memory.active == True)).all()
    flagged=[]
    for m in candidates:
        old = set(re.findall(r"\w+", m.content.lower()))
        negation_flip = ("não" in words) != ("não" in old)
        if negation_flip and len((words & old) - {"não"}) >= 3: flagged.append(m)
    return flagged

async def generate_reply(prompt: str) -> str | None:
    try:
        # A local Ollama instance may be absent or starting. Fail promptly so the
        # consent-safe fallback answer keeps the UI responsive.
        async with httpx.AsyncClient(timeout=settings.ollama_timeout_seconds) as client:
            response = await client.post(f"{settings.ollama_base_url}/api/generate", json={"model": settings.ollama_model, "prompt": prompt, "stream": False, "think": False, "keep_alive": "15m", "options": {"temperature": 0.42, "top_p": 0.9, "num_predict": 180}})
            response.raise_for_status()
            return response.json().get("response", "").strip() or None
    except (httpx.HTTPError, ValueError):
        return None

def profile(db: Session, persona_id) -> dict:
    traits = db.scalars(select(PersonalityTrait).where(PersonalityTrait.persona_id == persona_id)).all()
    def rows(model):
        return [{"key": t.key, "value": t.value, "classification": t.classification, "confidence": t.confidence, "evidence": t.evidence, "source_id": str(t.source_id) if t.source_id else None, "updated_at": t.updated_at} for t in db.scalars(select(model).where(model.persona_id == persona_id)).all()]
    return {"traits": rows(PersonalityTrait), "facts": rows(Fact), "preferences": rows(Preference), "opinions": rows(Opinion)}
