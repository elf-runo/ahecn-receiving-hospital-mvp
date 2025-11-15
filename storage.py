# storage.py
import sqlite3, json, time
import streamlit as st

@st.cache_resource
def get_db():
    conn = sqlite3.connect("ahecn_events.db", check_same_thread=False)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS events(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts REAL,
        type TEXT,
        case_id TEXT,
        actor TEXT,
        payload TEXT
      )
    """)
    conn.commit()
    return conn

def publish_event(etype: str, case_id: str, actor: str, payload: dict | None = None) -> int:
    """Append an event; returns last row id."""
    conn = get_db()
    conn.execute(
        "INSERT INTO events(ts,type,case_id,actor,payload) VALUES(?,?,?,?,?)",
        (time.time(), etype, case_id, actor, json.dumps(payload or {}, ensure_ascii=False))
    )
    conn.commit()
    rid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return rid

def poll_events_since(last_id: int = 0, case_id: str | None = None, limit: int = 200):
    """Fetch events > last_id (optionally for one case_id)."""
    conn = get_db()
    if case_id:
        rows = conn.execute(
            """SELECT id,ts,type,case_id,actor,payload
               FROM events WHERE id>? AND case_id=? ORDER BY id ASC LIMIT ?""",
            (last_id, case_id, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT id,ts,type,case_id,actor,payload
               FROM events WHERE id>? ORDER BY id ASC LIMIT ?""",
            (last_id, limit)
        ).fetchall()
    out = []
    for (eid, ts, etype, cid, actor, payload) in rows:
        try:
            data = json.loads(payload) if payload else {}
        except Exception:
            data = {}
        out.append(dict(id=eid, ts=ts, type=etype, case_id=cid, actor=actor, payload=data))
    return out
