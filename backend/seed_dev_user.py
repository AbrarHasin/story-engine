"""Seed the dev user that the backend expects."""
import asyncio
import asyncpg

async def main():
    conn = await asyncpg.connect(
        host="localhost", port=5432,
        user="storyengine", password="changeme",
        database="storyengine",
    )
    await conn.execute("""
        INSERT INTO users (id, email, name, plan, stories_this_month, total_tokens_used, created_at)
        VALUES ('00000000-0000-0000-0000-000000000001', 'dev@storyengine.local', 'Dev User', 'free', 0, 0, NOW())
        ON CONFLICT (id) DO NOTHING
    """)
    row = await conn.fetchrow("SELECT id, email, plan FROM users WHERE id = '00000000-0000-0000-0000-000000000001'")
    await conn.close()
    print(f"USER_OK: {row}")

asyncio.run(main())
