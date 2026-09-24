# MapEx Jira Monitoring

Automated weekly snapshot of MAPEX Jira backlog/open plus flow metrics per workgroup,
with trend charts published to Confluence.

## How it works

1. **Every Saturday at 20:00 CET** a GitHub Actions workflow runs.
2. It queries Jira for weekly snapshot counts and weekly flow transitions:
   - Backlog: `project = MAPEX AND status = Backlog AND createdDate > "2026-01-01"`
   - Open: `project = MAPEX AND status = Open AND createdDate > "2026-01-01"`
   - Created (arrivals): issues created in the ISO week window
   - Started: issues with `status CHANGED FROM "Backlog" TO "Open" DURING (...)`
   - Closed (throughput): issues with `status CHANGED TO "Closed" DURING (...)`
3. Counts are grouped by **workgroup** (`customfield_10521`).
4. A new row is appended to `data/weekly_snapshots.csv` with:
   - `backlog`, `open`, `created`, `started`, `closed`, `net_flow` (`created - closed`)
5. One Confluence page per workgroup is created/updated in the `~lapio` space
   with a **16-week stacked backlog/open chart**.
6. **Pilot only:** `LE - Africa` also gets a 3-week flow/velocity chart
   (Created vs Closed bars + Net Flow line) and a compact pilot summary table.

## Setup

### 1. Add GitHub Secrets

Go to **Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Value |
|---|---|
| `ATLASSIAN_EMAIL` | Your Atlassian account email |
| `ATLASSIAN_API_TOKEN` | Your Atlassian API token |
| `ATLASSIAN_BASE_URL` | `https://tomtom.atlassian.net` |
| `CONFLUENCE_SPACE_KEY` | `~lapio` |
| `WORKGROUP_FIELD` | `customfield_10521` |

### 2. Test manually

Once secrets are configured:
1. Go to **Actions → Jira Weekly Monitoring**
2. Click **Run workflow** → **Run workflow**
3. Check your Confluence space: `https://tomtom.atlassian.net/wiki/spaces/~lapio`

## File structure

```
.github/workflows/jira_monitor.yml   # Scheduled workflow (Saturdays 20:00 CET)
scripts/
  collect_jira_data.py               # Fetches Jira data, writes CSV + JSON
  update_confluence.py               # Reads CSV, updates Confluence pages
  discover_fields.py                 # One-time helper to find field IDs
data/
  weekly_snapshots.csv               # Historical data (auto-committed weekly)
  latest_snapshot.json               # Latest snapshot used by Confluence updater
```

## Confluence structure

```
MAPEX Jira Workgroup Trends          <- index page
  ├── WorkgroupA - MAPEX Trend
  ├── WorkgroupB - MAPEX Trend
  └── ... (one page per workgroup)
```
