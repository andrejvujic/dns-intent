import os

from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "Full-stack Starter")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    smtp_host: str | None = os.getenv("SMTP_HOST")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str | None = os.getenv("SMTP_USERNAME")
    smtp_password: str | None = os.getenv("SMTP_PASSWORD")
    smtp_from: str = os.getenv("SMTP_FROM", "dnsintent@localhost")
    smtp_starttls: bool = os.getenv("SMTP_STARTTLS", "true").lower() == "true"


settings = Settings()
