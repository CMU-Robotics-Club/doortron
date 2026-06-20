#!/usr/bin/env python3

import argparse
import sqlite3
import sys
import time
from datetime import datetime, timedelta

import numpy as np


STATE_UNKNOWN = 0
STATE_CLOSED = 1
STATE_OPEN = 2

HEATMAP_WEEKS = 6
HEATMAP_SECONDS = HEATMAP_WEEKS * 7 * 24 * 60 * 60
DEFAULT_DB_PATH = "db.sqlite3"


def now_ts():
    return int(time.time())


def load_heatmap(path):
    with open(path, "rb") as f:
        heatmap = np.load(f)

    if heatmap.shape != (HEATMAP_WEEKS, 7, 24, 2):
        raise ValueError(f"expected heatmap shape {(HEATMAP_WEEKS, 7, 24, 2)}, got {heatmap.shape}")

    heatmap = heatmap.astype("uint32", copy=False)
    if np.any(heatmap[:, :, :, 0] > heatmap[:, :, :, 1]):
        raise ValueError("legacy heatmap has open counts larger than total counts")

    return heatmap


def setup_db(path, reset):
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS door_events (
            ts INTEGER NOT NULL,
            state INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS door_meta (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_door_events_ts ON door_events(ts)")
    if reset:
        conn.execute("DELETE FROM door_events")
        conn.execute("DELETE FROM door_meta")
    conn.commit()
    return conn


def insert_event(conn, ts, state):
    conn.execute(
        "INSERT INTO door_events(ts, state) VALUES(?, ?)",
        (int(ts), int(state)),
    )


def set_last_updated(conn, ts):
    conn.execute(
        "INSERT INTO door_meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        ("last_updated", int(ts)),
    )


def window_start_ts(anchor_end_ts):
    end_dt = datetime.fromtimestamp(anchor_end_ts).replace(hour=0, minute=0, second=0, microsecond=0)
    days_since_sunday = (end_dt.weekday() + 1) % 7
    start_dt = end_dt - timedelta(weeks=HEATMAP_WEEKS, days=days_since_sunday)
    return int(start_dt.timestamp())


def first_weekday_occurrence_ts(anchor_end_ts, day_idx):
    start_dt = datetime.fromtimestamp(window_start_ts(anchor_end_ts))
    weekday_delta = (day_idx - start_dt.weekday()) % 7
    return int((start_dt + timedelta(days=weekday_delta)).timestamp())


def import_heatmap(conn, heatmap, anchor_end_ts):
    for week_idx in range(HEATMAP_WEEKS):
        for day_idx in range(7):
            day_base_ts = first_weekday_occurrence_ts(anchor_end_ts, day_idx) + week_idx * 7 * 24 * 60 * 60
            for hour_idx in range(24):
                open_seconds = int(heatmap[week_idx, day_idx, hour_idx, 0])
                total_seconds = int(heatmap[week_idx, day_idx, hour_idx, 1])

                if total_seconds == 0:
                    continue

                bucket_start_ts = day_base_ts + hour_idx * 60 * 60
                bucket_end_ts = bucket_start_ts + total_seconds

                if open_seconds <= 0:
                    insert_event(conn, bucket_start_ts, STATE_CLOSED)
                    insert_event(conn, bucket_end_ts, STATE_UNKNOWN)
                    continue

                if open_seconds >= total_seconds:
                    insert_event(conn, bucket_start_ts, STATE_OPEN)
                    insert_event(conn, bucket_end_ts, STATE_UNKNOWN)
                else:
                    closed_seconds = total_seconds - open_seconds
                    insert_event(conn, bucket_start_ts, STATE_CLOSED)
                    insert_event(conn, bucket_start_ts + closed_seconds, STATE_OPEN)
                    insert_event(conn, bucket_end_ts, STATE_UNKNOWN)

    set_last_updated(conn, anchor_end_ts + 1)
    conn.commit()


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Import a legacy doortron heatmap.npy into the SQLite event database."
    )
    parser.add_argument("heatmap_npy", help="path to the legacy heatmap .npy file")
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help=f"SQLite database path (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--anchor-end",
        type=int,
        default=now_ts(),
        help="unix timestamp used as the end of the 6-week import window (default: now)",
    )
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="append to the existing DB instead of clearing door_events and door_meta first",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])

    heatmap = load_heatmap(args.heatmap_npy)
    conn = setup_db(args.db, reset=not args.no_reset)
    try:
        import_heatmap(conn, heatmap, args.anchor_end)
    finally:
        conn.close()

    print(f"imported {args.heatmap_npy} into {args.db}")


if __name__ == "__main__":
    main()
