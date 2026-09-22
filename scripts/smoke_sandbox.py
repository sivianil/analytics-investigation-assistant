"""Real container checks; never replaces execution with a mock."""
import json
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from sandbox import DockerSandbox

load_dotenv()
context = os.environ.get('DOCKER_CONTEXT')
data = Path('state/smoke.jsonl')
data.parent.mkdir(parents=True, exist_ok=True)
data.write_text('{"quantity":2}\n')
sandbox = DockerSandbox(context=context, timeout=30)
code = '''import json, os, socket
assert os.getuid() == 65534
assert 'OPENAI_API_KEY' not in os.environ
assert not os.path.exists('/var/run/docker.sock')
assert open('/data/input').read().strip() == '{"quantity":2}'
for path in ['/data/input', '/root-test']:
    try:
        open(path, 'w').write('denied')
    except OSError:
        pass
    else:
        raise AssertionError('Unexpected write permission')
sock = socket.socket()
sock.settimeout(1)
assert sock.connect_ex(('1.1.1.1', 443)) != 0
print(json.dumps({'uid':os.getuid(),'read_only':True,'network_blocked':True,'secrets_absent':True}))
'''
result = sandbox.execute(code, data)
assert result['exit_code'] == 0, result
timeout = DockerSandbox(context=context, timeout=2).execute('import time; time.sleep(30)', data)
assert timeout['timed_out'], timeout
overflow = DockerSandbox(context=context, timeout=10, output_limit=1024).execute("print('a'*20000)", data)
assert overflow['truncated'] and len(overflow['output']) == 1024, overflow
docker = ['docker'] + (['--context', context] if context else [])
leftovers = subprocess.check_output(docker + ['ps','-aq','--filter','name=retail-agent-'], text=True)
assert not leftovers.strip(), 'Leaked execution containers'
print(json.dumps({'isolation': json.loads(result['output']), 'timeout_cleanup':True, 'output_limit':True}))
