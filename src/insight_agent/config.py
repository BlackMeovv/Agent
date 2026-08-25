"""运行配置：全部从环境变量 / .env 读取，见仓库根目录 .env.example。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM 接入
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-chat"

    # 成本记账（每百万 token 单价，仅用于统计）
    llm_price_input_per_m: float = 0.27
    llm_price_output_per_m: float = 1.10

    # 采样与超时
    llm_temperature: float = 0.0
    llm_timeout_seconds: float = 60
    llm_max_retries: int = 3

    # Agent 行为
    agent_max_repair_rounds: int = 3
    agent_max_tokens_per_run: int = 200_000
    agent_max_cost_per_run: float = 0.05

    # Schema RAG：on=强制启用 / off=全量 schema / auto=表数超过 top_k 才启用
    schema_rag: str = "auto"
    schema_rag_top_k: int = 6
    # 业务字典 / few-shot 例句（jsonl，选填；路径不存在则自动跳过）
    glossary_path: str = "eval/knowledge/glossary.jsonl"
    examples_path: str = "eval/knowledge/examples.jsonl"
    knowledge_top_n: int = 3

    # 可选向量检索（任何 OpenAI 兼容 embeddings 接口；不配置则纯 BM25）
    embed_api_key: str = ""
    embed_base_url: str = ""
    embed_model: str = ""

    # 回答防幻觉数字校验
    answer_verify: bool = True

    # 图表沙箱：docker（生产）/ subprocess（开发兜底）/ auto（有 docker 用 docker）
    chart_executor: str = "auto"
    chart_image: str = "insight-agent-chart"
    chart_timeout_seconds: float = 20
    chart_out_dir: str = "data/charts"

    # 服务
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    # 前端联调 CORS：逗号分隔的允许来源（如 http://localhost:5173）；留空则关闭
    cors_allow_origins: str = ""
    # 结果缓存：redis://host:6379/0；不配置则用进程内 LRU
    redis_url: str = ""
    cache_ttl_seconds: int = 600
    # 压测/演示用 mock 模式：不调真实 LLM（回答固定套路 SQL），绝不能用于评测
    llm_mock: bool = False

    # 跨会话记忆
    memory_db_path: str = "data/memory.sqlite"

    # SQL 守卫
    sql_timeout_seconds: float = 15
    sql_max_rows: int = 200

    # 数据库
    db_path: str = "data/demo/ecommerce.sqlite"

    # Langfuse 追踪（选填；两个 key 都配置才启用，还需 `uv sync --extra trace`）
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()
