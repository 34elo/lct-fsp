from fsp_platform.config import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "ml"
    taxonomy_version: int = 1
    embedding_dim: int = 1024  # bge-m3
    embedding_model: str = "bge-m3"  # lite: multilingual-e5-small (384, +нули)
    embedding_model_path: str = ""  # локальный каталог bge-m3; пусто → фейк при ML_FAKE=true
    embedding_max_texts: int = 128
    # модель с HF (кеш HF_HOME в томе), если локального каталога нет; пусто → по имени
    # модели (multilingual-e5-small → intfloat/...); EMBEDDING_AUTOLOAD=false выключает загрузку
    embedding_hf_id: str = ""
    embedding_autoload: bool = True
    embedding_cache_dir: str = ""  # пусто → HF_HOME / ~/.cache/huggingface
    core_url: str = "http://core-api:8000"
    service_token_ml: str = ""  # SERVICE_TOKEN_ML из .env; пусто → снимок графа не тянем
    # false (профиль lite/024): LLM не вызываем, каждая функция идёт правиловой веткой
    llm_enabled: bool = True
    # LLM: OpenAI-совместимый llama-server; значения — из окружения (.env)
    llm_profile: str = "gpu"  # gpu | cpu
    llm_base_url: str = ""  # пусто при ML_FAKE=false → воркер не стартует
    llm_api_key: str = ""
    llm_model: str = "qwen3-vl-4b"
    llm_timeout: float = 60.0
    llm_max_tokens: int = 4096
