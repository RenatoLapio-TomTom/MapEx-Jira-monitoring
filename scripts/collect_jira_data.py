#!/usr/bin/env python3
"""
collect_jira_data.py

Fetches BACKLOG, OPEN and CLOSED issue counts per workgroup from Jira
and appends a new weekly row to data/weekly_snapshots.csv.
"""

import os
import csv
import json
import base64
import requests
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

EMAIL    = os.environ["ATLASSIAN_EMAIL"]
TOKEN    = os.environ["ATLASSIAN_API_TOKEN"]
BASE_URL = os.environ["ATLASSIAN_BASE_URL"].rstrip("/")
JIRA_API = f"{BASE_URL}/rest/api/3"

# No date filter — fetch all BACKLOG, OPEN and CLOSED issues in the project
JQL_BACKLOG = 'project = MAPEX AND status = BACKLOG'
JQL_OPEN    = 'project = MAPEX AND status = OPEN'
JQL_CLOSED  = 'project = MAPEX AND status = Closed'

WORKGROUP_FIELD = os.environ.get("WORKGROUP_FIELD", "customfield_10521")
DATA_FILE     = Path("data/weekly_snapshots.csv")
SNAPSHOT_FILE = Path("data/latest_snapshot.json")

# Basic Auth header
_creds = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
AUTH_HEADERS = {
    "Authorization": f"Basic {_creds}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}


def jira_search(jql, fields):
    """Paginate using POST /rest/api/3/search/jql with nextPageToken."""
    url = f"{JIRA_API}/search/jql"
    all_issues = []
    next_page_token = None

    while True:
        payload = {"jql": jql, "maxResults": 100, "fields": fields}
        if next_page_token:
            payload["nextPageToken"] = next_page_token

        resp = requests.post(url, headers=AUTH_HEADERS, data=json.dumps(payload))
        print(f"  POST {url} -> HTTP {resp.status_code}")
        if not resp.ok:
            print(f"  Response body: {resp.text[:500]}")
        resp.raise_for_status()

        data = resp.json()
        issues = data.get("issues", [])
        all_issues.extend(issues)
        print(f"  Got {len(issues)} issues (total so far: {len(all_issues)})")

        next_page_token = data.get("nextPageToken")
        if not next_page_token or len(issues) == 0:
            break

    print(f"  Fetched {len(all_issues)} issues total")
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
    print(f"Jira API base: {JIRA_API}")
    print(f"Workgroup field: {WORKGROUP_FIELD}")

    fields = ["summary", WORKGROUP_FIELD]

    print("\n-- Fetching BACKLOG issues --")
    backlog_issues = jira_search(JQL_BACKLOG, fields)

    print("\n-- Fetching OPEN issues --")
    open_issues = jira_search(JQL_OPEN, fields)

    print("\n-- Fetching CLOSED issues --")
    closed_issues = jira_search(JQL_CLOSED, fields)

    backlog_counts = defaultdict(int)
    open_counts    = defaultdict(int)
    closed_counts  = defaultdict(int)

    for issue in backlog_issues:
        backlog_counts[extract_workgroup(issue, WORKGROUP_FIELD)] += 1
    for issue in open_issues:
        open_counts[extract_workgroup(issue, WORKGROUP_FIELD)] += 1
    for issue in closed_issues:
        closed_counts[extract_workgroup(issue, WORKGROUP_FIELD)] += 1

    all_workgroups = sorted(set(backlog_counts) | set(open_counts) | set(closed_counts))
    print(f"\nWorkgroups found: {all_workgroups}")
    for wg in all_workgroups:
        print(
            f"  {wg}: backlog={backlog_counts[wg]}, open={open_counts[wg]}, closed={closed_counts[wg]}"
        )

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Write latest_snapshot.json first (read by update_confluence.py in same run)
    snapshot = {
        "week": iso_week, "date": date_str,
        "workgroups": {
            wg: {
                "backlog": backlog_counts[wg],
                "open": open_counts[wg],
                "closed": closed_counts[wg],
            }
            for wg in all_workgroups
        },
    }
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"Written {SNAPSHOT_FILE}")

    # Append to weekly CSV
    existing_rows = []
    if DATA_FILE.exists() and DATA_FILE.stat().st_size > 0:
        with open(DATA_FILE, newline="") as f:
            existing_rows = list(csv.DictReader(f))
            for row in existing_rows:
                row["closed"] = row.get("closed") or 0

    existing_keys = {(r["week"], r["workgroup"]) for r in existing_rows}
    new_rows = [
        {"week": iso_week, "date": date_str, "workgroup": wg,
         "backlog": backlog_counts[wg], "open": open_counts[wg], "closed": closed_counts[wg]}
        for wg in all_workgroups
        if (iso_week, wg) not in existing_keys
    ]

    if not new_rows:
        print(f"Data for {iso_week} already recorded in CSV. Skipping append.")
    else:
        with open(DATA_FILE, "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["week", "date", "workgroup", "backlog", "open", "closed"]
            )
            writer.writeheader()
            writer.writerows(existing_rows + new_rows)
        print(f"Appended {len(new_rows)} rows to {DATA_FILE}")


if __name__ == "__main__":
    main()
