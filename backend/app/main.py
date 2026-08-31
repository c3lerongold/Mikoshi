import hashlib, re, uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session
from .db import Base, engine, get_db
from .models import Persona, Source, Memory, Feedback, Consent, ConversationSession, ConversationMessage, Chunk, Document, Fact, Preference, Opinion, PersonalityTrait, Relationship
from .schemas import PersonaCreate, ManualSource, MemoryCreate, MemoryPatch, RelationshipCreate, ChatRequest, FeedbackRequest, InterviewRequest
from .services import ingest_text, embeddings, search_memories, contradictions, generate_reply, profile, extract_declared_evidence, extract_llm_evidence
from ingestion.parsers import extract_text

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(title="Mikoshi", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def persona_or_404(db: Session, persona_id: str) -> Persona:
    p = db.get(Persona, uuid.UUID(persona_id))
    if not p: raise HTTPException(404, "Persona não encontrada")
    return p
def source_or_404(db: Session, source_id: str) -> Source:
    s = db.get(Source, uuid.UUID(source_id))
    if not s: raise HTTPException(404, "Fonte não encontrada")
    return s
def dump_persona(p: Persona): return {"id": str(p.id), "name": p.name, "description": p.description, "language": p.language, "created_at": p.created_at}

@app.get("/health")
def health(): return {"status": "ok"}

@app.post("/personas", status_code=201)
def create_persona(data: PersonaCreate, db: Session = Depends(get_db)):
    persona = Persona(**data.model_dump()); db.add(persona); db.commit(); db.refresh(persona); return dump_persona(persona)
@app.get("/personas")
def list_personas(db: Session = Depends(get_db)): return [dump_persona(p) for p in db.scalars(select(Persona).order_by(Persona.created_at.desc())).all()]
@app.get("/personas/{persona_id}")
def get_persona(persona_id: str, db: Session = Depends(get_db)):
    p = persona_or_404(db, persona_id)
    return {**dump_persona(p), "memories": db.scalar(select(func.count()).select_from(Memory).where(Memory.persona_id == p.id)), "sources": db.scalar(select(func.count()).select_from(Source).where(Source.persona_id == p.id))}
@app.delete("/personas/{persona_id}", status_code=204)
def delete_persona(persona_id: str, db: Session = Depends(get_db)):
    p = persona_or_404(db, persona_id); db.delete(p); db.commit()

def create_source(db: Session, persona_id: str, content: str, filename: str | None, origin: str, consent_status: str, source_type: str, owner_label: str | None = None):
    if consent_status != "granted": raise HTTPException(400, "Consentimento explícito (granted) é obrigatório")
    persona_or_404(db, persona_id)
    source = Source(persona_id=uuid.UUID(persona_id), source_type=source_type, filename=filename, origin=origin, consent_status=consent_status, content_hash=hashlib.sha256(content.encode()).hexdigest(), metadata_json={"owner_label": owner_label} if owner_label else {})
    db.add(source); db.flush(); db.add(Consent(persona_id=source.persona_id, source_id=source.id, granted=True)); db.flush()
    stats = ingest_text(db, source.persona_id, content, source)
    return {"id": str(source.id), "filename": source.filename, "stats": stats}
@app.post("/personas/{persona_id}/sources", status_code=201)
def add_manual_source(persona_id: str, data: ManualSource, db: Session = Depends(get_db)):
    return create_source(db, persona_id, data.content, data.filename, data.origin, data.consent_status, data.source_type, data.owner_label)
@app.post("/personas/{persona_id}/sources/upload", status_code=201)
async def upload_source(persona_id: str, file: UploadFile = File(...), origin: str = Form("user_export"), consent_status: str = Form("granted"), owner_label: str | None = Form(None), db: Session = Depends(get_db)):
    raw = await file.read()
    if len(raw) > 25 * 1024 * 1024: raise HTTPException(413, "Arquivo excede 25 MB")
    try: content = extract_text(file.filename or "upload.txt", raw)
    except ValueError as e: raise HTTPException(400, str(e))
    return create_source(db, persona_id, content, file.filename, origin, consent_status, "file", owner_label)
@app.get("/personas/{persona_id}/sources")
def list_sources(persona_id: str, db: Session = Depends(get_db)):
    persona_or_404(db, persona_id)
    return [{"id":str(s.id),"source_type":s.source_type,"filename":s.filename,"origin":s.origin,"consent_status":s.consent_status,"created_at":s.created_at,"metadata":s.metadata_json} for s in db.scalars(select(Source).where(Source.persona_id==uuid.UUID(persona_id))).all()]
@app.delete("/sources/{source_id}", status_code=204)
def delete_source(source_id: str, db: Session = Depends(get_db)):
    # Explicitly remove every derived entity; this remains correct even without DB-level cascading across derived tables.
    s = source_or_404(db, source_id)
    sid = s.id
    for model in (Chunk, Document, Memory, Fact, Preference, Opinion, PersonalityTrait, Relationship, Consent): db.execute(delete(model).where(model.source_id == sid))
    db.delete(s); db.commit()

@app.get("/personas/{persona_id}/memories")
def list_memories(persona_id: str, q: str | None = None, memory_type: str | None = None, db: Session = Depends(get_db)):
    persona_or_404(db, persona_id)
    items = search_memories(db, persona_id, q) if q else db.scalars(select(Memory).where(Memory.persona_id==uuid.UUID(persona_id))).all()
    if memory_type: items = [m for m in items if m.memory_type == memory_type]
    return [{"id":str(m.id),"content":m.content,"type":m.memory_type,"importance":m.importance,"confidence":m.confidence,"source_id":str(m.source_id) if m.source_id else None,"active":m.active,"tags":m.tags,"created_at":m.created_at} for m in items]
@app.post("/personas/{persona_id}/memories", status_code=201)
def add_memory(persona_id: str, data: MemoryCreate, db: Session = Depends(get_db)):
    p=persona_or_404(db, persona_id); conflicts = contradictions(db, persona_id, data.content)
    source=Source(persona_id=p.id, source_type="manual_memory", filename="memória adicionada manualmente", origin="persona_owner", consent_status="granted", content_hash=hashlib.sha256(data.content.encode()).hexdigest(), metadata_json={"memory_type":data.memory_type})
    db.add(source); db.flush(); db.add(Consent(persona_id=p.id, source_id=source.id, granted=True))
    m = Memory(persona_id=p.id, source_id=source.id, **data.model_dump(), embedding=embeddings.embed(data.content)); db.add(m); db.commit(); db.refresh(m)
    return {"id":str(m.id), "contradictions": [{"id":str(c.id),"content":c.content} for c in conflicts]}
@app.post("/personas/{persona_id}/relationships", status_code=201)
def add_relationship(persona_id: str, data: RelationshipCreate, db: Session = Depends(get_db)):
    p=persona_or_404(db, persona_id)
    content=f"{data.name}: {data.description or data.relationship_type}"
    source=Source(persona_id=p.id, source_type="manual_relationship", filename="pessoa importante", origin="persona_owner", consent_status="granted", content_hash=hashlib.sha256(content.encode()).hexdigest(), metadata_json={"name":data.name})
    db.add(source); db.flush(); db.add(Consent(persona_id=p.id, source_id=source.id, granted=True))
    relation=Relationship(persona_id=p.id, source_id=source.id, key=data.relationship_type, value=content, classification="FACT", confidence=.9, evidence=["Adicionado manualmente pelo dono da persona"]); db.add(relation)
    memory=Memory(persona_id=p.id, source_id=source.id, content=content, memory_type="relationship", importance=data.importance, confidence=.9, tags=["important_person", data.relationship_type], embedding=embeddings.embed(content)); db.add(memory); db.commit()
    return {"relationship_id":str(relation.id), "memory_id":str(memory.id), "source_id":str(source.id)}
@app.patch("/memories/{memory_id}")
def patch_memory(memory_id: str, data: MemoryPatch, db: Session = Depends(get_db)):
    m = db.get(Memory, uuid.UUID(memory_id))
    if not m: raise HTTPException(404, "Memória não encontrada")
    for k,v in data.model_dump(exclude_none=True).items(): setattr(m,k,v)
    if data.content: m.embedding = embeddings.embed(data.content)
    db.commit(); return {"id":str(m.id)}
@app.delete("/memories/{memory_id}", status_code=204)
def delete_memory(memory_id: str, db: Session = Depends(get_db)):
    m=db.get(Memory, uuid.UUID(memory_id));
    if not m: raise HTTPException(404, "Memória não encontrada")
    db.delete(m); db.commit()

@app.get("/personas/{persona_id}/profile")
def get_profile(persona_id: str, db: Session = Depends(get_db)): persona_or_404(db, persona_id); return profile(db, uuid.UUID(persona_id))
@app.post("/personas/{persona_id}/rebuild-profile")
def rebuild_profile(persona_id: str, db: Session = Depends(get_db)):
    persona_or_404(db, persona_id)
    pid = uuid.UUID(persona_id)
    for model in (PersonalityTrait, Fact, Preference, Opinion): db.execute(delete(model).where(model.persona_id == pid))
    for source, doc in db.execute(select(Source, Document).join(Document, Document.source_id==Source.id).where(Source.persona_id==pid)).all():
        extract_declared_evidence(db, pid, source.id, doc.content); extract_llm_evidence(db, pid, source.id, doc.content)
    db.commit(); return profile(db, uuid.UUID(persona_id))

@app.post("/personas/{persona_id}/chat")
async def chat(persona_id: str, request: ChatRequest, db: Session = Depends(get_db)):
    p=persona_or_404(db, persona_id)
    smalltalk = bool(re.fullmatch(r"\s*(?:oi+|ol[aá]+|opa+|e[ai]+|bom dia|boa tarde|boa noite)(?:[ ,.!?]+(?:como vai|tudo bem|suave|blz|beleza))?[!.?\s]*|\s*(?:tudo bem|como vai)[?.!\s]*", request.message.casefold()))
    memories=[] if smalltalk else search_memories(db, persona_id, request.message)
    profile_data=profile(db, p.id); traits=profile_data["traits"]
    facts = "\n".join(f"- {m.content}" for m in memories if m.confidence >= .45 and m.memory_type != "writing_example")
    # Examples teach form, not subject matter. Sending only the target reply
    # prevents the model from mistaking a third party's message for an answer.
    style_memories=db.scalars(select(Memory).where(Memory.persona_id==p.id, Memory.active==True, Memory.memory_type=="writing_example").order_by(Memory.created_at.desc()).limit(12)).all()
    writing_reply_marker = "Resposta da persona:\n"
    writing_examples = "\n".join(
        "- " + memory.content.split(writing_reply_marker)[-1]
        for memory in style_memories
    )
    question_words=set(re.findall(r"[\wÀ-ÿ]+", request.message.casefold()))
    explicit=[]
    for category in ("preferences", "opinions", "facts"):
        for item in profile_data[category]:
            text=f"{item['key']} {item['value']}".casefold()
            if smalltalk or question_words.intersection(re.findall(r"[\wÀ-ÿ]+", text)):
                explicit.append(f"- {item['value']} ({item['classification']}, confiança {item['confidence']})")
    known_profile="\n".join(explicit[:12])
    style = "\n".join(f"- {t['key']}: {t['value']} ({t['classification']})" for t in traits)
    mode = "É apenas um cumprimento/conversa casual. Responda de modo social e natural; não procure nem invente uma opinião." if smalltalk else "Responda diretamente à mensagem. Use fatos e opiniões somente se forem relevantes à pergunta."
    prompt=f"""Você é a persona textual de {p.name}. {mode}

OBJETIVO: gerar uma resposta coerente para a mensagem atual, moldada pelo jeito de escrever da persona. As AMOSTRAS servem SOMENTE para estilo, nunca como assunto, resposta pronta ou fato.

CONTRATO DE IMITAÇÃO: observe e replique o padrão predominante das AMOSTRAS: grafia informal ou formal, maiúsculas/minúsculas, pontuação (inclusive ausência dela), abreviações, gírias, expressões recorrentes, risadas, emojis, intensidade, tamanho e cadência. Não "corrija" a escrita da persona para português padrão. Não copie frases inteiras nem force uma gíria que não combine com a mensagem atual.

REGRAS: não mencione documentos, memórias, contexto, análise ou "informações fornecidas". Não copie amostras. Não invente experiências, gostos ou opiniões. Se uma pergunta pedir opinião e não houver uma opinião/fato relevante, diga de forma natural que não tem informação suficiente. Retorne somente a mensagem final, sem rótulos.

OPINIÕES, PREFERÊNCIAS E FATOS RELEVANTES:
{known_profile or '(nenhum relevante)'}

MEMÓRIAS RELEVANTES:
{facts or '(nenhuma relevante)'}

AMOSTRAS DE ESTILO DA PERSONA:
{writing_examples or '(nenhuma)'}

TRAÇOS INFERIDOS:
{style or '(nenhum)'}

MENSAGEM ATUAL: {request.message}
RESPOSTA:"""
    response=await generate_reply(prompt)
    if not response: response="opa, tudo certo?" if smalltalk else "Não tenho informação suficiente para saber o que eu pensaria sobre isso."
    session_id=uuid.UUID(request.session_id) if request.session_id else None
    if not session_id: session=ConversationSession(persona_id=p.id); db.add(session); db.flush(); session_id=session.id
    db.add(ConversationMessage(session_id=session_id, role="user", content=request.message)); answer=ConversationMessage(session_id=session_id, role="assistant", content=response, metadata_json={"memory_ids":[str(m.id) for m in memories]}); db.add(answer); db.commit(); db.refresh(answer)
    result={"answer":response,"session_id":str(session_id),"message_id":str(answer.id)}
    if request.debug: result["debug"]={"memories":[{"content":m.content,"source_id":str(m.source_id) if m.source_id else None,"confidence":m.confidence} for m in memories],"traits":traits}
    return result
@app.get("/personas/{persona_id}/chat/sessions/{session_id}")
def chat_history(persona_id: str, session_id: str, db: Session = Depends(get_db)):
    p=persona_or_404(db, persona_id); session=db.get(ConversationSession, uuid.UUID(session_id))
    if not session or session.persona_id != p.id: raise HTTPException(404, "Conversa não encontrada")
    messages=db.scalars(select(ConversationMessage).where(ConversationMessage.session_id==session.id).order_by(ConversationMessage.created_at.asc())).all()
    return {"session_id":str(session.id),"messages":[{"id":str(m.id),"role":m.role,"content":m.content,"created_at":m.created_at,"metadata":m.metadata_json} for m in messages]}

@app.post("/personas/{persona_id}/feedback", status_code=201)
def feedback(persona_id: str, request: FeedbackRequest, db: Session = Depends(get_db)):
    p=persona_or_404(db, persona_id); msg_id=uuid.UUID(request.message_id) if request.message_id else None; db.add(Feedback(persona_id=p.id,message_id=msg_id,kind=request.kind,content=request.content))
    source=Source(persona_id=p.id,source_type="manual_correction",filename="correção manual",origin="feedback",consent_status="granted",content_hash=hashlib.sha256(request.content.encode()).hexdigest()); db.add(source); db.flush(); db.add(Consent(persona_id=p.id,source_id=source.id,granted=True)); db.flush(); ingest_text(db,p.id,request.content,source)
    m=Memory(persona_id=p.id,source_id=source.id,content=request.content,memory_type="opinion" if request.kind=="correction" else "semantic",importance=.8,confidence=.9,tags=["manual_correction"],embedding=embeddings.embed(request.content)); db.add(m); db.commit(); return {"status":"recorded","memory_id":str(m.id),"source_id":str(source.id)}
@app.post("/personas/{persona_id}/interview")
def interview(persona_id: str, request: InterviewRequest, db: Session = Depends(get_db)):
    p=persona_or_404(db, persona_id)
    questions={"infância":"Qual é uma lembrança da infância que você gostaria de preservar?","trabalho":"Qual é uma experiência de trabalho que moldou sua forma de pensar?","hobbies":"Quais atividades você procura quando tem tempo livre?","valores":"Que princípio você tenta seguir nas decisões difíceis?","crenças_centrais":"Quando algo dá errado, qual explicação você costuma dar para si mesmo? Há uma regra pessoal que orienta sua reação?","decisões":"Conte uma decisão difícil. Quais alternativas você considerou e o que pesou mais?","relacionamentos":"O que faz você se sentir respeitado ou seguro em uma relação?"}
    if request.answer:
        source=Source(persona_id=p.id,source_type="interview",filename=f"entrevista_{request.category}",origin="guided_interview",consent_status="granted",content_hash=hashlib.sha256(request.answer.encode()).hexdigest(),metadata_json={"category":request.category}); db.add(source); db.flush(); db.add(Consent(persona_id=p.id,source_id=source.id,granted=True)); db.flush(); ingest_text(db,p.id,request.answer,source)
        return {"source_id":str(source.id),"next_question":questions.get(request.category, questions["valores"]),"safety":"Esta entrevista é reflexiva e não realiza diagnóstico psicológico ou médico."}
    return {"question":questions.get(request.category, questions["crenças_centrais"]),"safety":"Esta entrevista é reflexiva e não realiza diagnóstico psicológico ou médico."}
