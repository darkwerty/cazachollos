from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")  # ignore Telegram and Gemini keys

    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    # "require" for managed servers like Azure Database for PostgreSQL; empty for the local container
    POSTGRES_SSLMODE: str = ""

    def _url(self, driver: str, ssl_param: str) -> str:
        auth = f"{quote_plus(self.POSTGRES_USER)}:{quote_plus(self.POSTGRES_PASSWORD)}"
        url = f"postgresql+{driver}://{auth}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        return f"{url}?{ssl_param}={self.POSTGRES_SSLMODE}" if self.POSTGRES_SSLMODE else url

    @property
    def DATABASE_URL(self) -> str:
        return self._url("asyncpg", "ssl")

    @property
    def SYNC_DATABASE_URL(self) -> str:
        """Same database for the Streamlit dashboard, which uses the sync driver (psycopg2)."""
        return self._url("psycopg2", "sslmode")


settings = Settings()
