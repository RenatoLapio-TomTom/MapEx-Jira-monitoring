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
}


class FlowPilotSectionTests(unittest.TestCase):
    def test_section_for_non_africa_workgroup(self):
        workgroup = "Map Experts Pune"
        _, pilot_file = uc.chart_filenames(workgroup)
        section = uc.build_flow_pilot_section_html(workgroup, pilot_file, WEEKS_DATA)
        self.assertIn("3-Week Flow / Velocity Pilot (Map Experts Pune)", section)
        self.assertNotIn("Africa", section)
        self.assertIn('ri:filename="chart_Map_Experts_Pune_flow_pilot.png"', section)
        self.assertNotIn("2026-W36", section)
        self.assertIn("<td>2026-W37</td><td>0</td><td>0</td><td>0</td><td>0</td><td>n/a</td>", section)
        self.assertIn("<td>2026-W39</td><td>2</td><td>2</td><td>5</td><td>-3</td><td>2.50</td>", section)

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
