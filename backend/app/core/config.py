import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel


load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "Full-stack Starter")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_from_email: str = os.getenv("SMTP_FROM_EMAIL", "")
    smtp_from_name: str = os.getenv("SMTP_FROM_NAME", "DNS Intent")

    @property
    def smtp_configured(self) -> bool:
        return bool(
            self.smtp_host
            and self.smtp_port
            and self.smtp_username
            and self.smtp_password
            and self.smtp_from_email
        )


settings = Settings()
