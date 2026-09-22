from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from urllib.parse import urlsplit
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    openai_api_key: SecretStr
    assistant_api_token: SecretStr = Field(min_length=32)
    openai_model: Literal['gpt-6-astra'] = 'gpt-6-astra'
    reasoning_effort: Literal['low', 'medium', 'high', 'xhigh', 'max'] = 'high'
    embedding_model: Literal['BAAI/bge-small-en-v1.5', 'text-embedding-3-small'] = 'BAAI/bge-small-en-v1.5'
    embedding_dimensions: int = Field(default=384, ge=256, le=1536)
    qdrant_url: str = 'http://127.0.0.1:6333'
    qdrant_api_key: SecretStr | None = None
    data_dir: Path = Path('output')
    state_dir: Path = Path('state')
    docker_context: str | None = None
    sandbox_image: str = 'retail-agent-sandbox:local'
    sandbox_timeout: int = Field(default=60, ge=1, le=300)
    max_steps: int = Field(default=8, ge=2, le=12)
    max_output_tokens: int = Field(default=6000, ge=1000, le=16000)
    max_total_tokens: int = Field(default=80000, ge=1000, le=200000)
    max_concurrent_jobs: int = Field(default=2, ge=1, le=4)
    max_pending_jobs: int = Field(default=8, ge=1, le=32)

    @model_validator(mode='after')
    def secure_remote_qdrant(self):
        address = urlsplit(self.qdrant_url)
        if address.scheme not in {'http', 'https'} or not address.hostname or address.username or address.password:
            raise ValueError('Qdrant URL must be HTTP(S) without embedded credentials')
        if address.hostname not in {'127.0.0.1', 'localhost', '::1'}:
            if address.scheme != 'https' or self.qdrant_api_key is None:
                raise ValueError('Remote Qdrant requires HTTPS and an API key')
        return self

    @property
    def dataset(self):
        return self.data_dir.resolve() / 'cleaned.jsonl'

    @property
    def context_file(self):
        return self.data_dir.resolve() / 'llm_context.json'
