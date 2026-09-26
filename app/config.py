from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Incident Copilot"
    environment: str = "development"

    # AWS Bedrock
    aws_region: str = "eu-west-1"
    bedrock_model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"

    # Embeddings: "fake" (offline, for testing the pipeline) or "bedrock" (Titan v2)
    embedder: str = "fake"
    embedding_model_id: str = "amazon.titan-embed-text-v2:0"
    embedding_dim: int = 1024  # must match VECTOR(1024) in db/init.sql

    # Database
    database_url: str = "postgresql://copilot:copilot@localhost:5433/incident_copilot"


settings = Settings()
