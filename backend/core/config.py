from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"
    debug: bool = True

    # PostgreSQL
    database_url: str = "postgresql+asyncpg://rag:rag_dev_password@postgres:5432/rag"
    database_url_sync: str = "host=localhost port=5432 dbname=rag user=rag password=rag_dev_password"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Weaviate
    weaviate_url: str = "http://weaviate:8080"

    # OpenAI
    openai_api_key: str = ""

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── AI Pipeline ──
    understand_model: str = "gpt-4o-mini"
    generate_model: str = "gpt-4o"
    history_window_size: int = 8
    answer_max_tokens: int = 800
    understand_max_tokens: int = 400
    weaviate_alpha: float = 0.65
    min_search_relevance: float = 0.15
    top_k_chunks: int = 6
    escalation_confidence_floor: float = 0.3

    # ── Reranking (optional) ──
    rerank_enabled: bool = False
    cohere_api_key: str = ""
    rerank_model: str = "rerank-multilingual-v3.0"
    rerank_candidate_count: int = 20
    rerank_top_n: int = 6

    # ── Assistant Identity (injected into prompts) ──
    assistant_name: str = "Tanger Med Knowledge Assistant"
    assistant_name_fr: str = "Assistant Documentaire Tanger Med"
    organization: str = "Tanger Med Group & CIRES Technologies"
    support_email: str = "contact@cirestechnologies.com"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
