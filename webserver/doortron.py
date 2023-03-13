import os
import time
from flask import Flask, render_template, request, redirect
import threading

state = (0, 0)

app = Flask(__name__)

with open("key.txt") as f:
    key = f.read()

@app.route("/")
def index():
    return "good"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

