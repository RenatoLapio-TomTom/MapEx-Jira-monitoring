#!/usr/bin/env python3
"""
collect_jira_data.py

Fetches Backlog and Open issue counts per workgroup from Jira
and appends a new weekly row to data/weekly_snapshots.csv.
"""

import os
import csv
import json
import requests
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

EMAIL    = os.environ["ATLASSIAN_EMAIL"]
TOKEN    = os.environ["ATLASSIAN_API_TOKEN"]
BASE_URL = os.environ["ATLASSIAN_BASE_URL"].rstrip("/")
JIRA_API = f"{BASE_URL}/rest/api/3"

JQL_BACKLOG = 'project = MAPEX AND status = Backlog AND createdDate > "2026-01-01"'
JQL_OPEN    = 'project = MAPEX AND status = Open AND createdDate > "2026-01-01"'

WORKGROUP_FIELD = os.environ.get("WORKGROUP_FIELD", "customfield_10521")
DATA_FILE = Path("data/weekly_snapshots.csv")


def jira_get(jql, fields):
    """Paginate through all Jira issues using POST /rest/api/3/search/jql (Atlassian v3)."""
    auth = (EMAIL, TOKEN)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    # Use POST to /search/jql (preferred by Atlassian, avoids 410 on GET /search)
    url = f"{JIRA_API}/search/jql"
    start = 0
    all_issues = []
    while True:
        payload = {
            "jql": jql,
            "startAt": start,
            "maxResults": 100,
            "fields": fields,
        }
        resp = requests.post(url, auth=auth, headers=headers, data=json.dumps(payload))
        # Fallback: if /search/jql not available, try POST to /search
        if resp.status_code == 404:
            url_fallback = f"{JIRA_API}/search"
            resp = requests.post(url_fallback, auth=auth, headers=headers, data=json.dumps(payload))
        resp.raise_for_status()
        data = resp.json()
        issues = data.get("issues", [])
        all_issues.extend(issues)
        total = data.get("total", 0)
        if start + len(issues) >= total:
            break
        start += 100
    print(f"  Fetched {len(all_issues)} issues for JQL: {jql[:60]}...")
    return all_issues


def extract_workgroup(issue, field):
    val = issue.get("fields", {}).get(field)
    if val is None:
        return "Unassigned"
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("value") or val.get("name") or "Unassigned"
    if isinstance(val, list) and val:
        first = val[0]
        if isinstance(first, dict):
            return first.get("value") or first.get("name") or "Unassigned"
        return str(first)
    return "Unassigned"


def main():
    now = datetime.now(timezone.utc)
    iso_week = now.strftime("%G-W%V")
    date_str = now.strftime("%Y-%m-%d")
    print(f"\n=== Collecting Jira data for {iso_week} ({date_str}) ===")

    fields = ["summary", WORKGROUP_FIELD]
    backlog_issues = jira_get(JQL_BACKLOG, fields)
    open_issues    = jira_get(JQL_OPEN, fields)

    backlog_counts = defaultdict(int)
    open_counts    = defaultdict(int)

    for issue in backlog_issues:
        backlog_counts[extract_workgroup(issue, WORKGROUP_FIELD)] += 1
    for issue in open_issues:
        open_counts[extract_workgroup(issue, WORKGROUP_FIELD)] += 1

    all_workgroups = sorted(set(backlog_counts) | set(open_counts))
    print(f"Workgroups found: {all_workgroups}")
    for wg in all_workgroups:
        print(f"  {wg}: backlog={backlog_counts[wg]}, open={open_counts[wg]}")

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing_rows = []
    if DATA_FILE.exists() and DATA_FILE.stat().st_size > 0:
        with open(DATA_FILE, newline="") as f:
            existing_rows = list(csv.DictReader(f))

    existing_keys = {(r["week"], r["workgroup"]) for r in existing_rows}
    new_rows = [
        {"week": iso_week, "date": date_str, "workgroup": wg,
         "backlog": backlog_counts[wg], "open": open_counts[wg]}
        for wg in all_workgroups
        if (iso_week, wg) not in existing_keys
    ]

    if not new_rows:
        print(f"Data for {iso_week} already recorded. Skipping.")
    else:
        with open(DATA_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["week","date","workgroup","backlog","open"])
            writer.writeheader()
            writer.writerows(existing_rows + new_rows)
        print(f"Appended {len(new_rows)} rows to {DATA_FILE}")

    with open("data/latest_snapshot.json", "w") as f:
        json.dump({
            "week": iso_week, "date": date_str,
            "workgroups": {wg: {"backlog": backlog_counts[wg], "open": open_counts[wg]} for wg in all_workgroups}
        }, f, indent=2)
    print("Written data/latest_snapshot.json")


if __name__ == "__main__":
    main()
