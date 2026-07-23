#!/usr/bin/env python3
"""
update_confluence.py

Reads weekly_snapshots.csv and creates/updates one Confluence page
per workgroup with a stacked bar chart showing weekly Backlog + Open trends.
"""

import os
import csv
import json
import requests
from collections import defaultdict
from pathlib import Path

EMAIL     = os.environ["ATLASSIAN_EMAIL"]
TOKEN     = os.environ["ATLASSIAN_API_TOKEN"]
BASE_URL  = os.environ["ATLASSIAN_BASE_URL"].rstrip("/")
SPACE_KEY = os.environ["CONFLUENCE_SPACE_KEY"]

CONF_API  = f"{BASE_URL}/wiki/rest/api"
AUTH      = (EMAIL, TOKEN)
HEADERS   = {"Accept": "application/json", "Content-Type": "application/json"}
DATA_FILE = Path("data/weekly_snapshots.csv")
INDEX_TITLE = "MAPEX Jira Workgroup Trends"


def get_page(title):
    resp = requests.get(f"{CONF_API}/content",
        params={"spaceKey": SPACE_KEY, "title": title, "expand": "version"},
        auth=AUTH, headers=HEADERS)
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
    resp = requests.post(f"{CONF_API}/content", auth=AUTH, headers=HEADERS, data=json.dumps(payload))
    resp.raise_for_status()
    return resp.json()


def update_page(page_id, version, title, body_html):
    payload = {
        "type": "page", "title": title,
        "version": {"number": version + 1},
        "body": {"storage": {"value": body_html, "representation": "storage"}},
    }
    resp = requests.put(f"{CONF_API}/content/{page_id}", auth=AUTH, headers=HEADERS, data=json.dumps(payload))
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
    table_rows = "".join(
        f"<tr><td>{w}</td><td>{backlog_vals[i]}</td><td>{open_vals[i]}</td></tr>"
        for i, w in enumerate(weeks)
    )
    chart_macro = f"""
<ac:structured-macro ac:name="chart" ac:schema-version="1">
  <ac:parameter ac:name="type">bar</ac:parameter>
  <ac:parameter ac:name="stacked">true</ac:parameter>
  <ac:parameter ac:name="title">{workgroup} - Weekly Backlog &amp; Open Trend</ac:parameter>
  <ac:parameter ac:name="width">800</ac:parameter>
  <ac:parameter ac:name="height">400</ac:parameter>
  <ac:parameter ac:name="colors">#FF8C00,#1F7BC0</ac:parameter>
  <ac:parameter ac:name="domainAxisLabel">Week</ac:parameter>
  <ac:parameter ac:name="rangeAxisLabel">Issue Count</ac:parameter>
  <ac:rich-text-body>
    <table><tbody>
      <tr><th>Week</th><th>Backlog</th><th>Open</th></tr>
      {table_rows}
    </tbody></table>
  </ac:rich-text-body>
</ac:structured-macro>"""

    data_rows = "".join(
        f"<tr><td>{w}</td><td>{backlog_vals[i]}</td><td>{open_vals[i]}</td><td><strong>{backlog_vals[i]+open_vals[i]}</strong></td></tr>"
        for i, w in enumerate(weeks)
    )
    return f"""
<p>Auto-updated every Saturday by <a href="https://github.com/RenatoLapio-TomTom/MapEx-Jira-monitoring">MapEx Jira Monitoring</a>.<br/>
<em>MAPEX issues created after 2026-01-01, Backlog or Open status.</em></p>
<h2>Trend Chart</h2>
{chart_macro}
<h2>Raw Data</h2>
<table><tbody>
<tr><th>Week</th><th>Backlog</th><th>Open</th><th>Total</th></tr>
{data_rows}
</tbody></table>
"""


def main():
    if not DATA_FILE.exists():
        print("No data file found. Run collect_jira_data.py first.")
        return

    wg_data = defaultdict(dict)
    with open(DATA_FILE, newline="") as f:
        for row in csv.DictReader(f):
            wg_data[row["workgroup"]][row["week"]] = {
                "backlog": int(row["backlog"]), "open": int(row["open"])
            }

    workgroups = sorted(wg_data.keys())
    print(f"\n=== Updating Confluence (space: {SPACE_KEY}) ===")
    print(f"Workgroups: {workgroups}")

    index_html = "<p>Auto-generated index of MAPEX workgroup trend pages.</p><ul>" + \
        "".join(f'<li><ac:link><ri:page ri:content-title="{wg} - MAPEX Trend" /></ac:link></li>' for wg in workgroups) + \
        "</ul>"
    index_page = upsert_page(INDEX_TITLE, index_html)
    index_id = index_page.get("id") or get_page(INDEX_TITLE)["id"]

    for wg in workgroups:
        weeks = sorted(wg_data[wg].keys())
        backlog_vals = [wg_data[wg][w]["backlog"] for w in weeks]
        open_vals    = [wg_data[wg][w]["open"]    for w in weeks]
        upsert_page(f"{wg} - MAPEX Trend", build_chart_html(wg, weeks, backlog_vals, open_vals), parent_id=index_id)

    print("\nAll Confluence pages updated successfully.")


if __name__ == "__main__":
    main()
