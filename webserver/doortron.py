import os
import time
import json
import numpy as np
from datetime import datetime, timedelta
from quart import Quart, render_template
from quart_cors import cors, route_cors
import asyncio

# state

with open("key.txt") as f:
    THE_KEY = f.read().strip()

door_state = "unknown"
last_updated = datetime.now()
# attempt to load persisted heatmap
try:
    with open("heatmap.npy", "rb") as f:
        heatmap_raw = np.load(f).astype("uint64")
    assert heatmap_raw.shape == (7, 24)
except Exception as e:
    print(f"failed to load heatmap: {e}")
    print("creating new blank heatmap")
    # 7×24 array to track door open minutes
    heatmap_raw = np.zeros((7, 24), dtype="uint64")

# webapp stuff

app = Quart(__name__)
app = cors(app)
app.config['CORS_HEADERS'] = 'Content-Type'


async def task_heatmap():
    """Runs once a minute: if door is open, increment the heatmap bucket."""
    global heatmap_raw
    while True:
        await asyncio.sleep(60)  # wait 1 minute
        if door_state == "open":
            now = datetime.now()
            day_idx = now.weekday()   # 0=Monday … 6=Sunday
            hour_idx = now.hour       # 0–23
            heatmap_raw[day_idx, hour_idx] += 1
        try:
            with open("heatmap.npy", "wb") as f:
                np.save(f, heatmap_raw)
        except Exception as e:
            print(f"failed to save heatmap: {e}")

async def task_timeout():
    """Time out state if we haven't been updated in an hour"""
    global door_state, last_updated
    while True:
        await asyncio.sleep(60)
        if datetime.now() - last_updated > timedelta(hours=1):
            door_state = "unknown"


@app.route(f"/update/{THE_KEY}/<int:state>")
async def update(state):
    global door_state, last_updated
    door_state = "closed" if state == 0 else "open"
    last_updated = datetime.now()
    return "OK"

@app.route("/api")
@route_cors()
async def api():
    return json.dumps({"state": door_state})

@app.route("/heatmap")
@route_cors()
async def get_heatmap():
    """Expose the heatmap heatmap as JSON (7×24)"""
    return json.dumps(heatmap.tolist())

@app.route("/")
async def index():
    # compute heatmap
    heatmap = heatmap_raw
    maxpt = np.max(heatmap_raw)
    if maxpt > 0:
        heatmap = (heatmap_raw / maxpt * 255).astype("u1")

    return await render_template(
        "index.html",
        door_state=door_state,
        last_updated=last_updated,
        heatmap=heatmap,
        now=datetime.now(),
    )

@app.before_serving
async def create_tasks():
    asyncio.create_task(task_heatmap())
    asyncio.create_task(task_timeout())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
