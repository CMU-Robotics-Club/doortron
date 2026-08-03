import os, os.path
import json
import sqlite3
import time
import numpy as np
from datetime import datetime, timedelta
from quart import Quart, render_template
from quart_cors import cors, route_cors
import asyncio
import logging
import httpx

from viridis import viridis

# logging
log = logging.getLogger('doortron_py')
log.setLevel(logging.INFO)
try:
    from systemd import journal
    log.addHandler(journal.JournaldLogHandler())
except Exception as _:
    pass

# state stuff

with open("key.json") as f:
    keys = json.load(f)

club_door = None
club_last = datetime.now()
shop_door = None
shop_last = datetime.now()

ledtron_api = "http://ledtron.roboclub.org" # E-bench LEDs

STATE_UNKNOWN = 0
STATE_CLOSED = 1
STATE_OPEN = 2

HEATMAP_WEEKS = 6
HEATMAP_SECONDS = HEATMAP_WEEKS * 7 * 24 * 60 * 60
DB_RETENTION_SECONDS = 6 * 30 * 24 * 60 * 60

DB_PATH = "db.sqlite3"

def now_ts():
    return int(time.time())

def ts_to_datetime(ts):
    return datetime.fromtimestamp(ts)

def current_db_state():
    if club_door is None:
        return STATE_UNKNOWN
    if club_door:
        return STATE_OPEN
    return STATE_CLOSED

def next_hour_ts(ts):
    dt = ts_to_datetime(ts)
    next_hour = (dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1))
    return int(next_hour.timestamp())

def door_state():
    if club_door is None:
        return "unknown"
    elif not club_door:
        return "closed"
    elif not shop_door:
        return "open"
    else:
        return "open_shop"

def last_updated():
    updated_ts = db.get_last_updated()
    if updated_ts is not None:
        return ts_to_datetime(updated_ts)
    if club_last > shop_last:
        return club_last
    return shop_last

class DoortronDB:
    def __init__(self, path):
        existed = os.path.exists(path)
        self.conn = sqlite3.connect(path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS door_events (
                ts INTEGER NOT NULL,
                state INTEGER NOT NULL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS door_meta (
                key TEXT PRIMARY KEY,
                value INTEGER NOT NULL
            )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_door_events_ts ON door_events(ts)")
        self.conn.commit()

        startup_ts = now_ts()
        stored_last_updated = self.get_meta("last_updated")
        if existed and stored_last_updated is not None:
            # On init, assume nothing about door state from last db write
            self.insert_event(stored_last_updated, STATE_UNKNOWN)

        self.insert_event(startup_ts, current_db_state())
        self.set_last_updated(startup_ts + 1)

    def get_meta(self, key):
        row = self.conn.execute("SELECT value FROM door_meta WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        return row[0]

    def set_meta(self, key, value):
        self.conn.execute(
            "INSERT INTO door_meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, int(value)),
        )
        self.conn.commit()

    def get_last_updated(self):
        return self.get_meta("last_updated")

    def set_last_updated(self, ts):
        self.set_meta("last_updated", ts)

    def insert_event(self, ts, state):
        self.conn.execute(
            "INSERT INTO door_events(ts, state) VALUES(?, ?)",
            (int(ts), int(state)),
        )
        self.conn.commit()
        self.last_insert_ts = int(ts)
        self.last_insert_state = int(state)

    def persist_current_state(self, ts, state):
        if (
            self.last_insert_ts is None
            or self.last_insert_state != state
            # Add at least one record every hour, even if unchanged
            or ts - self.last_insert_ts > 60 * 60
        ):
            self.insert_event(ts, state)
        # last_updated is ts+1, to prevent unknown record from startup having same timestamp as another door event
        self.set_last_updated(ts+1)

    def cleanup(self, cutoff_ts):
        self.conn.execute("DELETE FROM door_events WHERE ts < ?", (int(cutoff_ts),))
        self.conn.commit()

    def heatmap_events(self, cutoff_ts):
        # door state at the start of the window
        prior = self.conn.execute(
            "SELECT ts, state FROM door_events WHERE ts < ? ORDER BY ts DESC, rowid DESC LIMIT 1",
            (int(cutoff_ts),),
        ).fetchone()
        events = self.conn.execute(
            "SELECT ts, state FROM door_events WHERE ts >= ? ORDER BY ts ASC, rowid ASC",
            (int(cutoff_ts),),
        ).fetchall()
        return prior, events

db = DoortronDB(DB_PATH)
heatmap_raw = np.zeros((HEATMAP_WEEKS, 7, 24, 2), dtype="uint32")
heatmap_colors = viridis[np.zeros((7, 24), dtype="u1")]
uptime_percent = 0.0

# tasks

def add_heatmap_interval(raw, start_ts, end_ts, state, window_start_ts):
    if state == STATE_UNKNOWN or end_ts <= start_ts:
        return

    current_ts = start_ts
    while current_ts < end_ts:
        dt = ts_to_datetime(current_ts)
        bucket_end_ts = min(end_ts, next_hour_ts(current_ts))
        week_idx = int((current_ts - window_start_ts) // (7 * 24 * 60 * 60))
        if 0 <= week_idx < HEATMAP_WEEKS:
            day_idx = dt.weekday()
            hour_idx = dt.hour
            seconds = bucket_end_ts - current_ts
            if state == STATE_OPEN:
                raw[week_idx, day_idx, hour_idx, 0] += seconds
            if state in (STATE_OPEN, STATE_CLOSED):
                raw[week_idx, day_idx, hour_idx, 1] += seconds
        current_ts = bucket_end_ts

def compute_heatmap():
    global heatmap_raw, heatmap_colors, uptime_percent

    end_ts = now_ts()
    window_start_ts = end_ts - HEATMAP_SECONDS
    new_heatmap_raw = np.zeros((HEATMAP_WEEKS, 7, 24, 2), dtype="uint32")
    prior, events = db.heatmap_events(window_start_ts)

    state = STATE_UNKNOWN if prior is None else prior[1]
    interval_start = window_start_ts

    for event_ts, event_state in events:
        clamped_event_ts = min(max(event_ts, window_start_ts), end_ts)
        add_heatmap_interval(new_heatmap_raw, interval_start, clamped_event_ts, state, window_start_ts)
        interval_start = clamped_event_ts
        state = event_state

    add_heatmap_interval(new_heatmap_raw, interval_start, end_ts, state, window_start_ts)

    all_weeks = np.sum(new_heatmap_raw, axis=0)
    heatmap = np.zeros((7, 24)) # initialize to zeros to avoid uninit
    np.divide(
        all_weeks[:, :, 0], all_weeks[:, :, 1],
        out=heatmap,
        where=all_weeks[:, :, 1] != 0, # when false, use existing value (0)
    )
    heatmap = np.clip(heatmap, 0, 1)

    heatmap_raw = new_heatmap_raw
    heatmap_colors = viridis[(heatmap * 255).astype("u1")]

    # unknown time is never recorded in either slot, so known/window == 1 - unknown/window
    known_seconds = int(new_heatmap_raw[:, :, :, 1].sum())
    uptime_percent = 100.0 * known_seconds / HEATMAP_SECONDS

async def task_persist_state():
    while True:
        await asyncio.sleep(60)
        ts = now_ts()
        try:
            db.persist_current_state(ts, current_db_state())
            db.cleanup(ts - DB_RETENTION_SECONDS)
        except Exception as e:
            log.error(f"failed to persist door state: {e}")

async def task_heatmap():
    while True:
        await asyncio.sleep(5 * 60)
        try:
            compute_heatmap()
        except Exception as e:
            log.error(f"failed to compute heatmap: {e}")

async def task_timeout():
    """Time out state if we haven't been updated in an hour"""
    global club_door, shop_door
    while True:
        await asyncio.sleep(60)
        if datetime.now() - club_last > timedelta(hours=1):
            log.warning("club door timed out!")
            club_door = None
        if datetime.now() - shop_last > timedelta(hours=1):
            log.warning("shop door timed out!")
            shop_door = None

"""Update E-bench LEDs"""
"""state: T=? (1=on, 0=off), PL=? (? is the preset number)"""
async def update_ledtron(state):
    global ledtron_api
    suffix = "win&T=1&PL=1" if state else "win&T=0"
    url = f"{ledtron_api}/{suffix}"
    try:
        async with httpx.AsyncClient() as client:
            await client.get(url, timeout=2.0)
    except Exception as e:
        log.error(f"LEDtron update failed: {e}")

# webapp stuff

app = Quart(__name__)
app = cors(app)
app.config['CORS_HEADERS'] = 'Content-Type'

@app.route(f"/update/{keys['club']}/<int:state>")
async def update_club(state):
    global club_door, club_last
    new_state = bool(state)
    if club_door != new_state:
        asyncio.create_task(update_ledtron(new_state))
    club_door = new_state
    club_last = datetime.now()
    return "OK"

@app.route(f"/update/{keys['shop']}/<int:state>")
async def update_shop(state):
    global shop_door, shop_last
    shop_door = bool(state)
    shop_last = datetime.now()
    return "OK"

@app.route("/api")
@route_cors()
async def api():
    return {"state": door_state()}

@app.route("/heatmap")
@route_cors()
async def get_heatmap():
    """Expose the full heatmap as JSON"""
    return heatmap_raw.tolist()

@app.route("/")
async def index():
    return await render_template(
        "index.html",
        door_state=door_state(),
        last_updated=last_updated(),
        heatmap=heatmap_colors,
        uptime=f"{uptime_percent:.3f}",
        now=datetime.now(),
    )

@app.before_serving
async def create_tasks():
    compute_heatmap()
    asyncio.create_task(task_persist_state())
    asyncio.create_task(task_heatmap())
    asyncio.create_task(task_timeout())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
