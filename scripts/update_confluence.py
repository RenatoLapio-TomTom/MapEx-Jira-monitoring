import os
import csv
import json
import requests
from requests.auth import HTTPBasicAuth
from collections import defaultdict
# --- Config ---
CONFLUENCE_BASE_URL = os.environ["CONFLUENCE_BASE_URL"]
CONFLUENCE_EMAIL = os.environ["CONFLUENCE_EMAIL"]
CONFLUENCE_API_TOKEN = os.environ["CONFLUENCE_API_TOKEN"]
CSV_PATH = "data/weekly_snapshots.csv"
auth = HTTPBasicAuth(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN)
headers = {"Accept": "application/json", "Content-Type": "application/json"}
# Map workgroup name → Confluence page ID
WORKGROUP_PAGE_IDS = {
    "Map Experts Lebanon": "2245001515",
    "Map Experts Pune": "2245001516",
    "Map Experts Gent": "2245001517",
    "Map Experts Lodz": "2245001518",
    "Map Experts Internal": "2245001519",
    "LE - Africa": "2245001520",
    "LE - Canada and USA": "2245001521",
    "LE - Eastern Europe and Central Asia": "2245001522",
    "LE - Mexico and Latin America": "2245001523",
    "LE - North and Central Europe": "2245001524",
    "LE - Northeast Asia": "2245001525",
    "LE - South Asia and Middle East": "2245001526",
    "LE - Southeast Asia and Oceania": "2245001527",
    "LE - South West Europe": "2245001528",
}
def load_data():
    data = defaultdict(dict)  # data[workgroup][week] = {backlog, open}
    with open(CSV_PATH, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            wg = row["workgroup"]
            week = row["week"]
            data[wg][week] = {
                "backlog": int(row["backlog"]) if row.get("backlog", "").strip() else 0,
                "open": int(row["open"]) if row.get("open", "").strip() else 0,
            }
    return data
def build_chart_html(workgroup, weeks_data):
    weeks = sorted(weeks_data.keys())
    backlog_vals = [weeks_data[w]["backlog"] for w in weeks]
    open_vals = [weeks_data[w]["open"] for w in weeks]
    labels = json.dumps(weeks)
    backlog_data = json.dumps(backlog_vals)
    open_data = json.dumps(open_vals)
    return f"""
<canvas id="chart_{workgroup.replace(' ', '_').replace('-', '_')}" width="700" height="350"></canvas>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
new Chart(document.getElementById('chart_{workgroup.replace(' ', '_').replace('-', '_')}'), {{
  type: 'bar',
  data: {{
    labels: {labels},
    datasets: [
      {{
        label: 'Backlog',
        data: {backlog_data},
        backgroundColor: 'rgba(255, 159, 64, 0.8)'
      }},
      {{
        label: 'Open',
        data: {open_data},
        backgroundColor: 'rgba(54, 162, 235, 0.8)'
      }}
    ]
  }},
  options: {{
    responsive: true,
    plugins: {{
      title: {{
        display: true,
        text: 'Weekly BACKLOG & OPEN Trend — {workgroup}'
      }},
      legend: {{ position: 'top' }}
    }},
    scales: {{
      x: {{ stacked: true }},
      y: {{ stacked: true, beginAtZero: true }}
    }}
  }}
}});
</script>
"""
def build_table_html(weeks_data):
    weeks = sorted(weeks_data.keys())
    rows = ""
    for w in weeks:
        b = weeks_data[w]["backlog"]
        o = weeks_data[w]["open"]
        total = b + o
        rows += f"<tr><td>{w}</td><td>{b}</td><td>{o}</td><td><strong>{total}</strong></td></tr>"
    return f"""
<table>
  <thead>
    <tr>
      <th>Week</th>
      <th>Backlog</th>
      <th>Open</th>
      <th>Total</th>
    </tr>
  </thead>
  <tbody>
    {rows}
  </tbody>
</table>
"""
def update_page(page_id, workgroup, weeks_data):
    # Get current page version
    url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{page_id}?expand=version,body.storage"
    response = requests.get(url, headers=headers, auth=auth)
    response.raise_for_status()
    page = response.json()
    version = page["version"]["number"]
    title = page["title"]
    chart_html = build_chart_html(workgroup, weeks_data)
    table_html = build_table_html(weeks_data)
    new_body = f"""
<h2>Weekly Backlog &amp; Open Trend</h2>
{chart_html}
<h2>Raw Data</h2>
{table_html}
"""
    payload = {
        "version": {"number": version + 1},
        "title": title,
        "type": "page",
        "body": {
            "storage": {
                "value": new_body,
                "representation": "storage"
            }
        }
    }
    put_url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{page_id}"
    put_response = requests.put(put_url, headers=headers, auth=auth, json=payload)
    put_response.raise_for_status()
    print(f"  ✅ Updated: {workgroup} (page {page_id})")
def run():
    data = load_data()
    for workgroup, weeks_data in data.items():
        page_id = WORKGROUP_PAGE_IDS.get(workgroup)
        if not page_id:
            print(f"  ⚠️ No page ID configured for: {workgroup} — skipping")
            continue
        print(f"Updating {workgroup}...")
        update_page(page_id, workgroup, weeks_data)
    print("✅ All Confluence pages updated.")
if __name__ == "__main__":
    run()
