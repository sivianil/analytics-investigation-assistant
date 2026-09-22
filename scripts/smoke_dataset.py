import json
from investigation.config import Settings
from sandbox import DockerSandbox

settings = Settings()
code = '''import json
totals = dict(rows=0, returns=0, missing_customer=0, outliers=0)
with open('/data/input') as handle:
    for line in handle:
        row = json.loads(line)
        totals['rows'] += 1
        totals['returns'] += row['is_return']
        totals['missing_customer'] += row['customer_id'] is None
        totals['outliers'] += row['is_outlier']
print(json.dumps(totals))
'''
result = DockerSandbox(context=settings.docker_context, timeout=60).execute(code, settings.dataset)
assert result['exit_code'] == 0 and not result['timed_out'], result
expected = {'rows':1067371, 'returns':22951, 'missing_customer':243007, 'outliers':190616}
assert json.loads(result['output']) == expected, result
print(json.dumps({'live_container_dataset_validation':'passed', 'counts':expected}))
