import os
import time
import json
import numpy as np
from datetime import datetime, timedelta
from quart import Quart, render_template
from quart_cors import cors, route_cors
import asyncio
import logging
from systemd import journal

from viridis import viridis

# state stuff

log = logging.getLogger('doortron_py')
log.addHandler(journal.JournaldLogHandler())
log.setLevel(logging.INFO)

with open("key.json") as f:
    keys = json.load(f)

club_door = None
club_last = datetime.now()
shop_door = None
shop_last = datetime.now()

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
    assert heatmap_raw.shape == (6, 7, 24, 2)
except Exception as e:
    print(f"failed to load heatmap and minutes: {e}")
    print("creating new blank heatmap")
    # 7 days * 24 hours array to track door open minutes
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

        # Run your task
        heatmap_raw = heatmap_raw[1:, :, :, :]
        heatmap_raw = np.concatenate([heatmap_raw, np.zeros(1, 7, 24, 2)])
        

async def task_heatmap():
    """Runs once a minute: if door is open, increment the heatmap bucket."""
    global heatmap_raw
    while True:
        await asyncio.sleep(60)  # wait 1 minute
        now = datetime.now()
        day_idx = now.weekday()   # 0=Monday … 6=Sunday
        hour_idx = now.hour       # 0–23
        if club_door:
            heatmap_raw[-1, day_idx, hour_idx, 0] += 1
        heatmap_raw[-1, day_idx, hour_idx, 1] += 1
        
        try:
            with open("heatmap.npy", "wb") as f:
                np.save(f, heatmap_raw)
        except Exception as e:
            print(f"failed to save heatmap: {e}")

async def task_timeout():
    """Time out state if we haven't been updated in an hour"""
    global club_door, shop_door
    while True:
        await asyncio.sleep(60)
        if datetime.now() - club_last > timedelta(hours=1):
            club_door = None
        if datetime.now() - shop_last > timedelta(hours=1):
            shop_door = None

# webapp stuff

app = Quart(__name__)
app = cors(app)
app.config['CORS_HEADERS'] = 'Content-Type'

@app.route(f"/update/{keys['club']}/<int:state>")
async def update_club(state):
    global club_door, club_last
    club_door = bool(state)
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
    """Expose the heatmap as JSON (7×24)"""
    return heatmap_raw.tolist()

@app.route("/")
async def index():
    # compute heatmap
    heatmap = np.sum(heatmap_raw, axis=0)
    if np.max(heatmap[:, :, 1]) > 0:
        heatmap = np.divide(heatmap[:, :, 0], heatmap[:, :, 1], where=heatmap[:, :, 1]!=0)
        log.info(f"{heatmap.shape}")
        heatmap = (heatmap * 255).astype("u1")
        heatmap = viridis[heatmap]
    else:
        heatmap = np.full((7, 24), viridis[0])

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
