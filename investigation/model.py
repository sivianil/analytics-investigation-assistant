from typing import Literal
import json
import threading
import httpx

from openai import OpenAI
from pydantic import BaseModel, ConfigDict


class Action(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['python', 'final']
    code: str | None
    answer: str | None
    evidence_ids: list[str]


class AstraModel:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client or OpenAI(api_key=settings.openai_api_key.get_secret_value(),
                                       timeout=90, max_retries=2)
        self.total_tokens = 0

    def next(self, messages):
        if self.total_tokens >= self.settings.max_total_tokens:
            raise RuntimeError('Investigation token budget exhausted')
        remaining = self.settings.max_total_tokens - self.total_tokens
        input_reserve = len(json.dumps(messages, ensure_ascii=False).encode()) + 1024
        if remaining - input_reserve < 256:
            raise RuntimeError('Investigation token budget exhausted before next request')
        response = self.client.responses.parse(
            model=self.settings.openai_model,
            reasoning={'effort': self.settings.reasoning_effort},
            input=messages,
            text_format=Action,
            max_output_tokens=min(self.settings.max_output_tokens,
                                  remaining - input_reserve),
            store=False,
        )
        if response.usage:
            self.total_tokens += response.usage.total_tokens
        if response.status != 'completed' or response.output_parsed is None:
            raise RuntimeError('Model response incomplete or refused')
        return response.output_parsed


class OllamaModel:
    """Native local inference. Never forwards the OpenAI key or uses a cloud fallback."""
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client
        self.total_tokens = 0

    def next(self, messages):
        remaining = self.settings.max_total_tokens - self.total_tokens
        # Bytes conservatively bound tokens; reserve space for structured output.
        input_reserve = len(json.dumps(messages, ensure_ascii=False).encode()) + 512
        available = min(remaining, self.settings.ollama_num_ctx) - input_reserve
        if available < 256:
            raise RuntimeError('Local model context or investigation token budget exhausted')
        payload = {'model': self.settings.ollama_model, 'messages': messages,
                   'stream': False, 'format': Action.model_json_schema(),
                   'think': self.settings.ollama_think, 'keep_alive': '2m',
                   'options': {'num_ctx': self.settings.ollama_num_ctx,
                               'num_predict': min(4096, self.settings.max_output_tokens, available),
                               'temperature': 0}}
        if self.client is not None:
            response = self.client.post('/api/chat', json=payload)
        else:
            with httpx.Client(base_url=self.settings.ollama_url,
                              timeout=self.settings.ollama_timeout, trust_env=False) as client:
                response = client.post('/api/chat', json=payload)
        response.raise_for_status()
        data = response.json()
        self.total_tokens += data.get('prompt_eval_count', 0) + data.get('eval_count', 0)
        if not data.get('done') or data.get('done_reason') == 'length':
            raise RuntimeError('Local model response incomplete; reduce the query or raise the output limit')
        return Action.model_validate_json(data['message']['content'])


def make_model(settings):
    return OllamaModel(settings) if settings.model_provider == 'ollama' else AstraModel(settings)


class Embeddings:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client
        self.local = None
        self.lock = threading.Lock()
        if settings.embedding_model == 'BAAI/bge-small-en-v1.5':
            if settings.embedding_dimensions != 384:
                raise ValueError('BAAI/bge-small-en-v1.5 requires 384 dimensions')
        else:
            self.client = client or OpenAI(api_key=settings.openai_api_key.get_secret_value(),
                                           timeout=30, max_retries=2)

    def encode(self, texts):
        if not texts or len(texts) > 64 or any(len(t) > 12000 for t in texts):
            raise ValueError('Embedding batch must contain 1..64 bounded documents')
        if self.settings.embedding_model == 'BAAI/bge-small-en-v1.5':
            with self.lock:
                if self.local is None:
                    from fastembed import TextEmbedding
                    self.local = TextEmbedding(model_name=self.settings.embedding_model,
                        cache_dir=str(self.settings.state_dir / 'embedding-cache'), threads=2)
                return [vector.tolist() for vector in self.local.embed(texts)]
        response = self.client.embeddings.create(model=self.settings.embedding_model,
                    dimensions=self.settings.embedding_dimensions, input=texts)
        return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
