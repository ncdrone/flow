#!/usr/bin/env python3
"""Check for raw ideas in the Personal X Pipeline and notify Metis."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (one level up from scripts/)
load_dotenv(Path(__file__).parent.parent / ".env")

DB_PATH = os.environ.get(
    "FLOW_DB_PATH",
    str(Path(__file__).parent.parent / "pipeline.db")  # sensible default
)


def get_raw_ideas():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM ideas WHERE status = 'raw' ORDER BY created_at ASC")
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows]
    except sqlite3.Error as e:
        print(f"[check_raw_ideas] DB error: {e}", file=sys.stderr)
        sys.exit(1)


def notify(idea_ids):
    ids_str = ", ".join(str(i) for i in idea_ids)
    message = f"RAW_IDEAS_FOUND\nidea_ids: [{ids_str}]\ncount: {len(idea_ids)}"
    subprocess.run(
        ["openclaw", "sessions", "send", "--label", "main", "--message", message],
        check=True,
    )


def main():
    idea_ids = get_raw_ideas()
    if not idea_ids:
        sys.exit(0)  # Silent exit — nothing to report
    notify(idea_ids)


if __name__ == "__main__":
    main()
