import hmac
import logging
import subprocess
import httpx
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from investigation.config import Settings
from investigation.engine import Investigator
from investigation.jobs import Jobs, QueueFull
from investigation.model import Embeddings
from investigation.retrieval import ContextStore


class Question(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    question: str = Field(min_length=3, max_length=8000)


class BodyLimit:
    def __init__(self, app, limit=16000):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        body, messages = 0, []
        while True:
            message = await receive()
            body += len(message.get('body', b''))
            if body > self.limit:
                await send({'type': 'http.response.start', 'status': 413,
                            'headers': [(b'content-type', b'application/json')]})
                await send({'type': 'http.response.body', 'body': b'{"detail":"Request too large"}'})
                return
            messages.append(message)
            if not message.get('more_body', False):
                break
        async def replay():
            return messages.pop(0) if messages else await receive()
        await self.app(scope, replay, send)


def create_app(settings=None, store=None, investigator=None):
    settings = settings or Settings()
    store = store or ContextStore(settings, Embeddings(settings))
    investigator = investigator or Investigator(settings, store)

    @asynccontextmanager
    async def lifespan(app):
        logging.basicConfig(level=logging.INFO)
        store.validate(full_hash=True)
        app.state.jobs = Jobs(settings, investigator)
        try:
            yield
        finally:
            app.state.jobs.close()

    app = FastAPI(title='Analytics Investigation Assistant', version='1.0.0',
                  lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(BodyLimit)
    bearer = HTTPBearer(auto_error=False)

    def authorize(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credentials is None or not hmac.compare_digest(
                credentials.credentials.encode(), settings.assistant_api_token.get_secret_value().encode()):
            raise HTTPException(status_code=401, detail='Unauthorized', headers={'WWW-Authenticate': 'Bearer'})

    @app.get('/healthz')
    def health():
        return {'status': 'ok'}

    @app.get('/readyz', dependencies=[Depends(authorize)])
    def ready():
        try:
            manifest = store.validate()
            store.client.get_collection(manifest['collection'])
            command = ['docker'] + (['--context', settings.docker_context] if settings.docker_context else [])
            subprocess.run(command + ['image', 'inspect', settings.sandbox_image],
                           check=True, capture_output=True, timeout=10)
            if settings.model_provider == 'ollama':
                with httpx.Client(base_url=settings.ollama_url, timeout=5, trust_env=False) as client:
                    response = client.get('/api/tags')
                    response.raise_for_status()
                    if not any(item['name'] == settings.ollama_model for item in response.json()['models']):
                        raise RuntimeError('Configured local model is not installed')
        except Exception:
            raise HTTPException(status_code=503, detail='Index, sandbox or local model unavailable') from None
        return {'status': 'ready', 'model': settings.model_name, 'provider': settings.model_provider}

    @app.post('/v1/investigations', status_code=202, dependencies=[Depends(authorize)])
    def investigate(payload: Question):
        try:
            store.validate()
            identifier = app.state.jobs.submit(payload.question)
        except QueueFull:
            raise HTTPException(status_code=429, detail='Investigation queue full', headers={'Retry-After': '30'}) from None
        except (FileNotFoundError, RuntimeError):
            raise HTTPException(status_code=503, detail='Dataset index unavailable; rebuild it') from None
        return {'id': identifier, 'status': 'queued', 'status_url': f'/v1/investigations/{identifier}'}

    @app.get('/v1/investigations/{identifier}', dependencies=[Depends(authorize)])
    def result(identifier: UUID):
        value = app.state.jobs.get(str(identifier))
        if value is None:
            raise HTTPException(status_code=404, detail='Investigation not found')
        return value

    return app
