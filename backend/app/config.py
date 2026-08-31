import json
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://mikoshi:mikoshi@localhost:5432/mikoshi"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    embedding_dimensions: int = 384
    max_upload_mb: int = 25
    analysis_with_llm: bool = True
    ollama_timeout_seconds: int = 90
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()

# The JSON file is intentionally simple to edit on Windows. Environment
# variables still provide the initial defaults and the selected local model
# is then read from config/ollama.json when present.
ollama_config_path = Path(__file__).resolve().parents[2] / "config" / "ollama.json"
try:
    configured_ollama = json.loads(ollama_config_path.read_text(encoding="utf-8"))
    updates = {}
    if isinstance(configured_ollama.get("base_url"), str): updates["ollama_base_url"] = configured_ollama["base_url"]
    if isinstance(configured_ollama.get("selected_model"), str): updates["ollama_model"] = configured_ollama["selected_model"]
    if isinstance(configured_ollama.get("enabled"), bool): updates["analysis_with_llm"] = configured_ollama["enabled"]
    if updates: settings = settings.model_copy(update=updates)
except (OSError, ValueError, json.JSONDecodeError):
    pass
