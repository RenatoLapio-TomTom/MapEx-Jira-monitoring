import os
import csv
import argparse
from datetime import datetime, timedelta
import requests
from requests.auth import HTTPBasicAuth

# --- Config ---
JIRA_BASE_URL = os.environ["JIRA_BASE_URL"]
JIRA_EMAIL = os.environ["JIRA_EMAIL"]
JIRA_API_TOKEN = os.environ["JIRA_API_TOKEN"]
CSV_PATH = "data/weekly_snapshots.csv"

WORKGROUPS = [
    "Map Experts Lebanon",
    "Map Experts Pune",
    "Map Experts Gent",
    "Map Experts Lodz",
    "Map Experts Internal",
    "LE - Africa",
    "LE - Canada and USA",
    "LE - Eastern Europe and Central Asia",
    "LE - Mexico and Latin America",
    "LE - North and Central Europe",
    "LE - Northeast Asia",
    "LE - South Asia and Middle East",
    "LE - Southeast Asia and Oceania",
    "LE - South West Europe",
]

# ISO week → snapshot date (Saturday of that week)
BACKFILL_DATES = {
    "W28": "2026-07-11",
    "W29": "2026-07-18",
    "W30": "2026-07-25",
}

auth = HTTPBasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)
headers = {"Accept": "application/json"}

def count_issues(jql):
    url = f"{JIRA_BASE_URL}/rest/api/3/search/jql/count"
    payload = {"jql": jql}
    response = requests.post(
        url,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        auth=auth,
        json=payload
    )
    response.raise_for_status()
    return response.json().get("count", 0)
    )
    response.raise_for_status()
    return response.json().get("total", 0)

def get_week_label():
    today = datetime.today()
    return f"W{today.isocalendar()[1]}"

def get_snapshot(workgroup, snapshot_date=None):
    wg = workgroup.replace('"', '\\"')
    if snapshot_date:
        backlog_jql = f'project = MAPEX AND status WAS "Backlog" ON "{snapshot_date}" AND cf[10521] = "{wg}"'
        open_jql = f'project = MAPEX AND status WAS "Open" ON "{snapshot_date}" AND cf[10521] = "{wg}"'
    else:
        backlog_jql = f'project = MAPEX AND status = "Backlog" AND cf[10521] = "{wg}"'
        open_jql = f'project = MAPEX AND status = "Open" AND cf[10521] = "{wg}"'
    backlog = count_issues(backlog_jql)
    open_count = count_issues(open_jql)
    return backlog, open_count

def load_existing_csv():
    rows = []
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "week" not in row:
                    continue
                row.pop("closed", None)
                row.pop("date", None)
                rows.append(row)
    return rows

def save_csv(rows):
    os.makedirs("data", exist_ok=True)
    fieldnames = ["week", "workgroup", "backlog", "open"]
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def run(backfill_weeks=None):
    existing_rows = load_existing_csv()
    if backfill_weeks:
        weeks_to_run = [w.strip() for w in backfill_weeks.split(",")]
        print(f"Running backfill for: {weeks_to_run}")
    else:
        weeks_to_run = [get_week_label()]
        print(f"Running current week snapshot: {weeks_to_run[0]}")
    for week_label in weeks_to_run:
        snapshot_date = BACKFILL_DATES.get(week_label) if backfill_weeks else None
        existing_rows = [r for r in existing_rows if r["week"] != week_label]
        for workgroup in WORKGROUPS:
            print(f"  {week_label} | {workgroup}...")
            backlog, open_count = get_snapshot(workgroup, snapshot_date)
            existing_rows.append({
                "week": week_label,
                "workgroup": workgroup,
                "backlog": backlog,
                "open": open_count,
            })
    save_csv(existing_rows)
    print("✅ CSV saved.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backfill", type=str, help="Comma-separated week labels e.g. W28,W29,W30")
    args = parser.parse_args()
    run(backfill_weeks=args.backfill)
