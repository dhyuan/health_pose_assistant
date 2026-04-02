from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import List


import os


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://hpa_user@localhost/health_pose_assistant"
    SECRET_KEY: str = "set-me-in-env"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    FRONTEND_URL: str = "http://localhost:3000"
    FRONTEND_URLS: str = "http://localhost:3000,http://100.87.10.116:3000"

    # 优先级：环境变量 > .env
    model_config = {"env_file": [".env"]}

    def __init__(self, **values):
        # 优先用环境变量覆盖
        for field in self.__fields__:
            env_val = os.environ.get(field)
            if env_val is not None:
                values[field] = env_val
        super().__init__(**values)

    @property
    def cors_origins(self) -> List[str]:
        """Return normalized CORS origins from FRONTEND_URLS/FRONTEND_URL."""
        raw = self.FRONTEND_URLS or self.FRONTEND_URL
        origins = [x.strip().rstrip("/") for x in raw.split(",") if x.strip()]
        if not origins:
            return [self.FRONTEND_URL.rstrip("/")]
        return origins


@lru_cache
def get_settings() -> Settings:
    return Settings()
