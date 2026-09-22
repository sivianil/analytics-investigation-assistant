"""Local SQLite reads; remote connectors require read-only credentials supplied by caller."""
import sqlite3
from pathlib import Path
import pandas as pd

def read_sqlite(path, query, params=(), limit=10000):
    if not 1 <= limit <= 100000:
        raise ValueError('limit must be 1..100000')
    with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True) as connection:
        connection.execute('PRAGMA query_only=ON')
        # SQLite authorizer is a permission boundary, not a SELECT-prefix heuristic.
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
        connection.set_authorizer(lambda op, a, b, db, trigger: sqlite3.SQLITE_OK if op in allowed and str(b).lower() != 'load_extension' else sqlite3.SQLITE_DENY)
        import time
        deadline = time.monotonic() + 10
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        cur = connection.execute(query, params)
        return pd.DataFrame(cur.fetchmany(limit), columns=[d[0] for d in cur.description])

def read_database(engine, query, params=None, limit=10000):
    """Trusted application ingestion only. NEVER give engine/credentials to generated code.

    Caller must enforce read-only database role, query timeout and approved query.
    Compatible with SQLAlchemy engines for PostgreSQL/MySQL/etc. Driver installed separately.
    """
    from sqlalchemy import text
    if not 1 <= limit <= 100000:
        raise ValueError('limit must be 1..100000')
    with engine.connect().execution_options(stream_results=True) as conn:
        result = conn.execute(text(query), params or {})
        return pd.DataFrame(result.fetchmany(limit), columns=result.keys())
