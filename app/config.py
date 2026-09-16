from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Incident Copilot"
    environment: str = "development"

    # AWS Bedrock (used later)
    aws_region: str = "eu-west-1"
    bedrock_model_id: str = "anthropic.claude-3-sonnet-20240229-v1:0"

    # Database (used later)
    database_url: str = "postgresql://postgres:postgres@localhost:5432/incident_copilot"

    class Config:
        env_file = ".env"


settings = Settings()
