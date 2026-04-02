from pydantic_settings import BaseSettings
from functools import lru_cache


import os


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://hpa_user@localhost/health_pose_assistant"
    SECRET_KEY: str = "set-me-in-env"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    FRONTEND_URL: str = "http://localhost:3000"

    # 优先级：环境变量 > .env
    model_config = {"env_file": [".env"]}

    def __init__(self, **values):
        # 优先用环境变量覆盖
        for field in self.__fields__:
            env_val = os.environ.get(field)
            if env_val is not None:
                values[field] = env_val
        super().__init__(**values)


@lru_cache
def get_settings() -> Settings:
    return Settings()
