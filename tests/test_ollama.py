import json

import httpx
import pytest

from investigation.config import Settings
from investigation.model import OllamaModel, make_model


def config(**changes):
    return Settings(_env_file=None, openai_api_key=None, assistant_api_token='t'*48, **changes)


def test_local_mode_needs_no_openai_key():
    settings = config()
    assert settings.model_provider == 'ollama'
    assert settings.model_name == 'qwen3.5:4b'
    assert isinstance(make_model(settings), OllamaModel)
    with pytest.raises(ValueError, match='OPENAI_API_KEY'):
        config(model_provider='openai')
    with pytest.raises(ValueError, match='OPENAI_API_KEY'):
        config(embedding_model='text-embedding-3-small')


@pytest.mark.parametrize('options', [
    {'ollama_url':'https://remote.example'},
    {'ollama_url':'http://user:secret@localhost:11434'},
    {'ollama_model':'qwen3.5:cloud'},
])
def test_remote_or_cloud_local_mode_is_rejected(options):
    with pytest.raises(ValueError):
        config(**options)


def test_native_ollama_contract_and_usage():
    def respond(request):
        body = json.loads(request.content)
        assert request.url.path == '/api/chat'
        assert 'authorization' not in request.headers
        assert body['model'] == 'qwen3.5:4b'
        assert body['format']['additionalProperties'] is False
        assert body['stream'] is False
        assert body['options']['num_predict'] <= 4096
        assert body['options']['num_ctx'] == 32768
        return httpx.Response(200, json={'done':True, 'done_reason':'stop',
            'prompt_eval_count':15, 'eval_count':20,
            'message':{'content':json.dumps({'action':'python','code':'print(2)',
                                            'answer':None,'evidence_ids':[]})}})
    with httpx.Client(base_url='http://127.0.0.1:11434', transport=httpx.MockTransport(respond)) as client:
        model = OllamaModel(config(), client)
        assert model.next([{'role':'user','content':'count'}]).code == 'print(2)'
        assert model.total_tokens == 35


def test_truncated_output_and_context_overflow_fail_closed():
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={
        'done':True,'done_reason':'length','message':{'content':'{}'}}))
    with httpx.Client(base_url='http://127.0.0.1:11434', transport=transport) as client:
        model = OllamaModel(config(), client)
        with pytest.raises(RuntimeError, match='incomplete'):
            model.next([])
        with pytest.raises(RuntimeError, match='context'):
            model.next([{'role':'user','content':'a'*40000}])


def test_local_endpoint_failure_never_falls_back_to_openai():
    with httpx.Client(base_url='http://127.0.0.1:11434', transport=httpx.MockTransport(
            lambda _: httpx.Response(503, json={'error':'not loaded'}))) as client:
        with pytest.raises(httpx.HTTPStatusError):
            OllamaModel(config(), client).next([])
