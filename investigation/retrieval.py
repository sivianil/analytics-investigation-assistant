"""Versioned Qdrant context retrieval; never use nearest rows to estimate totals."""
import hashlib
import json
import uuid
from pathlib import Path

from qdrant_client import QdrantClient, models


def fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def documents(context):
    docs = [{'id': 'dataset', 'text': json.dumps({
        'grain': context['row_grain'], 'schema': context['schema'],
        'cautions': context['cautions']}, ensure_ascii=False)}]
    for i, report in enumerate(context['quality']['sheets']):
        docs.append({'id': f'quality-sheet-{i+1}', 'text': json.dumps(report, ensure_ascii=False)})
    definitions = {
        'returns': 'is_return is true for a C-prefixed invoice or negative quantity. Count invoice lines, invoices and customers separately. Returns are preserved, and signed line_value is quantity times unit_price.',
        'sales': 'For positive sales choose and disclose a filter, commonly quantity > 0 and unit_price > 0 and not is_return. Net signed line value includes negative returns. Neither is audited revenue; currency unspecified.',
        'missing': 'Unknown customer_id and description remain null. Missing customers cannot be assigned invented identities. Customer analyses must disclose exclusions.',
        'outliers': 'IQR outliers and duplicate rows are flagged, not automatically excluded. Report sensitivity to exclusions when relevant. Duplicate scope is within each source sheet.',
        'time': 'invoice_date is a local timestamp with no specified timezone. source_sheet labels are not calendar-year boundaries. Use invoice_date for monthly/yearly analysis and compare equal periods.',
        'causality': 'Sales changes can be decomposed into volume, price, mix, returns, customers and country effects. Observational transactions alone do not establish causal reasons.'}
    docs.extend({'id': name, 'text': text} for name, text in definitions.items())
    # BGE-small has a bounded context window. Small overlapping chunks prevent
    # later fields in a long quality report from being silently truncated.
    chunks = []
    for doc in docs:
        words = doc['text'].split()
        if len(words) <= 150:
            chunks.append(doc)
        else:
            for start in range(0, len(words), 120):
                chunks.append({'id': doc['id'] + f':part-{start//120+1}',
                               'text': ' '.join(words[start:start+150])})
    return chunks


class ContextStore:
    def __init__(self, settings, embeddings, client=None):
        self.settings, self.embeddings = settings, embeddings
        self.client = client or QdrantClient(url=settings.qdrant_url,
            api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
            timeout=15)
        self.manifest_path = settings.state_dir / 'index.json'

    def build(self):
        context = json.loads(self.settings.context_file.read_text())
        docs = documents(context)
        identity = {'dataset_sha256': fingerprint(self.settings.dataset),
                    'context_sha256': fingerprint(self.settings.context_file),
                    'embedding_model': self.settings.embedding_model,
                    'dimensions': self.settings.embedding_dimensions, 'version': 2}
        suffix = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        collection = 'analytics_' + suffix
        if not self.client.collection_exists(collection):
            self.client.create_collection(collection, vectors_config=models.VectorParams(
                size=self.settings.embedding_dimensions, distance=models.Distance.COSINE))
        vectors = self.embeddings.encode([d['text'] for d in docs])
        if len(vectors) != len(docs):
            raise ValueError('Embedding count mismatch')
        self.client.upsert(collection, wait=True, points=[models.PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, collection + ':' + doc['id'])),
            vector=vector, payload={'source_id': doc['id'], 'text': doc['text'],
                                    'dataset_sha256': identity['dataset_sha256']})
            for doc, vector in zip(docs, vectors, strict=True)])
        manifest = {**identity, 'collection': collection, 'documents': len(docs),
                    'dataset_size': self.settings.dataset.stat().st_size,
                    'dataset_mtime_ns': self.settings.dataset.stat().st_mtime_ns}
        self.settings.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self.manifest_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(manifest, indent=2))
        tmp.replace(self.manifest_path)
        return manifest

    def validate(self, full_hash=False):
        manifest = json.loads(self.manifest_path.read_text())
        stat = self.settings.dataset.stat()
        if (manifest['embedding_model'] != self.settings.embedding_model
            or manifest['dimensions'] != self.settings.embedding_dimensions
            or manifest['dataset_size'] != stat.st_size
            or manifest['dataset_mtime_ns'] != stat.st_mtime_ns
            or manifest['context_sha256'] != fingerprint(self.settings.context_file)
            or (full_hash and manifest['dataset_sha256'] != fingerprint(self.settings.dataset))):
            raise RuntimeError('Dataset or embeddings changed; rebuild the index')
        return manifest

    def search(self, question, limit=5):
        manifest = self.validate()
        vector = self.embeddings.encode([question])[0]
        points = self.client.query_points(manifest['collection'], query=vector, limit=limit,
            query_filter=models.Filter(must=[models.FieldCondition(key='dataset_sha256',
                            match=models.MatchValue(value=manifest['dataset_sha256']))]),
            with_payload=True).points
        return [{'id': 'context:' + p.payload['source_id'], 'text': p.payload['text'],
                 'score': p.score} for p in points]
