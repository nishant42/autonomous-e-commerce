"""Database access. SQLite for the demo, one swap away from Postgres.

Everything the platform does goes through a connection from here, so the
Postgres migration is: change `connect()` and the two dialect constants.
"""
import os
import sqlite3
import json
import uuid
from datetime import datetime, timezone

DB_PATH = os.environ.get("ENGINE_DB", os.path.join(os.path.dirname(__file__), "..", "engine.db"))
SCHEMA = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")

# The only dialect-specific strings in the codebase.
SKIP_LOCKED = ""          # Postgres: "FOR UPDATE SKIP LOCKED"
JSON_TYPE = "TEXT"        # Postgres: "jsonb"


def connect():
    conn = sqlite3.connect(DB_PATH, isolation_level=None, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init(reset=False):
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = connect()
    with open(SCHEMA) as fh:
        conn.executescript(fh.read())
    return conn


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix):
    return "%s_%s" % (prefix, uuid.uuid4().hex[:10])


def rows(conn, sql, args=()):
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def one(conn, sql, args=()):
    r = conn.execute(sql, args).fetchone()
    return dict(r) if r else None


def scalar(conn, sql, args=(), default=0):
    r = conn.execute(sql, args).fetchone()
    return default if r is None or r[0] is None else r[0]


def dumps(obj):
    return json.dumps(obj, sort_keys=True, default=str)
