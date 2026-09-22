"""Start a loopback-only authenticated Qdrant server in the dedicated runtime."""
import os
import subprocess

from dotenv import dotenv_values

config = {**dotenv_values('.env'), **os.environ}
key = config.get('QDRANT_API_KEY')
if not key:
    raise SystemExit('Set QDRANT_API_KEY first')
docker = ['docker'] + (['--context', config['DOCKER_CONTEXT']] if config.get('DOCKER_CONTEXT') else [])
env = {**os.environ, 'QDRANT__SERVICE__API_KEY': key}
subprocess.run(docker + ['run', '-d', '--name', 'analytics-qdrant', '--restart', 'unless-stopped',
    '-p', '127.0.0.1:6333:6333', '--memory', '512m', '--cpus', '1', '--pids-limit', '128',
    '--cap-drop=ALL', '--security-opt=no-new-privileges:true',
    '-e', 'QDRANT__SERVICE__API_KEY', '-v', 'analytics-qdrant-data:/qdrant/storage',
    'qdrant/qdrant:v1.19.0'], env=env, check=True)
