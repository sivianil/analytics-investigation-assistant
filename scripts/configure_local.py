"""Create a private local .env without writing the inherited OpenAI API key."""
import os
import secrets
from pathlib import Path

path = Path('.env')
if path.exists():
    raise SystemExit('.env already exists; preserving it')
text = '\n'.join([
    'MODEL_PROVIDER=ollama', 'OLLAMA_MODEL=qwen3.5:4b',
    '# OPENAI_API_KEY is inherited from your environment, not copied here.',
    'ASSISTANT_API_TOKEN=' + secrets.token_urlsafe(48),
    'QDRANT_API_KEY=' + secrets.token_urlsafe(48),
    'QDRANT_URL=http://127.0.0.1:6333',
    'OPENAI_MODEL=gpt-6-astra', 'REASONING_EFFORT=high',
    'DOCKER_CONTEXT=colima-analytics', 'DATA_DIR=output', 'STATE_DIR=state',
    'MAX_CONCURRENT_JOBS=1', '',
])
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as handle:
    handle.write(text)
print('Created private .env; secrets not displayed')
