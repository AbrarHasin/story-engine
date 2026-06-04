"""Direct auth test — bypasses HTTP timeout issues."""
import asyncio
import time

async def main():
    # Test 1: password hashing
    print("=== Test bcrypt hashing ===")
    t0 = time.time()
    from passlib.context import CryptContext
    ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = ctx.hash("testpassword123")
    print(f"Hash took {time.time()-t0:.2f}s: {hashed[:30]}...")

    # Test 2: verify
    t0 = time.time()
    ok = ctx.verify("testpassword123", hashed)
    print(f"Verify took {time.time()-t0:.2f}s: {ok}")

    # Test 3: DB insert
    print("\n=== Test DB insert ===")
    import asyncpg
    conn = await asyncpg.connect(
        host="localhost", port=5432,
        user="storyengine", password="changeme",
        database="storyengine",
    )
    # Check if password_hash column exists
    row = await conn.fetchrow(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name='users' AND column_name='password_hash'"
    )
    print(f"Column exists: {row}")

    # Try inserting a user
    import uuid
    uid = uuid.uuid4()
    try:
        await conn.execute(
            "INSERT INTO users (id, email, name, password_hash, plan, stories_this_month, total_tokens_used, created_at) "
            "VALUES ($1, $2, $3, $4, 'free', 0, 0, NOW())",
            uid, "test2@example.com", "Test2", hashed
        )
        print(f"Inserted user {uid}")

        row = await conn.fetchrow("SELECT id, email, password_hash FROM users WHERE id=$1", uid)
        print(f"Fetched: {row}")

        # Clean up
        await conn.execute("DELETE FROM users WHERE id=$1", uid)
        print("Cleaned up")
    except Exception as e:
        print(f"DB error: {e}")

    await conn.close()

    # Test 4: register via HTTP with longer timeout
    print("\n=== Test register (30s timeout) ===")
    import httpx
    try:
        r = httpx.post("http://localhost:8080/api/v1/auth/register", json={
            "email": "smoketest@example.com",
            "password": "testpassword123",
            "name": "Smoke Test",
        }, timeout=30)
        print(f"Status: {r.status_code}")
        print(f"Body: {r.text[:300]}")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(main())
