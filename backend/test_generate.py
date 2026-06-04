"""Test story generation endpoint."""
import httpx
import sys

resp = httpx.post(
    "http://localhost:8080/api/v1/stories/generate",
    json={
        "topic": "The future of AI",
        "tonality": "neutral",
        "audience": "general",
        "length": "short",
        "locale": "en",
        "include_light": True,
        "include_dark": True,
        "include_facts": True,
    },
    headers={"Accept": "text/event-stream"},
    timeout=60,
)

print(f"Status: {resp.status_code}")
print(f"Content-Type: {resp.headers.get('content-type')}")
print("---BODY---")
print(resp.text[:2000])
