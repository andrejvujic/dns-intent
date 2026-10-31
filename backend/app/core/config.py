import os

from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "Full-stack Starter")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")


settings = Settings()
