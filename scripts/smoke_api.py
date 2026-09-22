import json
import httpx
from investigation.config import Settings
from investigation.model import Embeddings
from investigation.retrieval import ContextStore

settings = Settings()
headers = {'Authorization': 'Bearer ' + settings.assistant_api_token.get_secret_value()}
with httpx.Client(base_url='http://127.0.0.1:8000', timeout=30) as client:
    assert client.get('/healthz').status_code == 200
    assert client.get('/readyz').status_code == 401
    ready = client.get('/readyz', headers=headers)
    assert ready.status_code == 200, ready.text
    assert client.post('/v1/investigations', json={'question':'Count rows'}).status_code == 401
store = ContextStore(settings, Embeddings(settings))
matches = store.search('Why should returns and cancellations be kept in net sales?')
assert any(item['id']=='context:returns' for item in matches), matches
print(json.dumps({'health':'passed','authentication':'passed','readiness':'passed',
                  'live_qdrant_retrieval':[item['id'] for item in matches]}))
