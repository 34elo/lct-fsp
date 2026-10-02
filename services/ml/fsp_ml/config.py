from fsp_platform.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "ml"
    taxonomy_version: int = 1
    embedding_dim: int = 1024  # bge-m3
    embedding_model_path: str = ""  # локальный каталог bge-m3; пусто → фейк при ML_FAKE=true
    embedding_max_texts: int = 128
    core_url: str = "http://core-api:8000"
    service_token_ml: str = ""  # SERVICE_TOKEN_ML из .env; пусто → снимок графа не тянем
