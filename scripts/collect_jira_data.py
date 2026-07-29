#!/usr/bin/env python3
"""
collect_jira_data.py

Fetches Backlog and Open issue counts per workgroup from Jira
and appends a new weekly row to data/weekly_snapshots.csv.
"""

import os
import csv
import json
import base64
import argparse
import requests
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

EMAIL    = os.environ["ATLASSIAN_EMAIL"]
TOKEN    = os.environ["ATLASSIAN_API_TOKEN"]
BASE_URL = os.environ["ATLASSIAN_BASE_URL"].rstrip("/")
JIRA_API = f"{BASE_URL}/rest/api/3"

WORKGROUP_FIELD = os.environ.get("WORKGROUP_FIELD", "customfield_10521")
DATA_FILE = Path("data/weekly_snapshots.csv")

BACKFILL_DATES = {
    "2026-W28": "2026-07-11",
    "2026-W29": "2026-07-18",
    "2026-W30": "2026-07-25",
    "2026-W31": "2026-08-01",
}

# Basic Auth header
_creds = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
AUTH_HEADERS = {
    "Authorization": f"Basic {_creds}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}


def jira_search(jql, fields):
    """
    Paginate through all Jira issues using POST /rest/api/3/search/jql
    (the new Atlassian Cloud API as of 2025).
    Uses nextPageToken-based pagination as required by the new endpoint.
    """
    url = f"{JIRA_API}/search/jql"
    all_issues = []
    next_page_token = None

    while True:
        payload = {
            "jql": jql,
            "maxResults": 100,
            "fields": fields,
        }
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


def main(backfill_weeks=None):
    if backfill_weeks:
        weeks_to_run = [w.strip() for w in backfill_weeks.split(",")]
        print(f"\n=== Backfill mode: {weeks_to_run} ===")
    else:
        now = datetime.now(timezone.utc)
        iso_week = now.strftime("%G-W%V")
        weeks_to_run = [iso_week]
        print(f"\n=== Collecting Jira data for {iso_week} ===")

    print(f"Jira API base: {JIRA_API}")
    print(f"Workgroup field: {WORKGROUP_FIELD}")

    fields = ["summary", WORKGROUP_FIELD]

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    existing_rows = []
    if DATA_FILE.exists() and DATA_FILE.stat().st_size > 0:
        with open(DATA_FILE, newline="") as f:
            existing_rows = list(csv.DictReader(f))

    all_new_rows = []

    for iso_week in weeks_to_run:
        date_str = BACKFILL_DATES.get(iso_week) if backfill_weeks else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if date_str is None:
            print(f"\nNo backfill date defined for {iso_week}, skipping.")
            continue

        print(f"\n=== Week: {iso_week} | Snapshot date: {date_str} ===")

        if backfill_weeks:
            jql_backlog = f'project = MAPEX AND status WAS "Backlog" ON "{date_str}" AND createdDate > "2026-01-01"'
            jql_open    = f'project = MAPEX AND status WAS "Open" ON "{date_str}" AND createdDate > "2026-01-01"'
        else:
            jql_backlog = 'project = MAPEX AND status = Backlog AND createdDate > "2026-01-01"'
            jql_open    = 'project = MAPEX AND status = Open AND createdDate > "2026-01-01"'

        print("\n-- Fetching BACKLOG issues --")
        backlog_issues = jira_search(jql_backlog, fields)

        print("\n-- Fetching OPEN issues --")
        open_issues = jira_search(jql_open, fields)

        backlog_counts = defaultdict(int)
        open_counts    = defaultdict(int)

        for issue in backlog_issues:
            backlog_counts[extract_workgroup(issue, WORKGROUP_FIELD)] += 1
        for issue in open_issues:
            open_counts[extract_workgroup(issue, WORKGROUP_FIELD)] += 1

        all_workgroups = sorted(set(backlog_counts) | set(open_counts))
        print(f"\nWorkgroups found: {all_workgroups}")
        for wg in all_workgroups:
            print(f"  {wg}: backlog={backlog_counts[wg]}, open={open_counts[wg]}")

        existing_keys = {(r["week"], r["workgroup"]) for r in existing_rows + all_new_rows}
        new_rows = [
            {"week": iso_week, "date": date_str, "workgroup": wg,
             "backlog": backlog_counts[wg], "open": open_counts[wg]}
            for wg in all_workgroups
            if (iso_week, wg) not in existing_keys
        ]

        if not new_rows:
            print(f"\nData for {iso_week} already recorded. Skipping.")
        else:
            all_new_rows.extend(new_rows)
            print(f"\nQueued {len(new_rows)} rows for {iso_week}")

        with open("data/latest_snapshot.json", "w") as f:
            json.dump({
                "week": iso_week, "date": date_str,
                "workgroups": {wg: {"backlog": backlog_counts[wg], "open": open_counts[wg]} for wg in all_workgroups}
            }, f, indent=2)
        print("Written data/latest_snapshot.json")

    if all_new_rows:
        with open(DATA_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["week", "date", "workgroup", "backlog", "open"])
            writer.writeheader()
            writer.writerows(existing_rows + all_new_rows)
        print(f"\nAppended {len(all_new_rows)} rows to {DATA_FILE}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backfill",
        type=str,
        help="Comma-separated ISO week labels e.g. 2026-W28,2026-W29",
    )
    args = parser.parse_args()
    main(backfill_weeks=args.backfill)
