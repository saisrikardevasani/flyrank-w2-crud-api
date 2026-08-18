"""Storage layer. Every SQL string in this project lives in this file.

One connection per call: SQLite opens in microseconds, and a fresh connection per request
keeps uvicorn's worker threads from sharing one cursor.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).with_name("tasks.db")

SEED = [
    {"id": 1, "title": "Read the assignment", "done": True},
    {"id": 2, "title": "Build the CRUD API", "done": False},
    {"id": 3, "title": "Push it to GitHub", "done": False},
]


@contextmanager
def transaction():
    """Yield a connection inside a transaction: commit on success, roll back on any exception."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def to_task(row: sqlite3.Row) -> dict:
    """SQLite has no boolean type, so `done` comes back as 0/1 and turns into a bool here."""
    return {**dict(row), "done": bool(row["done"])}


def migrate(conn) -> None:
    """Add the timestamp columns to a tasks.db made before they existed.

    The column names come from the tuple below, never from a request, so putting them in
    the SQL text is safe. SQLite rejects a non-constant DEFAULT on ALTER TABLE, hence the
    separate UPDATE to fill the rows that are already there.
    """
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)")}
    for column in ("created_at", "updated_at"):
        if column not in existing:
            conn.execute(f"ALTER TABLE tasks ADD COLUMN {column} TEXT")
            conn.execute(f"UPDATE tasks SET {column} = datetime('now')")


def init() -> None:
    """Create the file, the table and the three example rows, each only if they are missing."""
    with transaction() as conn:
        # WAL lets readers carry on while something else is mid-write. Without it, having
        # tasks.db open in DB Browser with unsaved changes makes every GET fail on a lock.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS tasks ("
            " id INTEGER PRIMARY KEY,"
            " title TEXT NOT NULL,"
            " done INTEGER NOT NULL DEFAULT 0,"
            " created_at TEXT NOT NULL DEFAULT (datetime('now')),"
            " updated_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        migrate(conn)
        # Sorting by title reads straight off this index instead of sorting every row.
        conn.execute("CREATE INDEX IF NOT EXISTS tasks_title ON tasks (title)")
        # Seeding is all-or-nothing: three rows or none, never one and a crash.
        if conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO tasks (title, done) VALUES (?, ?)",
                [(t["title"], t["done"]) for t in SEED],
            )
