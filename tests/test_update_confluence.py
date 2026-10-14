import os
import sys
import unittest

os.environ.setdefault("CONFLUENCE_BASE_URL", "https://example.invalid/wiki")
os.environ.setdefault("CONFLUENCE_EMAIL", "test@example.invalid")
os.environ.setdefault("CONFLUENCE_API_TOKEN", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import update_confluence as uc  # noqa: E402

WEEKS_DATA = {
    "2026-W36": {"backlog": 1, "open": 1, "created": 9, "started": 9, "closed": 9, "net_flow": 0},
    "2026-W37": {"backlog": 1, "open": 1, "created": 0, "started": 0, "closed": 0, "net_flow": 0},
    "2026-W38": {"backlog": 1, "open": 1, "created": 4, "started": 1, "closed": 2, "net_flow": 2},
    "2026-W39": {"backlog": 1, "open": 1, "created": 2, "started": 2, "closed": 5, "net_flow": -3},
    "2026-W40": {"backlog": 1, "open": 1, "created": 0, "started": 0, "closed": 0, "net_flow": 0},
    "2026-W41": {"backlog": 1, "open": 1, "created": 3, "started": 1, "closed": 1, "net_flow": 2},
    "2026-W42": {"backlog": 1, "open": 1, "created": 4, "started": 2, "closed": 2, "net_flow": 2},
}


class FlowPilotSectionTests(unittest.TestCase):
    def test_section_for_non_africa_workgroup(self):
        workgroup = "Map Experts Pune"
        _, pilot_file = uc.chart_filenames(workgroup)
        section = uc.build_flow_pilot_section_html(workgroup, pilot_file, WEEKS_DATA)
        self.assertIn("<h2>Weekly Flow / Velocity Trend (Map Experts Pune)</h2>", section)
        self.assertIn("<h3>Flow Summary</h3>", section)
        self.assertNotIn("3-Week", section)
        self.assertNotIn("Pilot", section)
        self.assertNotIn("Africa", section)
        self.assertIn('ri:filename="chart_Map_Experts_Pune_flow_pilot.png"', section)
        for old_week in ("2026-W36", "2026-W37", "2026-W38"):
            self.assertNotIn(old_week, section)
        self.assertIn("<td>2026-W39</td><td>2</td><td>2</td><td>5</td><td>-3</td><td>2.50</td>", section)
        self.assertIn("<td>2026-W40</td><td>0</td><td>0</td><td>0</td><td>0</td><td>n/a</td>", section)

    def test_flow_history_grows_from_w39(self):
        def table_weeks(data):
            table = uc.build_flow_pilot_table_html(data)
            return [w for w in sorted(data) if f"<td>{w}</td>" in table]

        expected = ["2026-W39", "2026-W40", "2026-W41", "2026-W42"]
        self.assertEqual(uc.flow_history_weeks(WEEKS_DATA), expected)
        self.assertEqual(table_weeks(WEEKS_DATA), expected)

        grown = dict(WEEKS_DATA)
        grown["2026-W43"] = {"backlog": 1, "open": 1, "created": 1, "started": 1, "closed": 3, "net_flow": -2}
        expected_grown = expected + ["2026-W43"]
        self.assertEqual(uc.flow_history_weeks(grown), expected_grown)
        self.assertEqual(table_weeks(grown), expected_grown)

        table = uc.build_flow_pilot_table_html(grown)
        positions = [table.index(f"<td>{w}</td>") for w in expected_grown]
        self.assertEqual(positions, sorted(positions))

    def test_flow_history_crosses_year_boundary(self):
        data = {w: {"created": 1, "closed": 1} for w in ("2026-W38", "2026-W52", "2026-W39", "2027-W01")}
        self.assertEqual(uc.flow_history_weeks(data), ["2026-W39", "2026-W52", "2027-W01"])

    def test_filenames_unique_and_distinct(self):
        names = []
        for wg in uc.WORKGROUP_PAGE_IDS:
            backlog_file, pilot_file = uc.chart_filenames(wg)
            self.assertNotEqual(backlog_file, pilot_file)
            self.assertEqual(uc.chart_filenames(wg), (backlog_file, pilot_file))
            names += [backlog_file, pilot_file]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(uc.chart_filenames("LE - Africa")[1], "chart_LE___Africa_flow_pilot.png")

    def test_chart_title_uses_workgroup(self):
        titles = []
        orig = uc.plt.Axes.set_title

        def capture(ax, title, *a, **k):
            titles.append(title)
            return orig(ax, title, *a, **k)

        uc.plt.Axes.set_title = capture
        try:
            png = uc.generate_flow_pilot_chart("LE - Northeast Asia", WEEKS_DATA)
        finally:
            uc.plt.Axes.set_title = orig
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertTrue(any(t.endswith("— LE - Northeast Asia") for t in titles))
        self.assertTrue(any(t.startswith("Weekly Flow / Velocity Trend") for t in titles))
        self.assertFalse(any("3-Week" in t or "Pilot" in t for t in titles))

    def test_chart_shows_all_weeks_from_w39(self):
        tick_labels = []
        orig = uc.plt.Axes.set_xticklabels

        def capture(ax, labels, *a, **k):
            tick_labels.append(list(labels))
            return orig(ax, labels, *a, **k)

        grown = dict(WEEKS_DATA)
        grown["2026-W43"] = {"created": 1, "started": 1, "closed": 3, "net_flow": -2}
        uc.plt.Axes.set_xticklabels = capture
        try:
            uc.generate_flow_pilot_chart("LE - Africa", WEEKS_DATA)
            uc.generate_flow_pilot_chart("LE - Africa", grown)
        finally:
            uc.plt.Axes.set_xticklabels = orig
        self.assertEqual(tick_labels[0], ["2026-W39", "2026-W40", "2026-W41", "2026-W42"])
        self.assertEqual(tick_labels[1], ["2026-W39", "2026-W40", "2026-W41", "2026-W42", "2026-W43"])

    def test_missing_stock_snapshot_is_displayed_as_unavailable(self):
        weeks_data = {
            "2026-W38": {
                "backlog": None, "open": None,
                "created": 1, "started": 0, "closed": 0, "net_flow": 1,
            },
        }
        section = uc.build_table_html(weeks_data)
        self.assertIn("<td>2026-W38</td><td>n/a</td><td>n/a</td><td><strong>n/a</strong></td>", section)
        self.assertTrue(uc.generate_chart("New team", weeks_data).startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
