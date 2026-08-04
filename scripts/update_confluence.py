import os
import csv
import io
import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from requests.auth import HTTPBasicAuth
from collections import defaultdict

# --- Config ---
CONFLUENCE_BASE_URL = os.environ["CONFLUENCE_BASE_URL"]
CONFLUENCE_EMAIL = os.environ["CONFLUENCE_EMAIL"]
CONFLUENCE_API_TOKEN = os.environ["CONFLUENCE_API_TOKEN"]
CSV_PATH = "data/weekly_snapshots.csv"

auth = HTTPBasicAuth(CONFLUENCE_EMAIL, CONFLUENCE_API_TOKEN)
headers = {"Accept": "application/json", "Content-Type": "application/json"}

# Map workgroup name -> Confluence page ID
WORKGROUP_PAGE_IDS = {
    "Map Experts Lebanon": "2245001515",
    "Map Experts Pune": "2244575432",
    "Map Experts Gent": "2245230751",
    "Map Experts Lodz": "2244542788",
    "Map Experts Internal": "2245165286",
    "LE - Africa": "2244182226",
    "LE - Canada and USA": "2244247796",
    "LE - Eastern Europe and Central Asia": "2245427391",
    "LE - Mexico and Latin America": "2244477241",
    "LE - North and Central Europe": "2245623979",
    "LE - Northeast Asia": "2245394686",
    "LE - South Asia and Middle East": "2245034207",
    "LE - Southeast Asia and Oceania": "2244575409",
    "LE - South West Europe": "2244378902",
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


def generate_chart(workgroup, weeks_data):
    """Generate a stacked bar chart as PNG bytes."""
    weeks = sorted(weeks_data.keys())

    # Rolling window: last 16 weeks only
    if len(weeks) > 16:
        weeks = weeks[-16:]

    backlog_vals = [weeks_data[w]["backlog"] for w in weeks]
    open_vals = [weeks_data[w]["open"] for w in weeks]

    x = np.arange(16)  # always 16 slots on x-axis
    width = 0.55        # thinner bars, closer together

    fig, ax = plt.subplots(figsize=(16, 5))  # fixed width always

    bars_backlog = ax.bar(x[:len(weeks)], backlog_vals, width, label="Backlog", color="#FF9F40")
    bars_open = ax.bar(x[:len(weeks)], open_vals, width, bottom=backlog_vals, label="Open", color="#36A2EB")

    # Add value labels inside bars
    for i in range(len(weeks)):
        if backlog_vals[i] > 0:
            ax.text(x[i], backlog_vals[i] / 2, str(backlog_vals[i]),
                    ha="center", va="center", fontweight="bold", fontsize=12, color="white")
        if open_vals[i] > 0:
            ax.text(x[i], backlog_vals[i] + open_vals[i] / 2, str(open_vals[i]),
                    ha="center", va="center", fontweight="bold", fontsize=12, color="white")

    ax.set_xlabel("Week")
    ax.set_ylabel("Issue Count")
    ax.set_title(f"Weekly BACKLOG & OPEN Trend — {workgroup}")
    ax.set_xticks(x[:len(weeks)])
    ax.set_xticklabels(weeks, rotation=45, ha="right", fontsize=12)
    ax.set_xlim(-0.5, 15.5)  # fixed x range for 16 slots
    ax.legend(loc="upper right")
    ax.set_ylim(0, max((b + o for b, o in zip(backlog_vals, open_vals)), default=10) * 1.15)

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


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


def upload_attachment(page_id, filename, image_bytes):
    """Upload (or update) a PNG attachment on the given Confluence page."""
    url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{page_id}/child/attachment"

    # Check if attachment already exists
    existing = requests.get(url, auth=auth, headers={"Accept": "application/json"})
    existing.raise_for_status()
    att_id = None
    for att in existing.json().get("results", []):
        if att["title"] == filename:
            att_id = att["id"]
            break

    upload_headers = {"X-Atlassian-Token": "nocheck"}
    files = {"file": (filename, image_bytes, "image/png")}

    if att_id:
        # Update existing attachment
        put_url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{page_id}/child/attachment/{att_id}/data"
        resp = requests.post(put_url, auth=auth, headers=upload_headers, files=files)
    else:
        # Create new attachment
        resp = requests.post(url, auth=auth, headers=upload_headers, files=files)

    resp.raise_for_status()
    print(f"    📎 Attachment '{filename}' uploaded to page {page_id}")


def update_page(page_id, workgroup, weeks_data):
    chart_filename = f"chart_{workgroup.replace(' ', '_').replace('-', '_')}.png"

    # 1. Generate and upload chart image
    chart_bytes = generate_chart(workgroup, weeks_data)
    upload_attachment(page_id, chart_filename, chart_bytes)

    # 2. Get current page version
    url = f"{CONFLUENCE_BASE_URL}/rest/api/content/{page_id}?expand=version,body.storage"
    response = requests.get(url, headers=headers, auth=auth)
    response.raise_for_status()
    page = response.json()
    version = page["version"]["number"]
    title = page["title"]

    # 3. Build page body with embedded chart image + table
    table_html = build_table_html(weeks_data)
    new_body = f"""
<h2>Weekly Backlog &amp; Open Trend</h2>
<ac:image ac:width="1100"><ri:attachment ri:filename="{chart_filename}" /></ac:image>
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
                "representation": "storage",
            }
        },
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
