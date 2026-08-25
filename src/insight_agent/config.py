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
