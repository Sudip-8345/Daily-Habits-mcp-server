from fastmcp import FastMCP
import os
import asyncio
import aiosqlite
from datetime import date, timedelta

DB_PATH = os.path.join(os.path.dirname(__file__), "habits.db")

mcp = FastMCP("Daily-Habbit")


_db_initialized = False
_db_init_lock: asyncio.Lock | None = None


def _get_db_init_lock() -> asyncio.Lock:
    global _db_init_lock
    if _db_init_lock is None:
        _db_init_lock = asyncio.Lock()
    return _db_init_lock


async def ensure_db_initialized() -> None:
    """Create DB/tables exactly once per process.

    This avoids a race where `fastmcp run/dev` accepts tool calls before the
    background init task completes.
    """
    global _db_initialized
    if _db_initialized:
        return
    async with _get_db_init_lock():
        if _db_initialized:
            return
        await init_db()
        _db_initialized = True


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS habits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS habit_completions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                habit_id INTEGER NOT NULL,
                completion_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (habit_id) REFERENCES habits(id) ON DELETE CASCADE
            )
        """)

        await db.commit()


def _ensure_db_initialized() -> None:
    """
    Ensure DB/tables exist even when this module is imported by `fastmcp dev/run`.
    If an event loop is already running, schedule init; otherwise run it now.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(init_db())
        return

    loop.create_task(init_db())


@mcp.tool()
async def add_habit(name: str, description: str = ""):
    await ensure_db_initialized()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            "INSERT INTO habits (name, description) VALUES (?, ?)",
            (name, description),
        )
        await db.commit()
    return f"Habit '{name}' added successfully."


@mcp.tool()
async def list_habits():
    await ensure_db_initialized()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cursor = await db.execute(
            "SELECT id, name, description, created_at, is_active FROM habits"
        )
        rows = await cursor.fetchall()
        return rows


@mcp.tool()
async def complete_habit(habit_id: int):
    await ensure_db_initialized()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")

        # Validate habit exists (prevents “fake” completions)
        cursor = await db.execute("SELECT 1 FROM habits WHERE id = ?", (habit_id,))
        if await cursor.fetchone() is None:
            return f"Habit {habit_id} does not exist."

        await db.execute(
            "INSERT INTO habit_completions (habit_id) VALUES (?)",
            (habit_id,),
        )
        await db.commit()

    return f"Habit {habit_id} marked as completed for today."


@mcp.tool()
async def list_completions():
    await ensure_db_initialized()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cursor = await db.execute("""
            SELECT hc.id, h.name, hc.completion_date
            FROM habit_completions hc
            JOIN habits h ON hc.habit_id = h.id
            ORDER BY hc.completion_date DESC
        """)
        rows = await cursor.fetchall()
        return rows


@mcp.tool()
async def delete_habit(habit_id: int):
    await ensure_db_initialized()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute("DELETE FROM habits WHERE id = ?", (habit_id,))
        await db.commit()
    return f"Habit {habit_id} deleted successfully."


@mcp.tool()
async def get_current_streak(habit_id: int) -> int:
    """
    Return the current consecutive-day streak for the given habit.
    """
    await ensure_db_initialized()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cursor = await db.execute("""
            SELECT DISTINCT DATE(completion_date) AS day
            FROM habit_completions
            WHERE habit_id = ?
            ORDER BY day DESC
        """, (habit_id,))
        rows = await cursor.fetchall()

    if not rows:
        return 0

    completion_days = {date.fromisoformat(r[0]) for r in rows}
    today = date.today()

    streak = 0
    while True:
        current_day = today - timedelta(days=streak)
        if current_day in completion_days:
            streak += 1
        else:
            break

    return streak


_ensure_db_initialized()

if __name__ == "__main__":
    # For local HTTP testing (Claude Desktop typically uses stdio via `fastmcp run`)
    mcp.run(transport="http", host="0.0.0.0", port=8000)