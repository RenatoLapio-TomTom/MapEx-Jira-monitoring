#!/usr/bin/env python3
"""
update_confluence.py

Reads latest_snapshot.json (written by collect_jira_data.py in the same run)
and creates/updates one Confluence page per workgroup with a stacked bar chart
showing weekly Backlog + Open trends (one bar per week, two colors stacked).
"""

import os
import csv
import json
import base64
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
    if not resp.ok:
        print(f"  Response: {resp.text[:300]}")
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


def build_chart_html(workgroup, weeks, backlog_vals, open_vals):
    """
    Stacked bar chart: one bar per week on the X axis,
    two stacked series (Backlog=orange, Open=blue).

    The Confluence chart macro expects:
    - Row 1: header with series names  -> Week | Backlog | Open
    - Row N: one data row per X-axis category (week)
    """
    # Data rows: one per week (X axis category)
    data_rows = "".join(
        f"<tr><td>{w}</td><td>{backlog_vals[i]}</td><td>{open_vals[i]}</td></tr>"
        for i, w in enumerate(weeks)
    )

    chart_macro = f"""
<ac:structured-macro ac:name="chart" ac:schema-version="1">
  <ac:parameter ac:name="type">bar</ac:parameter>
  <ac:parameter ac:name="stacked">true</ac:parameter>
  <ac:parameter ac:name="title">{workgroup} - Weekly BACKLOG &amp; OPEN Trend</ac:parameter>
  <ac:parameter ac:name="width">800</ac:parameter>
  <ac:parameter ac:name="height">400</ac:parameter>
  <ac:parameter ac:name="colors">#FF8C00,#1F7BC0</ac:parameter>
  <ac:parameter ac:name="domainAxisLabel">Week</ac:parameter>
  <ac:parameter ac:name="rangeAxisLabel">Issue Count</ac:parameter>
  <ac:parameter ac:name="orientation">vertical</ac:parameter>
  <ac:rich-text-body>
    <table><tbody>
      <tr><th>Week</th><th>Backlog</th><th>Open</th></tr>
      {data_rows}
    </tbody></table>
  </ac:rich-text-body>
</ac:structured-macro>"""

    # Raw data table below the chart
    raw_rows = "".join(
        f"<tr><td>{w}</td><td>{backlog_vals[i]}</td><td>{open_vals[i]}</td><td><strong>{backlog_vals[i]+open_vals[i]}</strong></td></tr>"
        for i, w in enumerate(weeks)
    )

    return f"""
<p>Auto-updated every Saturday by <a href="https://github.com/RenatoLapio-TomTom/MapEx-Jira-monitoring">MapEx Jira Monitoring</a>.<br/>
<em>MAPEX issues with BACKLOG or OPEN status. Each bar = one week, stacked: orange = Backlog, blue = Open.</em></p>
<h2>Trend Chart</h2>
{chart_macro}
<h2>Raw Data</h2>
<table><tbody>
<tr><th>Week</th><th>Backlog</th><th>Open</th><th>Total</th></tr>
{raw_rows}
</tbody></table>
"""


def main():
    print(f"\n=== Updating Confluence (space: {SPACE_KEY}) ===")
    print(f"Confluence API: {CONF_API}")

    # Load historical data from CSV
    wg_data = defaultdict(dict)
    if DATA_FILE.exists() and DATA_FILE.stat().st_size > 0:
        with open(DATA_FILE, newline="") as f:
            for row in csv.DictReader(f):
                wg_data[row["workgroup"]][row["week"]] = {
                    "backlog": int(row["backlog"]), "open": int(row["open"])
                }
        print(f"Loaded historical data from {DATA_FILE}")

    # Merge latest snapshot
    if not SNAPSHOT_FILE.exists():
        print(f"ERROR: {SNAPSHOT_FILE} not found. collect_jira_data.py must run first.")
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

    # Create/update index page
    index_html = "<p>Auto-generated index of MAPEX workgroup trend pages.</p><ul>" + \
        "".join(f'<li><ac:link><ri:page ri:content-title="{wg} - MAPEX Trend" /></ac:link></li>' for wg in workgroups) + \
        "</ul>"
    index_page = upsert_page(INDEX_TITLE, index_html)
    index_id = index_page.get("id")
    if not index_id:
        index_id = get_page(INDEX_TITLE)["id"]

    # Create/update one page per workgroup
    for wg in workgroups:
        weeks = sorted(wg_data[wg].keys())
        backlog_vals = [wg_data[wg][w]["backlog"] for w in weeks]
        open_vals    = [wg_data[wg][w]["open"]    for w in weeks]
        upsert_page(f"{wg} - MAPEX Trend", build_chart_html(wg, weeks, backlog_vals, open_vals), parent_id=index_id)

    print("\nAll Confluence pages updated successfully.")


if __name__ == "__main__":
    main()
