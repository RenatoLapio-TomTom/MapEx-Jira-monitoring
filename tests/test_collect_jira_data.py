import csv
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("JIRA_EMAIL", "test@example.invalid")
os.environ.setdefault("JIRA_API_TOKEN", "dummy")
os.environ.setdefault("JIRA_BASE_URL", "https://example.invalid")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import collect_jira_data as collector  # noqa: E402


class JiraSearchTests(unittest.TestCase):
    @staticmethod
    def response(status, issues=None, next_page_token=None, headers=None):
        result = Mock()
        result.status_code = status
        result.ok = 200 <= status < 400
        result.headers = headers or {}
        result.json.return_value = {
            "issues": issues or [],
            "nextPageToken": next_page_token,
        }
        return result

    @patch.object(collector.time, "sleep")
    @patch.object(collector.requests, "post")
    def test_retries_same_page_then_preserves_pagination_token(self, post, sleep):
        first_page = [{"key": "MAPEX-1"}]
        second_page = [{"key": "MAPEX-2"}]
        post.side_effect = [
            self.response(500),
            self.response(200, first_page, "page-2"),
            self.response(200, second_page),
        ]

        issues = collector.jira_search(
            "project = MAPEX", ["summary"], "CREATED flow", "2026-W38"
        )

        self.assertEqual(issues, first_page + second_page)
        self.assertEqual(post.call_count, 3)
        first_attempt_payload = post.call_args_list[0].kwargs["json"]
        retry_payload = post.call_args_list[1].kwargs["json"]
        self.assertEqual(first_attempt_payload, retry_payload)
        self.assertNotIn("nextPageToken", retry_payload)
        self.assertEqual(
            post.call_args_list[2].kwargs["json"]["nextPageToken"], "page-2"
        )
        self.assertEqual(post.call_args_list[0].kwargs["timeout"], 60)
        self.assertEqual(sleep.call_args_list[0].args, (2,))

    @patch.object(collector.time, "sleep")
    @patch.object(collector.requests, "post")
    def test_honors_retry_after_for_rate_limit(self, post, sleep):
        post.side_effect = [
            self.response(429, headers={"Retry-After": "3"}),
            self.response(200),
        ]

        self.assertEqual(
            collector.jira_search("project = MAPEX", [], "OPEN snapshot", "2026-W38"),
            [],
        )
        sleep.assert_called_once_with(3.0)

    @patch.object(collector.time, "sleep")
    @patch.object(collector.requests, "post")
    def test_nontransient_status_fails_without_retry(self, post, sleep):
        post.return_value = self.response(400)

        with self.assertRaisesRegex(
            collector.JiraSearchError, "OPEN snapshot search for 2026-W38 failed: HTTP 400"
        ):
            collector.jira_search("invalid", [], "OPEN snapshot", "2026-W38")

        post.assert_called_once()
        sleep.assert_not_called()


class HistoricalBackfillTests(unittest.TestCase):
    def test_snapshot_failure_preserves_stock_and_upserts_flow(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            data_file = temporary_path / "weekly_snapshots.csv"
            latest_file = temporary_path / "latest_snapshot.json"
            headers = [
                "week", "date", "workgroup", "backlog", "open",
                "created", "started", "closed", "net_flow",
            ]
            with data_file.open("w", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=headers)
                writer.writeheader()
                writer.writerows([
                    {
                        "week": "2026-W38", "date": "2026-09-20",
                        "workgroup": "Existing", "backlog": "12", "open": "4",
                        "created": "1", "started": "1", "closed": "0", "net_flow": "1",
                    },
                    {
                        "week": "2026-W38", "date": "2026-09-20",
                        "workgroup": "Zero stock", "backlog": "0", "open": "0",
                        "created": "0", "started": "0", "closed": "0", "net_flow": "0",
                    },
                    {
                        "week": "2026-W37", "date": "2026-09-13",
                        "workgroup": "Unchanged", "backlog": "7", "open": "3",
                        "created": "2", "started": "1", "closed": "1", "net_flow": "1",
                    },
                ])

            def search(_jql, _fields, category, _week):
                if category == "BACKLOG snapshot":
                    raise collector.JiraSearchError(
                        category, "2026-W38", status_code=500, retryable=True
                    )
                if category == "CREATED flow":
                    return [{
                        "fields": {collector.WORKGROUP_FIELD: {"value": "New team"}}
                    }]
                if category in {"STARTED flow", "CLOSED flow"}:
                    return [{
                        "fields": {collector.WORKGROUP_FIELD: {"value": "Existing"}}
                    }]
                return []

            with (
                patch.object(collector, "DATA_FILE", data_file),
                patch.object(collector, "LATEST_SNAPSHOT_FILE", latest_file),
                patch.object(collector, "jira_search", side_effect=search),
            ):
                collector.main("2026-W38")

            with data_file.open(newline="") as saved:
                rows = {
                    (row["week"], row["workgroup"]): row
                    for row in csv.DictReader(saved)
                }

            existing = rows[("2026-W38", "Existing")]
            self.assertEqual((existing["backlog"], existing["open"]), ("12", "4"))
            self.assertEqual(
                (existing["created"], existing["started"], existing["closed"], existing["net_flow"]),
                ("0", "1", "1", "-1"),
            )
            zero_stock = rows[("2026-W38", "Zero stock")]
            self.assertEqual((zero_stock["backlog"], zero_stock["open"]), ("0", "0"))
            self.assertEqual(zero_stock["created"], "0")
            new_team = rows[("2026-W38", "New team")]
            self.assertEqual((new_team["backlog"], new_team["open"]), ("", ""))
            self.assertEqual(new_team["created"], "1")
            self.assertIn(("2026-W37", "Unchanged"), rows)

            with latest_file.open() as saved:
                latest = json.load(saved)
            self.assertEqual(latest["workgroups"]["Existing"]["backlog"], "12")
            self.assertEqual(latest["workgroups"]["New team"]["open"], "")


if __name__ == "__main__":
    unittest.main()
