import json
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from investigation.api import create_app
from investigation.config import Settings
from investigation.engine import Investigator
from investigation.jobs import Jobs, QueueFull
from investigation.model import Action, AstraModel
from investigation.retrieval import ContextStore


@pytest.fixture
def settings(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    (data/'cleaned.jsonl').write_text('{"quantity":2}\n')
    (data/'llm_context.json').write_text(json.dumps({'row_grain':'line','schema':{'quantity':'Float64'},
        'cautions':['Test data'], 'quality':{'sheets':[{'input_rows':1}]}}))
    return Settings(_env_file=None, openai_api_key='test-key', assistant_api_token='t'*48,
                    data_dir=data, state_dir=tmp_path/'state', max_concurrent_jobs=1, max_pending_jobs=1,
                    embedding_dimensions=256)


class FakeEmbeddings:
    def encode(self, texts):
        return [[1.0] + [0.0]*255 for _ in texts]


def make_store(settings):
    return ContextStore(settings, FakeEmbeddings(), QdrantClient(':memory:'))


def test_qdrant_index_search_and_dataset_change(settings):
    store = make_store(settings)
    manifest = store.build()
    assert manifest['documents'] == 8
    matches = store.search('returns')
    assert matches and matches[0]['id'].startswith('context:')
    assert store.validate(full_hash=True) == manifest
    settings.dataset.write_text('{"quantity":200}\n')
    with pytest.raises(RuntimeError, match='rebuild'):
        store.search('returns')


def test_embedding_config_change_rejected(settings):
    store = make_store(settings)
    store.build()
    settings.embedding_dimensions = 512
    with pytest.raises(RuntimeError):
        store.validate()


def test_astra_responses_contract(settings):
    client = MagicMock()
    action = Action(action='python', code='print(2)', answer=None, evidence_ids=[])
    client.responses.parse.return_value = SimpleNamespace(status='completed', output_parsed=action,
                                                         usage=SimpleNamespace(total_tokens=42))
    model = AstraModel(settings, client)
    assert model.next([{'role':'user','content':'count'}]) == action
    call = client.responses.parse.call_args.kwargs
    assert call['model'] == 'gpt-6-astra'
    assert call['reasoning'] == {'effort':'high'}
    assert call['store'] is False
    assert 'temperature' not in call
    assert model.total_tokens == 42
    client.responses.parse.return_value.status = 'incomplete'
    with pytest.raises(RuntimeError, match='incomplete'):
        model.next([])


def test_model_budget_gate(settings):
    model = AstraModel(settings, MagicMock())
    model.total_tokens = settings.max_total_tokens
    with pytest.raises(RuntimeError, match='budget'):
        model.next([])


def test_remote_vector_database_requires_tls_and_auth(settings):
    values = settings.model_dump()
    values['qdrant_url'] = 'http://remote.example:6333'
    with pytest.raises(ValueError, match='HTTPS'):
        Settings(_env_file=None, **values)
    values['qdrant_url'] = 'https://remote.example'
    values['qdrant_api_key'] = 'test-vector-key'
    assert Settings(_env_file=None, **values).qdrant_url.startswith('https')


def test_investigation_repairs_errors_and_requires_real_evidence(settings):
    store = make_store(settings)
    store.build()
    responses = iter([
        Action(action='final', answer='made up', code=None, evidence_ids=['exec:999']),
        Action(action='python', code='bad', answer=None, evidence_ids=[]),
        Action(action='python', code='print(2)', answer=None, evidence_ids=[]),
        Action(action='final', answer='Quantity is 2 [exec:3]', code=None, evidence_ids=['exec:3'])])
    model = SimpleNamespace(next=lambda messages: next(responses), total_tokens=10)
    sandbox = MagicMock()
    sandbox.execute.side_effect = [
        {'exit_code':1, 'output':'NameError', 'timed_out':False, 'truncated':False},
        {'exit_code':0, 'output':'2', 'timed_out':False, 'truncated':False}]
    result = Investigator(settings, store, lambda:model, lambda:sandbox).investigate('Quantity?')
    assert result['status'] == 'complete'
    assert len(result['evidence']) == 2
    assert result['evidence_ids'] == ['exec:3']


def test_api_auth_body_limits_and_validated_input(settings):
    store = make_store(settings)
    store.build()
    investigator = SimpleNamespace(investigate=lambda q: {'status':'complete', 'answer':'Done'})
    app = create_app(settings, store, investigator)
    headers = {'Authorization':'Bearer ' + 't'*48}
    with TestClient(app) as client:
        assert client.get('/healthz').status_code == 200
        assert client.post('/v1/investigations', json={'question':'count'}).status_code == 401
        assert client.post('/v1/investigations', headers=headers, json={'question':'count','path':'/etc/passwd'}).status_code == 422
        assert client.post('/v1/investigations', headers=headers, content=b'x'*16001).status_code == 413
        response = client.post('/v1/investigations', headers=headers, json={'question':'count'})
        assert response.status_code == 202
        assert client.get(response.json()['status_url']).status_code == 401
        assert client.get(response.json()['status_url'], headers=headers).status_code == 200
        assert client.get('/v1/investigations/not-a-uuid', headers=headers).status_code == 422


def test_jobs_persistence_admission_and_single_worker(settings):
    event = threading.Event()
    def work(question):
        event.wait(5)
        return {'status':'complete','answer':'Done'}
    jobs = Jobs(settings, SimpleNamespace(investigate=work))
    try:
        identifier = jobs.submit('one')
        jobs.submit('two')
        with pytest.raises(QueueFull):
            jobs.submit('three')
        with pytest.raises(RuntimeError, match='one API worker'):
            Jobs(settings, SimpleNamespace())
    finally:
        event.set()
        jobs.close()
    restored = Jobs(settings, SimpleNamespace(investigate=work))
    try:
        assert restored.get(identifier)['status'] == 'complete'
    finally:
        restored.close()


def test_failure_does_not_expose_exception_secret(settings):
    event = threading.Event()
    def work(question):
        try:
            raise ValueError('secret-key-must-not-leak')
        finally:
            event.set()
    jobs = Jobs(settings, SimpleNamespace(investigate=work))
    identifier = jobs.submit('one')
    event.wait(5)
    jobs.close()
    assert 'secret-key' not in json.dumps(jobs.get(identifier))
