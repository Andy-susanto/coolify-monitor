#!/usr/bin/env python3
"""
Uptime Tracker — records resource status transitions to SQLite and computes
uptime percentages over time windows.

Design:
- A background poller calls record_snapshot() with the current status of every
  resource on each tick.
- We only write a row when a resource's up/down state CHANGES (a transition),
  keeping the DB small. The current state is held in memory and also recoverable
  from the last row per resource.
- Uptime % over a window is computed by walking the transition intervals: for
  each resource we know its state at the window start (last transition before it)
  and every change within the window, then sum the "up" duration.
"""

import os
import sqlite3
import threading
import time
from datetime import datetime, timezone

try:
    import paths
    DB_PATH = os.getenv("COOLIFY_DB_FILE", str(paths.db_file()))
except Exception:
    DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uptime.db")

# States considered "up"
_UP_STATES = {"running", "started", "healthy"}


def _now() -> float:
    return time.time()


def _is_up(status: str) -> bool:
    """Normalize a Coolify status string to up/down boolean."""
    if not status:
        return False
    main = status.lower().strip().split(":")[0]
    return main in _UP_STATES


class UptimeTracker:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        # In-memory cache of last known up-state per uuid to detect transitions
        self._last_state = {}
        self._init_db()
        self._load_last_states()

    # ─── DB setup ────────────────────────────────────

    def _conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS status_events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    uuid        TEXT NOT NULL,
                    name        TEXT,
                    type        TEXT,
                    is_up       INTEGER NOT NULL,
                    status      TEXT,
                    ts          REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_uuid_ts ON status_events(uuid, ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON status_events(ts)")
            # Tracks the first time we ever saw a resource (for accurate windows)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS resources (
                    uuid        TEXT PRIMARY KEY,
                    name        TEXT,
                    type        TEXT,
                    first_seen  REAL NOT NULL,
                    last_seen   REAL NOT NULL
                )
            """)

    def _load_last_states(self):
        """Rebuild in-memory last-state cache from the most recent event per uuid."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT e.uuid, e.is_up
                FROM status_events e
                JOIN (
                    SELECT uuid, MAX(ts) AS max_ts
                    FROM status_events GROUP BY uuid
                ) m ON e.uuid = m.uuid AND e.ts = m.max_ts
            """).fetchall()
            for r in rows:
                self._last_state[r["uuid"]] = bool(r["is_up"])

    # ─── Recording ───────────────────────────────────

    def record_snapshot(self, resources: list):
        """
        resources: list of dicts with keys uuid, name, type, status.
        Records a transition row only when up-state changes vs last known.
        """
        ts = _now()
        with self._lock, self._conn() as conn:
            for r in resources:
                uuid = r.get("uuid")
                if not uuid:
                    continue
                name = r.get("name", "")
                rtype = r.get("type", "")
                status = r.get("status", "")
                up = _is_up(status)

                # Upsert resource registry
                conn.execute("""
                    INSERT INTO resources (uuid, name, type, first_seen, last_seen)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(uuid) DO UPDATE SET name=excluded.name,
                        type=excluded.type, last_seen=excluded.last_seen
                """, (uuid, name, rtype, ts, ts))

                prev = self._last_state.get(uuid)
                if prev is None or prev != up:
                    # Transition (or first observation) — record it
                    conn.execute("""
                        INSERT INTO status_events (uuid, name, type, is_up, status, ts)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (uuid, name, rtype, 1 if up else 0, status, ts))
                    self._last_state[uuid] = up

    # ─── Querying ────────────────────────────────────

    def _uptime_for_uuid(self, conn, uuid: str, window_start: float, now: float, first_seen: float):
        """Compute uptime fraction for one resource over [window_start, now]."""
        # Effective start: don't count time before we first saw the resource
        eff_start = max(window_start, first_seen)
        if eff_start >= now:
            return None  # No measurable window yet

        # State at eff_start: last event at or before eff_start
        row = conn.execute("""
            SELECT is_up FROM status_events
            WHERE uuid = ? AND ts <= ?
            ORDER BY ts DESC LIMIT 1
        """, (uuid, eff_start)).fetchone()
        cur_up = bool(row["is_up"]) if row else None

        # Events strictly within (eff_start, now]
        events = conn.execute("""
            SELECT is_up, ts FROM status_events
            WHERE uuid = ? AND ts > ? AND ts <= ?
            ORDER BY ts ASC
        """, (uuid, eff_start, now)).fetchall()

        # If we have no prior state and no events, we can't measure
        if cur_up is None and not events:
            return None
        if cur_up is None:
            # First event defines the initial state for the rest; treat time
            # before the first event as unknown → shrink window to first event
            cur_up = bool(events[0]["is_up"])
            eff_start = events[0]["ts"]
            events = events[1:]

        total = now - eff_start
        if total <= 0:
            return None

        up_dur = 0.0
        last_ts = eff_start
        for ev in events:
            seg = ev["ts"] - last_ts
            if cur_up:
                up_dur += seg
            cur_up = bool(ev["is_up"])
            last_ts = ev["ts"]
        # Final segment to now
        if cur_up:
            up_dur += now - last_ts

        return {
            "uptime_pct": round(100.0 * up_dur / total, 3),
            "measured_seconds": round(total),
            "up_seconds": round(up_dur),
            "down_seconds": round(total - up_dur),
        }

    def get_uptime(self, window_hours: float = 24):
        """Return uptime stats for all known resources over the window."""
        now = _now()
        window_start = now - window_hours * 3600
        results = []
        with self._conn() as conn:
            resources = conn.execute(
                "SELECT uuid, name, type, first_seen, last_seen FROM resources"
            ).fetchall()
            for r in resources:
                stats = self._uptime_for_uuid(conn, r["uuid"], window_start, now, r["first_seen"])
                if stats is None:
                    continue
                # Current state
                cur = self._last_state.get(r["uuid"])
                results.append({
                    "uuid": r["uuid"],
                    "name": r["name"],
                    "type": r["type"],
                    "current_up": cur,
                    "first_seen": r["first_seen"],
                    "last_seen": r["last_seen"],
                    **stats,
                })
        # Sort: worst uptime first (most likely needs attention)
        results.sort(key=lambda x: x["uptime_pct"])
        return results

    def get_events(self, uuid: str, limit: int = 50):
        """Return recent transition events for one resource (newest first)."""
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT is_up, status, ts FROM status_events
                WHERE uuid = ? ORDER BY ts DESC LIMIT ?
            """, (uuid, limit)).fetchall()
            return [{
                "is_up": bool(r["is_up"]),
                "status": r["status"],
                "ts": r["ts"],
                "iso": datetime.fromtimestamp(r["ts"], tz=timezone.utc).isoformat(),
            } for r in rows]

    def prune(self, keep_days: int = 90):
        """Delete events older than keep_days (run occasionally)."""
        cutoff = _now() - keep_days * 86400
        with self._lock, self._conn() as conn:
            conn.execute("DELETE FROM status_events WHERE ts < ?", (cutoff,))


# Singleton
_tracker = None


def get_tracker():
    global _tracker
    if _tracker is None:
        _tracker = UptimeTracker()
    return _tracker
