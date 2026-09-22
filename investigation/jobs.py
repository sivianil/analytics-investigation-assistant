"""Bounded, persisted jobs for a single service process / single organization."""
import fcntl
import json
import logging
import os
import sqlite3
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone

log = logging.getLogger(__name__)


class QueueFull(Exception):
    pass


class Jobs:
    def __init__(self, settings, investigator):
        self.settings, self.investigator = settings, investigator
        settings.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = (settings.state_dir / 'service.lock').open('a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise RuntimeError('Use one API worker per state directory') from None
        self.path = settings.state_dir / 'jobs.sqlite'
        self.pool = ThreadPoolExecutor(max_workers=settings.max_concurrent_jobs)
        self.slots = threading.BoundedSemaphore(settings.max_pending_jobs + settings.max_concurrent_jobs)
        with self.connect() as conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, status TEXT NOT NULL, question TEXT NOT NULL, created TEXT NOT NULL, result TEXT)')
            conn.execute("UPDATE jobs SET status='interrupted', result=? WHERE status IN ('queued','running')",
                         (json.dumps({'error': 'Service restarted; resubmit the investigation.'}),))
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def submit(self, question):
        if not self.slots.acquire(blocking=False):
            raise QueueFull('Investigation queue is full')
        identifier = str(uuid.uuid4())
        try:
            with self.connect() as conn:
                conn.execute('INSERT INTO jobs VALUES (?, ?, ?, ?, NULL)',
                             (identifier, 'queued', question, datetime.now(timezone.utc).isoformat()))
            self.pool.submit(self._run, identifier, question)
        except Exception:
            self.slots.release()
            raise
        return identifier

    def _run(self, identifier, question):
        try:
            self._update(identifier, 'running', None)
            result = self.investigator.investigate(question)
            self._update(identifier, result['status'], result)
            log.info('investigation_finished id=%s status=%s', identifier, result['status'])
        except Exception as error:
            # No credentials, questions or raw exception strings in public errors/logs.
            log.error('investigation_failed id=%s type=%s', identifier, type(error).__name__)
            message = 'Investigation failed. Check provider access, index and sandbox readiness.'
            if getattr(error, 'code', None) in {'credit_balance_exhausted', 'insufficient_quota'}:
                message = 'OpenAI API credits are exhausted. Add API credits, then resubmit this investigation.'
            self._update(identifier, 'failed', {'error': message,
                                                'error_type': type(error).__name__})
        finally:
            self.slots.release()

    def _update(self, identifier, status, result):
        with self.connect() as conn:
            conn.execute('UPDATE jobs SET status=?, result=? WHERE id=?',
                         (status, json.dumps(result) if result is not None else None, identifier))

    def get(self, identifier):
        with self.connect() as conn:
            row = conn.execute('SELECT * FROM jobs WHERE id=?', (identifier,)).fetchone()
        if row is None:
            return None
        value = dict(row)
        value['result'] = json.loads(value['result']) if value['result'] else None
        return value

    def close(self):
        self.pool.shutdown(wait=True)
        fcntl.flock(self.lock, fcntl.LOCK_UN)
        self.lock.close()
