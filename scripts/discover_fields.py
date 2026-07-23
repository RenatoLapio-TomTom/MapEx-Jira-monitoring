#!/usr/bin/env python3
"""
discover_fields.py - Run once locally to find the Workgroup custom field ID.

Usage:
  ATLASSIAN_EMAIL=you@example.com \
  ATLASSIAN_API_TOKEN=your_token \
  ATLASSIAN_BASE_URL=https://tomtom.atlassian.net \
  python scripts/discover_fields.py
"""

import os, json, requests

EMAIL    = os.environ["ATLASSIAN_EMAIL"]
TOKEN    = os.environ["ATLASSIAN_API_TOKEN"]
BASE_URL = os.environ["ATLASSIAN_BASE_URL"].rstrip("/")
auth     = (EMAIL, TOKEN)
headers  = {"Accept": "application/json"}

print("\n=== Fields containing 'workgroup' ===")
resp = requests.get(f"{BASE_URL}/rest/api/3/field", auth=auth, headers=headers)
resp.raise_for_status()
fields = resp.json()
matches = [f for f in fields if "workgroup" in f.get("name", "").lower()]
if matches:
    for m in matches:
        print(f"  id={m['id']}  name={m['name']}")
else:
    print("  None found. All custom fields:")
    for c in [f for f in fields if f.get("custom")]:
        print(f"  id={c['id']}  name={c['name']}")

print("\n=== Custom fields on latest MAPEX issue ===")
resp2 = requests.get(f"{BASE_URL}/rest/api/3/search",
    params={"jql": "project=MAPEX ORDER BY created DESC", "maxResults": 1, "fields": "*all"},
    auth=auth, headers=headers)
resp2.raise_for_status()
issues = resp2.json().get("issues", [])
if issues:
    for k, v in sorted(issues[0]["fields"].items()):
        if k.startswith("customfield_") and v:
            print(f"  {k}: {json.dumps(v)[:100]}")
