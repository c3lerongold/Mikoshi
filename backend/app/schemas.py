from datetime import datetime
from pydantic import BaseModel, Field
from typing import Any

class PersonaCreate(BaseModel): name: str = Field(min_length=1, max_length=200); description: str | None = None; language: str = "pt-BR"
class PersonaOut(PersonaCreate): id: str; created_at: datetime
class ManualSource(BaseModel): content: str = Field(min_length=1); filename: str | None = "manual.txt"; origin: str = "manual"; consent_status: str = "granted"; source_type: str = "manual"; owner_label: str | None = None
class MemoryCreate(BaseModel): content: str; memory_type: str = "semantic"; importance: float = .7; confidence: float = .8; tags: list[str] = []
class MemoryPatch(BaseModel): content: str | None = None; memory_type: str | None = None; importance: float | None = None; confidence: float | None = None; active: bool | None = None; tags: list[str] | None = None
class RelationshipCreate(BaseModel): name: str = Field(min_length=1, max_length=200); relationship_type: str = "important_person"; description: str = ""; importance: float = .8
class ChatRequest(BaseModel): message: str; session_id: str | None = None; debug: bool = False
class FeedbackRequest(BaseModel): content: str; kind: str = "correction"; message_id: str | None = None
class InterviewRequest(BaseModel): category: str = "general"; answer: str | None = None
