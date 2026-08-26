from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Loaded from environment; in deployed environments these are injected
    from GCP Secret Manager, not from a .env file. See spec §12."""

    gemini_api_key: str = ""
    gcp_project_id: str = ""
    gcs_bucket_name: str = ""
    supabase_url: str = ""
    supabase_service_key: str = ""
    cloud_tasks_queue: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
