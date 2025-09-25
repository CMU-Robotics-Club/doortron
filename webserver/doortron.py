import os
import time
import json
import numpy as np
from datetime import datetime
from quart import Quart, render_template
from quart_cors import cors, route_cors
import asyncio

STATE_CLOSED = 0
STATE_OPEN = 1
STATE_ERROR = 2

m_status = (STATE_CLOSED, 0)  # (state, last_updated_timestamp)

COLORS = {
    STATE_CLOSED: "#8b0000",
    STATE_OPEN: "#006400",
    STATE_ERROR: "#444444"
}
STATUS_TEXT1 = {
    STATE_CLOSED: "Roboclub is... ",
    STATE_OPEN: "Roboclub is... ",
    STATE_ERROR: ""
}
STATUS_TEXT2 = {
    STATE_CLOSED: "CLOSED",
    STATE_OPEN: "OPEN",
    STATE_ERROR: ""
}
INFO_TEXT = {
    STATE_CLOSED: "Contact an officer if you would like to get into the club.",
    STATE_OPEN: "This means there's an officer at the club, feel free to drop by :D",
    STATE_ERROR: "The DoorTron system is currently offline, if this persists for more than 5 minutes please notify an officer"
}

SVGS = {}
with open("templates/closed.svg") as f:
    SVGS[STATE_CLOSED] = f.read()
with open("templates/open.svg") as f:
    SVGS[STATE_OPEN] = f.read()
with open("templates/unknown.svg") as f:
    SVGS[STATE_ERROR] = f.read()

app = Quart(__name__)
app = cors(app)
app.config['CORS_HEADERS'] = 'Content-Type'

with open("key.txt") as f:
    THE_KEY = f.read().strip()

# 7×24 array to track door open minutes
door_data = np.zeros((7, 24), dtype=int)

def fmttime(x):
    return datetime.fromtimestamp(x).strftime("%-I:%M %p, %b %-d")

async def background_counter():
    """Runs once a minute: if door is open, increment the heatmap bucket."""
    global door_data
    while True:
        await asyncio.sleep(60)  # wait 1 minute
        state, last_update = m_status
        if state == STATE_OPEN:
            now = datetime.now()
            day_idx = now.weekday()   # 0=Monday … 6=Sunday
            hour_idx = now.hour       # 0–23
            door_data[day_idx, hour_idx] += 1


@app.route(f"/update/{THE_KEY}/0")
async def update0():
    global m_status
    m_status = (STATE_CLOSED, time.time())
    return "OK"

@app.route(f"/update/{THE_KEY}/1")
async def update1():
    """Door open endpoint"""
    global m_status
    m_status = (STATE_OPEN, time.time())
    return "OK"

@app.route("/api")
@route_cors()
async def api():
    state = m_status[0]
    if time.time() - m_status[1] > 600:
        state = STATE_ERROR

    if state == STATE_OPEN:
        state_name = "open"
    elif state == STATE_CLOSED:
        state_name = "closed"
    else:
        state_name = "unknown"

    return json.dumps({"state": state_name})

@app.route("/heatmap")
@route_cors()
async def heatmap():
    """Expose the door_data heatmap as JSON (7×24)"""
    return json.dumps(door_data.tolist())

@app.route("/")
async def index():
    state = m_status[0]
    if time.time() - m_status[1] > 600:
        state = STATE_ERROR
    ts = ("(last updated " + fmttime(m_status[1]) + ")") if state in [STATE_OPEN, STATE_CLOSED] else ""

    return await render_template(
        "index.html",
        color=COLORS[state],
        status_text1=STATUS_TEXT1[state],
        status_text2=STATUS_TEXT2[state],
        time_text=ts,
        info_text=INFO_TEXT[state]
    )

@app.before_serving
async def create_tasks():
    asyncio.create_task(background_counter())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
