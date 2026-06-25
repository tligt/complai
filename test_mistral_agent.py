"""
Standalone test — run this via GitHub Actions to see the raw
Conversations API response in the Actions log.

Add to .github/workflows/test_agent.yml and trigger manually.
"""
import os
import json
import requests

api_key  = os.environ.get("MISTRAL_API_KEY", "")
agent_id = os.environ.get("MISTRAL_AGENT_ID", "ag_019efe92f08e71a78d70f0f8b9230d29")

print(f"API key present: {bool(api_key)}")
print(f"Agent ID: {agent_id}")

resp = requests.post(
    "https://api.mistral.ai/v1/conversations",
    headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    },
    json={
        "agent_id": agent_id,
        "inputs":   "Find 3 recent GDPR news articles from this week.",
    },
    timeout=90,
)

print(f"\nHTTP status: {resp.status_code}")
print(f"\nFull response:")
print(json.dumps(resp.json(), indent=2))
