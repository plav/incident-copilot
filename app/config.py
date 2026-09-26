from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Incident Copilot"
    environment: str = "development"

    # AWS Bedrock
    aws_region: str = "eu-west-1"
    bedrock_model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"

    # Embeddings: "fake" (random, pipeline testing), "ollama" (free, local) or "bedrock" (Titan v2)
    embedder: str = "fake"
    ollama_url: str = "http://localhost:11434"
    ollama_embed_model: str = "mxbai-embed-large"  # 1024 dims, matches the DB
    embedding_model_id: str = "amazon.titan-embed-text-v2:0"
    embedding_dim: int = 1024  # must match VECTOR(1024) in db/init.sql

    # LLM for /triage: "ollama" (free, local) or "fake" (fixed stub answer)
    llm: str = "ollama"
    ollama_chat_model: str = "llama3.2"

    # Database
    database_url: str = "postgresql://copilot:copilot@localhost:5433/incident_copilot"


settings = Settings()
