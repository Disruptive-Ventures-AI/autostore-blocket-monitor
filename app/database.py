import aiosqlite
from datetime import datetime, timezone

from app.config import DATABASE_PATH

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS seen_ads (
    ad_id TEXT PRIMARY KEY,
    first_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scraped_at TEXT NOT NULL,
    ad_id TEXT NOT NULL,
    car_title TEXT,
    make TEXT,
    year INTEGER,
    mileage_raw TEXT,
    mileage_km INTEGER,
    price_sek INTEGER,
    fuel TEXT,
    gearbox TEXT,
    location TEXT,
    ad_url TEXT
);

CREATE TABLE IF NOT EXISTS run_state (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init_db() -> None:
    db = await get_db()
    try:
        await db.executescript(_CREATE_TABLES)
        await db.commit()
    finally:
        await db.close()


async def get_seen_ad_ids() -> set[str]:
    db = await get_db()
    try:
        cursor = await db.execute("SELECT ad_id FROM seen_ads")
        rows = await cursor.fetchall()
        return {row["ad_id"] for row in rows}
    finally:
        await db.close()


async def write_seen_ads(ad_ids: list[str]) -> None:
    if not ad_ids:
        return
    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    try:
        await db.executemany(
            "INSERT OR IGNORE INTO seen_ads (ad_id, first_seen) VALUES (?, ?)",
            [(aid, now) for aid in ad_ids],
        )
        await db.commit()
    finally:
        await db.close()


async def write_price_history(cars: list) -> None:
    if not cars:
        return
    now = datetime.now(timezone.utc).isoformat()
    db = await get_db()
    try:
        await db.executemany(
            """INSERT INTO price_history
               (scraped_at, ad_id, car_title, make, year, mileage_raw,
                mileage_km, price_sek, fuel, gearbox, location, ad_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    now,
                    c.ad_id,
                    c.car_title,
                    c.make,
                    c.year,
                    c.mileage_raw,
                    c.mileage_km,
                    c.price,
                    c.fuel,
                    c.gearbox,
                    c.location,
                    c.url,
                )
                for c in cars
            ],
        )
        await db.commit()
    finally:
        await db.close()


async def get_run_state(key: str) -> str | None:
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT value FROM run_state WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row["value"] if row else None
    finally:
        await db.close()


async def set_run_state(key: str, value: str) -> None:
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO run_state (key, value) VALUES (?, ?)",
            (key, value),
        )
        await db.commit()
    finally:
        await db.close()
