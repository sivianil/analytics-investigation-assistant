"""Audit tracked files and fetched Git history before making this repository public."""
import os
import re
import subprocess
from pathlib import PurePosixPath

from dotenv import dotenv_values

secrets = [value.encode() for key, value in dotenv_values('.env').items()
           if value and ('KEY' in key or 'TOKEN' in key)]
if os.environ.get('OPENAI_API_KEY'):
    secrets.append(os.environ['OPENAI_API_KEY'].encode())
patterns = [re.compile(rb'sk-(?:proj-)?[A-Za-z0-9_-]{24,}'),
            re.compile(rb'gh[pousr]_[A-Za-z0-9]{25,}'),
            re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')]

def validate_path(name):
    path = PurePosixPath(name)
    if path.name == '.env.example':
        return
    if (path.name.startswith('.env') or any(part in {'output','data','state','artifacts','.venv'} for part in path.parts)
        or path.suffix.lower() in {'.xlsx','.sqlite','.jsonl','.zip','.ses'} or path.name == '.DS_Store'):
        raise SystemExit('Private/generated file is tracked in history: ' + name)

def validate_data(name, data):
    if len(data) > 1_000_000:
        raise SystemExit('Unexpected large tracked file: ' + name)
    if any(secret in data for secret in secrets) or any(pattern.search(data) for pattern in patterns):
        raise SystemExit('Potential secret found in: ' + name)

tracked = subprocess.check_output(['git','ls-files','-z']).decode().split('\0')
for name in filter(None, tracked):
    validate_path(name)
    with open(name, 'rb') as handle:
        validate_data(name, handle.read())

objects = subprocess.check_output(['git','rev-list','--objects','--all']).decode().splitlines()
count = 0
for entry in objects:
    sha, _, name = entry.partition(' ')
    if not name or subprocess.check_output(['git','cat-file','-t',sha]).strip() != b'blob':
        continue
    validate_path(name)
    validate_data(name, subprocess.check_output(['git','cat-file','blob',sha]))
    count += 1
print(f'Public-export audit passed: {len(list(filter(None, tracked)))} tracked files and {count} historical blobs; no detected secrets/data artifacts.')
