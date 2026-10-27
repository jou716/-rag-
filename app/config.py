from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = "ExoRAG"
    app_env: str = "local"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    log_level: str = "INFO"

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_database: str = "exo_rag"
    mysql_user: str = "exo_rag_app"
    mysql_password: str = ""
    mysql_charset: str = "utf8mb4"
    mysql_connect_timeout: int = 5

    source_doc_path: Path = BASE_DIR / "工业外骨骼产品目录.docx"

    answer_generation_mode: str = "local"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: int = 90

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def mysql_url(self) -> URL:
        return URL.create(
            "mysql+pymysql",
            username=self.mysql_user,
            password=self.mysql_password,
            host=self.mysql_host,
            port=self.mysql_port,
            database=self.mysql_database,
            query={"charset": self.mysql_charset},
        )

    @property
    def mysql_target(self) -> str:
        return (
            f"{self.mysql_user}@{self.mysql_host}:{self.mysql_port}/"
            f"{self.mysql_database}"
        )

    @property
    def database_configured(self) -> bool:
        return bool(self.mysql_user and self.mysql_password)

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key and self.llm_model)


settings = Settings()
