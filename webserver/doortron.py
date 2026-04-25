import os, os.path
import shutil
import time
import json
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
    if club_last > shop_last:
        return club_last
    return shop_last

# attempt to load persisted heatmap
try:
    with open("heatmap.npy", "rb") as f:
        heatmap_raw = np.load(f).astype("uint32")
    assert heatmap_raw.shape[1:] == (7, 24, 2)
    log.info("loaded persisted heatmap")
except Exception as e:
    log.exception(f"failed to load heatmap: ")
    # back up old heatmap if failed to load
    if os.path.isfile("heatmap.npy"):
        shutil.copy("heatmap.npy", f"heatmap_failed_{time.time()}.npy")
    if os.path.isfile("heatmap_new.npy"):
        shutil.copy("heatmap_new.npy", f"heatmap_new_failed_{time.time()}.npy")

    log.info("creating new blank heatmap")
    # 6 weeks * 7 days * 24 hours * (open, total)
    heatmap_raw = np.zeros((6, 7, 24, 2), dtype="uint32")

# tasks

async def task_roll_heatmap():
    global heatmap_raw
    while True:
        now = datetime.now()
        # Find the next Sunday (weekday=6 for Sunday)
        days_ahead = (6 - now.weekday()) % 7  # how many days until next Sunday
        next_sunday = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)

        # If it's already Sunday midnight, schedule for next week
        if next_sunday <= now:
            next_sunday += timedelta(weeks=1)

        # Compute sleep duration
        sleep_seconds = (next_sunday - now).total_seconds()
        await asyncio.sleep(sleep_seconds)

        # Roll heatmap forward
        heatmap_raw = heatmap_raw[1:, :, :, :]
        heatmap_raw = np.concatenate([heatmap_raw, np.zeros(1, 7, 24, 2)])

        log.info("rolled over heatmap")

        # Note: even though the roll-over won't happen in the case that Doortron is turned off during
        # Sunday midnight, that shouldn't be a problem (in that case one week's table will just contain
        # 2 weeks' worth of data, but it will average out and eventually be cleared the same way)

async def task_heatmap():
    """Runs once a minute: if door is open, increment the heatmap bucket."""
    global heatmap_raw
    while True:
        await asyncio.sleep(60)  # wait 1 minute
        now = datetime.now()
        day_idx = now.weekday()   # 0=Monday … 6=Sunday
        hour_idx = now.hour       # 0–23
        # open minutes
        if club_door:
            heatmap_raw[-1, day_idx, hour_idx, 0] += 1
        # total minutes
        heatmap_raw[-1, day_idx, hour_idx, 1] += 1

        # save heatmap
        try:
            with open("heatmap_new.npy", "wb") as f:
                np.save(f, heatmap_raw)
            shutil.move("heatmap_new.npy", "heatmap.npy")
        except Exception as e:
            log.error(f"failed to save heatmap: {e}")

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
    # compute heatmap
    all_weeks = np.sum(heatmap_raw, axis=0)
    heatmap = np.zeros((7, 24)) # initialize to zeros to avoid uninit
    np.divide(
        all_weeks[:, :, 0], all_weeks[:, :, 1],
        out=heatmap,
        where=all_weeks[:, :, 1] != 0, # when false, use existing value (0)
    )
    heatmap = np.clip(heatmap, 0, 1)

    heatmap = (heatmap * 255).astype("u1")
    heatmap = viridis[heatmap]

    return await render_template(
        "index.html",
        door_state=door_state(),
        last_updated=last_updated(),
        heatmap=heatmap,
        now=datetime.now(),
    )

@app.before_serving
async def create_tasks():
    asyncio.create_task(task_heatmap())
    asyncio.create_task(task_roll_heatmap())
    asyncio.create_task(task_timeout())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
