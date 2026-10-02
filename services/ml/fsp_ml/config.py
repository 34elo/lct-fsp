from fsp_platform.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "ml"
    taxonomy_version: int = 1
    embedding_dim: int = 1024  # bge-m3
