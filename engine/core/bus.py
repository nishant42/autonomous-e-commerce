"""The bus: durable handover of work, and the transactional outbox.

Phase 1 is a Postgres/SQLite table. Agent code only ever sees publish() and
the worker loop, so swapping in Service Bus or Temporal is a driver change.
"""
import json
import random
from datetime import datetime, timedelta, timezone

from core import db

MAX_ATTEMPTS = 5
LOCK_TIMEOUT_SECONDS = 120    # a worker that dies mid-job must not block its session forever
HANDLERS = {}            # topic -> callable(conn, payload)


def subscribe(topic):
    def deco(fn):
        HANDLERS[topic] = fn
        return fn
    return deco


def publish(conn, topic, payload, session_key=None, delay_seconds=0):
    """Enqueue work. Called by adapters, cron, and the gateway."""
    run_after = (datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)).isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO work_queue (topic, session_key, payload, run_after, created_at) VALUES (?,?,?,?,?)",
        (topic, session_key or "", db.dumps(payload), run_after, db.now()),
    )


def emit(conn, topic, payload, session_key=None):
    """Write an event to the outbox inside the caller's transaction.

    The event cannot exist unless the fact committed, and cannot be lost if it did.
    """
    conn.execute(
        "INSERT INTO outbox (topic, session_key, payload, created_at) VALUES (?,?,?,?)",
        (topic, session_key or "", db.dumps(payload), db.now()),
    )


def relay(conn):
    """Move committed outbox rows onto the queue. Idempotent; safe to re-run."""
    conn.execute("SAVEPOINT relay_outbox")
    try:
        moved = _relay(conn)
        conn.execute("RELEASE SAVEPOINT relay_outbox")
        return moved
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT relay_outbox")
        conn.execute("RELEASE SAVEPOINT relay_outbox")
        raise


def _relay(conn):
    moved = 0
    for row in db.rows(conn, "SELECT * FROM outbox WHERE published_at IS NULL ORDER BY id"):
        publish(conn, row["topic"], json.loads(row["payload"]), row["session_key"])
        conn.execute("UPDATE outbox SET published_at=? WHERE id=?", (db.now(), row["id"]))
        moved += 1
    return moved


def reclaim_expired(conn):
    """Return jobs abandoned by a dead worker to the ready pool.

    Without this, a process killed mid-job leaves a row in 'running' and the
    session-ordering rule then blocks every later job for the same key. This is
    the visibility-timeout that any durable queue needs, and it is the reason a
    crash costs a retry rather than a stuck pipeline.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=LOCK_TIMEOUT_SECONDS)).isoformat(timespec="seconds")
    n = conn.execute(
        "UPDATE work_queue SET status='ready', locked_by=NULL, last_error=? "
        "WHERE status='running' AND (locked_at IS NULL OR locked_at < ?)",
        ("reclaimed: worker lock expired", cutoff),
    ).rowcount
    return n


def _claim(conn, worker_id):
    """Claim one ready job. SKIP LOCKED on Postgres; a short transaction here."""
    reclaim_expired(conn)
    now = db.now()
    row = db.one(
        conn,
        "SELECT * FROM work_queue AS candidate WHERE status='ready' AND run_after<=? "
        "AND (session_key='' OR NOT EXISTS (SELECT 1 FROM work_queue AS active "
        "WHERE active.status='running' AND active.session_key=candidate.session_key)) "
        "ORDER BY id LIMIT 1 " + db.SKIP_LOCKED,
        (now,),
    )
    if not row:
        return None
    # Session ordering: never run two jobs for the same key concurrently.
    busy = db.scalar(
        conn,
        "SELECT COUNT(*) FROM work_queue WHERE status='running' AND session_key=? AND session_key<>''",
        (row["session_key"],),
    )
    if busy:
        return None
    changed = conn.execute(
        "UPDATE work_queue SET status='running', locked_by=?, locked_at=?, attempts=attempts+1 "
        "WHERE id=? AND status='ready' AND (session_key='' OR NOT EXISTS "
        "(SELECT 1 FROM work_queue AS active WHERE active.status='running' "
        "AND active.session_key=work_queue.session_key))",
        (worker_id, now, row["id"]),
    ).rowcount
    return db.one(conn, "SELECT * FROM work_queue WHERE id=?", (row["id"],)) if changed else None


def run_worker(conn, worker_id="w1", max_jobs=500, verbose=True):
    """Drain the queue. Returns (done, dead)."""
    done = dead = 0
    for _ in range(max_jobs):
        relay(conn)
        job = _claim(conn, worker_id)
        if not job:
            break
        handler = HANDLERS.get(job["topic"])
        payload = json.loads(job["payload"])
        if handler is None:
            # No subscription for this topic: the event is delivered nowhere,
            # which is normal on a bus, not a failure.
            conn.execute("UPDATE work_queue SET status='done', last_error=? WHERE id=?",
                         ("no subscriber", job["id"]))
            done += 1          # delivered nowhere is still handled, and the caller needs progress
            if verbose:
                print("  [bus] %-28s no subscriber" % job["topic"])
            continue
        try:
            handler(conn, payload)
            conn.execute("UPDATE work_queue SET status='done' WHERE id=?", (job["id"],))
            done += 1
            if verbose:
                print("  [bus] %-28s ok" % job["topic"])
        except Exception as exc:                      # noqa: BLE001 - boundary
            attempts = job["attempts"]
            if attempts >= MAX_ATTEMPTS:
                conn.execute("UPDATE work_queue SET status='dead', last_error=? WHERE id=?",
                             (repr(exc), job["id"]))
                dead += 1
                print("  [bus] %-28s DEAD after %d attempts: %r" % (job["topic"], attempts, exc))
            else:
                backoff = min(300, 2 ** attempts) * (1 + random.random() * 0.2)
                nxt = (datetime.now(timezone.utc) + timedelta(seconds=backoff)).isoformat(timespec="seconds")
                conn.execute("UPDATE work_queue SET status='ready', run_after=?, last_error=? WHERE id=?",
                             (nxt, repr(exc), job["id"]))
                print("  [bus] %-28s retry %d: %r" % (job["topic"], attempts, exc))
    return done, dead


def depth(conn):
    return {
        "ready": db.scalar(conn, "SELECT COUNT(*) FROM work_queue WHERE status='ready'"),
        "running": db.scalar(conn, "SELECT COUNT(*) FROM work_queue WHERE status='running'"),
        "done": db.scalar(conn, "SELECT COUNT(*) FROM work_queue WHERE status='done'"),
        "dead": db.scalar(conn, "SELECT COUNT(*) FROM work_queue WHERE status='dead'"),
    }
