"""Live reasoning check with an independently computed equal-period baseline."""
import json
from pathlib import Path

from investigation.config import Settings
from investigation.engine import Investigator
from investigation.model import Embeddings
from investigation.retrieval import ContextStore
from sandbox import DockerSandbox

settings = Settings()
store = ContextStore(settings, Embeddings(settings))
store.validate(full_hash=True)
question = (
    'Compare January through November 2010 with January through November 2011. '
    'Compute rows and net signed line_value in each period from the full file. '
    'Also compute positive_sales as the sum of line_value only where quantity > 0, '
    'unit_price > 0 and is_return is false. Print one JSON object keyed by "2010" '
    'and "2011", with numeric rows, net and positive_sales for each. '
    'Explain the direction of change, why net differs from positive sales, and '
    'why this comparison does not prove a causal reason for the change. '
    'Use invoice_date and equal month windows, not source_sheet labels.')
result = Investigator(settings, store).investigate(question)
Path('artifacts').mkdir(exist_ok=True)
Path('artifacts/live-comparison.json').write_text(json.dumps(result, indent=2))
assert result['status'] == 'complete', result['status']
baseline_code = '''import json
from decimal import Decimal
out = {year:dict(rows=0,net=Decimal(0),positive_sales=Decimal(0)) for year in ['2010','2011']}
with open('/data/input') as handle:
    for line in handle:
        row=json.loads(line)
        date=row['invoice_date']
        if date is None or date[:4] not in out or int(date[5:7])>11: continue
        item=out[date[:4]]
        item['rows']+=1
        value=Decimal(str(row['line_value']))
        item['net']+=value
        if row['quantity']>0 and row['unit_price']>0 and not row['is_return']:
            item['positive_sales']+=value
for item in out.values():
    item['net']=float(item['net'])
    item['positive_sales']=float(item['positive_sales'])
print(json.dumps(out))
'''
baseline = DockerSandbox(context=settings.docker_context).execute(baseline_code, settings.dataset)
assert baseline['exit_code'] == 0, baseline
expected = json.loads(baseline['output'])
observed = []
for evidence in result['evidence']:
    if evidence['exit_code'] != 0:
        continue
    for text in [evidence['output'], *evidence['output'].splitlines()]:
        try:
            observed.append(json.loads(text))
        except json.JSONDecodeError:
            pass
def matches(item):
    try:
        return all(item[y]['rows'] == expected[y]['rows'] and
                   all(abs(item[y][key] - expected[y][key]) < 0.01 for key in ['net','positive_sales'])
                   for y in expected)
    except (TypeError, KeyError):
        return False
assert any(matches(item) for item in observed), 'Model-computed comparison differs from the independent baseline'
print(json.dumps({'model':result['model'],'status':'verified','baseline':expected,
                  'duration_seconds':result['duration_seconds'], 'answer':result['answer']}, indent=2))
