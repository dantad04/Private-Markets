from __future__ import annotations

import unittest

from scripts.demo_corpus import DemoCorpusError, load_manifest, require_postgres_database_url


class TestDemoCorpusManifest(unittest.TestCase):
    def test_manifest_matches_locked_demo_fund_scope(self) -> None:
        manifest = load_manifest()

        self.assertEqual(
            ["hesta", "aware", "unisuper", "australiansuper", "cbus"],
            [fund.fund_code for fund in manifest.funds],
        )
        self.assertNotIn(
            "HostPlusPhdStateMachineAdapter",
            {fund.adapter_key for fund in manifest.funds},
        )
        self.assertNotIn(
            "AustralianRetirementTrustReal16ColumnPhdAdapter",
            {fund.adapter_key for fund in manifest.funds},
        )
        self.assertNotIn("ArtQsuperPhdAdapter", {fund.adapter_key for fund in manifest.funds})
        self.assertNotIn("ArtSunsuperPhdAdapter", {fund.adapter_key for fund in manifest.funds})

    def test_manifest_file_counts_and_rows_are_self_consistent(self) -> None:
        manifest = load_manifest()
        expected = {
            "hesta": (9, 14620),
            "aware": (14, 19132),
            "unisuper": (1, 25404),
            "australiansuper": (10, 22917),
            "cbus": (11, 13352),
        }

        for fund in manifest.funds:
            with self.subTest(fund=fund.fund_code):
                self.assertEqual(expected[fund.fund_code][0], fund.expected_source_file_count)
                self.assertEqual(expected[fund.fund_code][1], fund.expected_row_count)
                self.assertEqual(
                    fund.expected_row_count,
                    sum(source_file.expected_rows for source_file in fund.source_files),
                )
                self.assertEqual(0, fund.row_count_tolerance)

        self.assertEqual(95425, sum(fund.expected_row_count for fund in manifest.funds))

    def test_database_url_must_be_postgres(self) -> None:
        with self.assertRaisesRegex(DemoCorpusError, "DATABASE_URL must be set"):
            require_postgres_database_url("")
        with self.assertRaisesRegex(DemoCorpusError, "SQLite"):
            require_postgres_database_url("sqlite:///demo.db")

        self.assertEqual(
            "postgresql+psycopg://postgres@127.0.0.1:5432/private_markets_demo",
            require_postgres_database_url(
                "postgresql+psycopg://postgres@127.0.0.1:5432/private_markets_demo"
            ),
        )


if __name__ == "__main__":
    unittest.main()
