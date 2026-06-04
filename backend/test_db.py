"""Quick DB connectivity test."""
import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect(
        host="localhost", port=5432,
        user="storyengine", password="changeme",
        database="storyengine",
    )
    ver = await conn.fetchval("SELECT version()")
    await conn.close()
    print(f"DB_OK: {ver[:60]}")

asyncio.run(main())
