import csv, io, json
from pathlib import Path

def extract_text(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md"}: return data.decode("utf-8", errors="replace")
    if suffix == ".json": return json.dumps(json.loads(data.decode("utf-8")), ensure_ascii=False, indent=2)
    if suffix == ".csv": return "\n".join(" | ".join(row) for row in csv.reader(io.StringIO(data.decode("utf-8", errors="replace"))))
    if suffix == ".pdf":
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    if suffix == ".docx":
        from docx import Document
        return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    raise ValueError("Formato não suportado. Use TXT, MD, JSON, CSV, PDF ou DOCX.")
