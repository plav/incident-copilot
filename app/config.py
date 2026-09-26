from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Incident Copilot"
    environment: str = "development"

    # AWS Bedrock (used later)
    aws_region: str = "eu-west-1"
    bedrock_model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"

    # Database
    database_url: str = "postgresql://copilot:copilot@localhost:5433/incident_copilot"


settings = Settings()
