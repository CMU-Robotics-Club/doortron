import os
import time
import json
import numpy as np
from datetime import datetime, timedelta
from quart import Quart, render_template
from quart_cors import cors, route_cors
import asyncio

# state

door_state = "unknown"
last_updated = datetime.now()
# 7×24 array to track door open minutes
door_data = np.zeros((7, 24), dtype=int)

# webapp stuff

app = Quart(__name__)
app = cors(app)
app.config['CORS_HEADERS'] = 'Content-Type'

with open("key.txt") as f:
    THE_KEY = f.read().strip()


async def task_heatmap():
    """Runs once a minute: if door is open, increment the heatmap bucket."""
    global door_data
    while True:
        await asyncio.sleep(60)  # wait 1 minute
        if door_state == "open":
            now = datetime.now()
            day_idx = now.weekday()   # 0=Monday … 6=Sunday
            hour_idx = now.hour       # 0–23
            door_data[day_idx, hour_idx] += 1

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
async def heatmap():
    """Expose the door_data heatmap as JSON (7×24)"""
    return json.dumps(door_data.tolist())

@app.route("/")
async def index():
    return await render_template(
        "index.html",
        door_state=door_state,
        last_updated=last_updated,
    )

@app.before_serving
async def create_tasks():
    asyncio.create_task(task_heatmap())
    asyncio.create_task(task_timeout())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
