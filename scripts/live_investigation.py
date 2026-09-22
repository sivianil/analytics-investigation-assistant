"""Explicit opt-in paid, end-to-end evaluation on the full prepared workbook."""
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
            'missing-customer lines and IQR-outlier lines are there? Compute from all records. '
            'Print one JSON object with keys rows, returns, missing_customer and outliers. '
            'Explain why dropping missing customers or outliers could bias an investigation.')
result = Investigator(settings, store).investigate(question)
assert result['status'] == 'complete', result['status']
expected = {'rows':1067371, 'returns':22951, 'missing_customer':243007, 'outliers':190616}
observed = []
for evidence in result['evidence']:
    for line in evidence['output'].splitlines():
        try:
            observed.append(json.loads(line))
        except json.JSONDecodeError:
            pass
assert any(isinstance(item, dict) and all(item.get(k)==v for k,v in expected.items())
           for item in observed), 'Computed counts do not match the independently verified baseline'
Path('artifacts').mkdir(exist_ok=True)
Path('artifacts/live-investigation.json').write_text(json.dumps(result, indent=2))
print(json.dumps({'status':result['status'], 'model':result['model'],
                  'total_tokens':result['total_tokens'], 'duration_seconds':result['duration_seconds'],
                  'counts_verified':expected, 'answer':result['answer']}, indent=2))
