"""Quick auth smoke test."""
import httpx

BASE = "http://localhost:8080"

# Test register
print("=== Register ===")
try:
    r = httpx.post(f"{BASE}/api/v1/auth/register", json={
        "email": "test@example.com",
        "password": "testpassword123",
        "name": "Test User",
    })
    print(f"Status: {r.status_code}")
    print(f"Body: {r.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

# Test login
print("\n=== Login ===")
try:
    r = httpx.post(f"{BASE}/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "testpassword123",
    })
    print(f"Status: {r.status_code}")
    print(f"Body: {r.text[:500]}")

    if r.status_code == 200:
        token = r.json()["access_token"]
        print(f"\n=== /me ===")
        r2 = httpx.get(f"{BASE}/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        print(f"Status: {r2.status_code}")
        print(f"Body: {r2.text[:500]}")
except Exception as e:
    print(f"Error: {e}")

# Test dev fallback (no token)
print("\n=== Dev Fallback (no token) ===")
try:
    r = httpx.get(f"{BASE}/api/v1/stories/", timeout=5)
    print(f"Status: {r.status_code}")
    print(f"Body: {r.text[:200]}")
except Exception as e:
    print(f"Error: {e}")
