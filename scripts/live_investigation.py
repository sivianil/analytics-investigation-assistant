"""End-to-end evaluation on the full workbook; local by default, paid with OpenAI."""
import json
from pathlib import Path

from investigation.config import Settings
from investigation.engine import Investigator
from investigation.model import Embeddings
from investigation.retrieval import ContextStore

settings = Settings()
store = ContextStore(settings, Embeddings(settings))
store.validate(full_hash=True)
question = ('Across the complete dataset, how many invoice lines, return/cancellation lines, '
            'missing-customer lines and flagged IQR-outlier lines are there? Compute from all records. '
            'Count existing is_return and is_outlier flags and null customer_id values; do not redefine them. '
            'Print one JSON object with keys rows, returns, missing_customer and outliers. '
            'Explain why dropping missing customers or outliers could bias an investigation.')
Path('artifacts').mkdir(exist_ok=True)
with Path('artifacts/live-progress.jsonl').open('w') as progress:
    def on_event(event):
        progress.write(json.dumps(event)+'\n')
        progress.flush()
    result = Investigator(settings, store).investigate(question, on_event=on_event)
Path('artifacts/live-investigation.json').write_text(json.dumps(result, indent=2))
assert result['status'] == 'complete', result['status']
expected = {'rows':1067371, 'returns':22951, 'missing_customer':243007, 'outliers':190616}
observed = []
for evidence in result['evidence']:
    for line in [evidence['output'], *evidence['output'].splitlines()]:
        try:
            observed.append(json.loads(line))
        except json.JSONDecodeError:
            pass
assert any(isinstance(item, dict) and all(item.get(k)==v for k,v in expected.items())
           for item in observed), 'Computed counts do not match the independently verified baseline'
print(json.dumps({'status':result['status'], 'model':result['model'],
                  'total_tokens':result['total_tokens'], 'duration_seconds':result['duration_seconds'],
                  'counts_verified':expected, 'answer':result['answer']}, indent=2))
