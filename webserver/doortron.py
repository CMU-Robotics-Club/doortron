import os
import time
from flask import Flask, render_template, request, redirect
import threading
from datetime import datetime

STATE_CLOSED = 0
STATE_OPEN = 1
STATE_ERROR = 2

m_status = (STATE_CLOSED, 0) # state, updated

COLORS = {STATE_CLOSED: "#8b0000", STATE_OPEN: "#006400", STATE_ERROR: "#444444"}
STATUS_TEXT1 = {STATE_CLOSED: "Roboclub is... ", STATE_OPEN: "Roboclub is... ", STATE_ERROR: ""}
STATUS_TEXT2 = {STATE_CLOSED: "CLOSED", STATE_OPEN: "OPEN", STATE_ERROR: ""}
INFO_TEXT = {STATE_CLOSED: "Contact an officer if you would like to get into the club.",
             STATE_OPEN: "This means there's an officer at the club, feel free to drop by :)",
             STATE_ERROR: "The DoorTron system is currently offline, if this persists for more than 5 minutes please notify an officer"}

SVGS = {}
with open("templates/closed.svg") as f: SVGS[STATE_CLOSED] = f.read()
with open("templates/open.svg") as f: SVGS[STATE_OPEN] = f.read()
with open("templates/unknown.svg") as f: SVGS[STATE_ERROR] = f.read()

app = Flask(__name__)

with open("key.txt") as f:
    THE_KEY = f.read().strip()

def fmttime(x):
    return datetime.fromtimestamp(x).strftime("%-I:%M %p, %b %-d")

@app.route(f"/update/{THE_KEY}/0")
def update0():
    global m_status
    m_status = (0, time.time())
    return "OK"

@app.route(f"/update/{THE_KEY}/1")
def update1():
    global m_status
    m_status = (1, time.time())
    return "OK"

@app.route("/widget")
def widget():
    state = m_status[0]
    if time.time() - m_status[1] > 600:
        state = STATE_ERROR

    ts = fmttime(m_status[1])

    return render_template("widget.html", the_svg=SVGS[state].replace("__TIMESTAMP__", ts))

@app.route("/")
def index():
    state = m_status[0]
    if time.time() - m_status[1] > 600:
        state = STATE_ERROR

    ts = ("(last updated " + fmttime(m_status[1]) + ")") if state in [STATE_OPEN, STATE_CLOSED] else ""

    return render_template("index.html", color=COLORS[state], status_text1=STATUS_TEXT1[state],
                           status_text2=STATUS_TEXT2[state], time_text=ts, info_text=INFO_TEXT[state])

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

