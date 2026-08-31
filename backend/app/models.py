import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, Float, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base

def now(): return datetime.utcnow()
def uid(): return uuid.uuid4()

class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Persona(Base):
    __tablename__ = "personas"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(12), default="pt-BR")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Source(Base):
    __tablename__ = "sources"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    persona_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("personas.id", ondelete="CASCADE"), index=True)
    source_type: Mapped[str] = mapped_column(String(50))
    filename: Mapped[str | None] = mapped_column(String(500))
    origin: Mapped[str] = mapped_column(String(200))
    consent_status: Mapped[str] = mapped_column(String(30), default="granted")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    persona_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("personas.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int]
    embedding: Mapped[list] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class Memory(Base):
    __tablename__ = "memories"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    persona_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("personas.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    content: Mapped[str] = mapped_column(Text)
    memory_type: Mapped[str] = mapped_column(String(50), default="semantic")
    importance: Mapped[float] = mapped_column(Float, default=.5)
    confidence: Mapped[float] = mapped_column(Float, default=.5)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    embedding: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

class EvidenceEntity(Base):
    __abstract__ = True
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    persona_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("personas.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(100))
    value: Mapped[str] = mapped_column(Text)
    classification: Mapped[str] = mapped_column(String(12), default="FACT")
    confidence: Mapped[float] = mapped_column(Float, default=.5)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
class Fact(EvidenceEntity): __tablename__ = "facts"
class Preference(EvidenceEntity): __tablename__ = "preferences"
class Opinion(EvidenceEntity): __tablename__ = "opinions"
class PersonalityTrait(EvidenceEntity): __tablename__ = "personality_traits"
class Relationship(EvidenceEntity): __tablename__ = "relationships"

class ConversationSession(Base):
    __tablename__ = "conversation_sessions"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    persona_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("personas.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversation_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    persona_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("personas.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversation_messages.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uid)
    persona_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("personas.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(100), default="persona_training")
    granted: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
