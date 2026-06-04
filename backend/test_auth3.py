"""Auth endpoint test — HTTP only."""
import httpx

BASE = "http://localhost:8080"

# Clean up from previous test
print("=== Register ===")
r = httpx.post(f"{BASE}/api/v1/auth/register", json={
    "email": "smoketest@example.com",
    "password": "testpassword123",
    "name": "Smoke Test",
}, timeout=30)
print(f"Status: {r.status_code}")
print(f"Body: {r.text[:300]}")

if r.status_code in (201, 409):
    print("\n=== Login ===")
    r = httpx.post(f"{BASE}/api/v1/auth/login", json={
        "email": "smoketest@example.com",
        "password": "testpassword123",
    }, timeout=10)
    print(f"Status: {r.status_code}")
    print(f"Body: {r.text[:300]}")

    if r.status_code == 200:
        token = r.json()["access_token"]
        print(f"\n=== /me (with JWT) ===")
        r2 = httpx.get(f"{BASE}/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        print(f"Status: {r2.status_code}")
        print(f"Body: {r2.text[:300]}")

        print(f"\n=== List stories (with JWT) ===")
        r3 = httpx.get(f"{BASE}/api/v1/stories/", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        print(f"Status: {r3.status_code}")
        print(f"Body: {r3.text[:200]}")

print("\n=== Dev fallback (no token) ===")
r = httpx.get(f"{BASE}/api/v1/stories/", timeout=10)
print(f"Status: {r.status_code}")
print(f"Body: {r.text[:200]}")
