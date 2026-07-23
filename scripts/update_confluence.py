#!/usr/bin/env python3
"""
update_confluence.py

Reads latest_snapshot.json and weekly_snapshots.csv, then creates/updates
one Confluence page per workgroup with a stacked bar chart image (via QuickChart.io)
showing weekly Backlog + Open trends.
"""

import os
import csv
import json
import base64
import urllib.parse
import requests
from collections import defaultdict
from pathlib import Path

EMAIL     = os.environ["ATLASSIAN_EMAIL"]
TOKEN     = os.environ["ATLASSIAN_API_TOKEN"]
BASE_URL  = os.environ["ATLASSIAN_BASE_URL"].rstrip("/")
SPACE_KEY = os.environ["CONFLUENCE_SPACE_KEY"]

CONF_API      = f"{BASE_URL}/wiki/rest/api"
DATA_FILE     = Path("data/weekly_snapshots.csv")
SNAPSHOT_FILE = Path("data/latest_snapshot.json")
INDEX_TITLE   = "MAPEX Jira Workgroup Trends"

_creds = base64.b64encode(f"{EMAIL}:{TOKEN}".encode()).decode()
HEADERS = {
    "Authorization": f"Basic {_creds}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}


def get_page(title):
    resp = requests.get(f"{CONF_API}/content",
        params={"spaceKey": SPACE_KEY, "title": title, "expand": "version"},
        headers=HEADERS)
    print(f"  GET content '{title}' -> HTTP {resp.status_code}")
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0] if results else None


def create_page(title, body_html, parent_id=None):
    payload = {
        "type": "page", "title": title,
        "space": {"key": SPACE_KEY},
        "body": {"storage": {"value": body_html, "representation": "storage"}},
    }
    if parent_id:
        payload["ancestors"] = [{"id": parent_id}]
    resp = requests.post(f"{CONF_API}/content", headers=HEADERS, data=json.dumps(payload))
    print(f"  POST content '{title}' -> HTTP {resp.status_code}")
    if not resp.ok:
        print(f"  Response: {resp.text[:300]}")
    resp.raise_for_status()
    return resp.json()


def update_page(page_id, version, title, body_html):
    payload = {
        "type": "page", "title": title,
        "version": {"number": version + 1},
        "body": {"storage": {"value": body_html, "representation": "storage"}},
    }
    resp = requests.put(f"{CONF_API}/content/{page_id}", headers=HEADERS, data=json.dumps(payload))
    print(f"  PUT content '{title}' -> HTTP {resp.status_code}")
    if not resp.ok:
        print(f"  Response: {resp.text[:300]}")
    resp.raise_for_status()
    return resp.json()


def upsert_page(title, body_html, parent_id=None):
    existing = get_page(title)
    if existing:
        result = update_page(existing["id"], existing["version"]["number"], title, body_html)
        print(f"  Updated: '{title}'")
        return result
    else:
        result = create_page(title, body_html, parent_id)
        print(f"  Created: '{title}'")
        return result


def build_quickchart_url(workgroup, weeks, backlog_vals, open_vals):
    """Build a QuickChart.io URL for a stacked bar chart."""
    chart_config = {
        "type": "bar",
        "data": {
            "labels": weeks,
            "datasets": [
                {
                    "label": "Backlog",
                    "data": backlog_vals,
                    "backgroundColor": "#FF8C00",
                },
                {
                    "label": "Open",
                    "data": open_vals,
                    "backgroundColor": "#1F7BC0",
                },
            ],
        },
        "options": {
            "title": {
                "display": True,
                "text": f"{workgroup} - Weekly BACKLOG & OPEN Trend",
            },
            "scales": {
                "xAxes": [{"stacked": True}],
                "yAxes": [{"stacked": True, "ticks": {"beginAtZero": True}}],
            },
            "legend": {"position": "bottom"},
        },
    }
    chart_json = json.dumps(chart_config, separators=(",", ":"))
    encoded = urllib.parse.quote(chart_json)
    return f"https://quickchart.io/chart?c={encoded}&width=800&height=400&backgroundColor=white"


def build_page_html(workgroup, weeks, backlog_vals, open_vals):
    chart_url = build_quickchart_url(workgroup, weeks, backlog_vals, open_vals)

    raw_rows = "".join(
        f"<tr><td>{w}</td><td>{backlog_vals[i]}</td><td>{open_vals[i]}</td>"
        f"<td><strong>{backlog_vals[i] + open_vals[i]}</strong></td></tr>"
        for i, w in enumerate(weeks)
    )

    return f"""
<p>Auto-updated every Saturday by <a href="https://github.com/RenatoLapio-TomTom/MapEx-Jira-monitoring">MapEx Jira Monitoring</a>.<br/>
<em>MAPEX issues with BACKLOG or OPEN status. Each bar = one week, stacked: orange = Backlog, blue = Open.</em></p>
<h2>Trend Chart</h2>
<p><ac:image ac:width="800"><ri:url ri:value="{chart_url}" /></ac:image></p>
<h2>Raw Data</h2>
<table><tbody>
<tr><th>Week</th><th>Backlog</th><th>Open</th><th>Total</th></tr>
{raw_rows}
</tbody></table>
"""


def main():
    print(f"\n=== Updating Confluence (space: {SPACE_KEY}) ===")
    print(f"Confluence API: {CONF_API}")

    wg_data = defaultdict(dict)
    if DATA_FILE.exists() and DATA_FILE.stat().st_size > 0:
        with open(DATA_FILE, newline="") as f:
            for row in csv.DictReader(f):
                wg_data[row["workgroup"]][row["week"]] = {
                    "backlog": int(row["backlog"]), "open": int(row["open"])
                }
        print(f"Loaded historical data from {DATA_FILE}")

    if not SNAPSHOT_FILE.exists():
        print(f"ERROR: {SNAPSHOT_FILE} not found.")
        raise SystemExit(1)

    with open(SNAPSHOT_FILE) as f:
        snapshot = json.load(f)

    iso_week = snapshot["week"]
    for wg, counts in snapshot["workgroups"].items():
        wg_data[wg][iso_week] = counts

    workgroups = sorted(wg_data.keys())
    print(f"Workgroups: {workgroups}")

    if not workgroups:
        print("No workgroups found — nothing to publish.")
        return

    # Index page
    index_html = "<p>Auto-generated index of MAPEX workgroup trend pages.</p><ul>" + \
        "".join(f'<li><ac:link><ri:page ri:content-title="{wg} - MAPEX Trend" /></ac:link></li>' for wg in workgroups) + \
        "</ul>"
    index_page = upsert_page(INDEX_TITLE, index_html)
    index_id = index_page.get("id") or get_page(INDEX_TITLE)["id"]

    # One page per workgroup
    for wg in workgroups:
        weeks = sorted(wg_data[wg].keys())
        backlog_vals = [wg_data[wg][w]["backlog"] for w in weeks]
        open_vals    = [wg_data[wg][w]["open"]    for w in weeks]
        upsert_page(f"{wg} - MAPEX Trend",
                    build_page_html(wg, weeks, backlog_vals, open_vals),
                    parent_id=index_id)

    print("\nAll Confluence pages updated successfully.")


if __name__ == "__main__":
    main()
