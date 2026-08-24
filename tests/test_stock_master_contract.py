from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from a_share_quant_agent.data_sources import (
    DataSourceError,
    apply_point_in_time_stock_master_filter,
    enrich_panel_with_stock_master,
    load_stock_master_csv,
    symbols_from_stock_master,
)


class QDataStockMasterContractTest(unittest.TestCase):
    def test_qdata_export_fields_map_to_agent_lifecycle_fields(self) -> None:
        raw = (
            "symbol,name,asset_type,currency,list_date,delist_date,status\n"
            "000001.SZ,Example Bank,stock,CNY,2020-01-02,2020-01-05,delisted\n"
        )

        master = self._load(raw)

        row = master.iloc[0]
        self.assertEqual(row["stockName"], "Example Bank")
        self.assertEqual(row["stockType"], "A股")
        self.assertEqual(row["listStatus"], "delisted")
        self.assertEqual(row["listDate"], pd.Timestamp("2020-01-02"))
        self.assertEqual(row["delistDate"], pd.Timestamp("2020-01-05"))

    def test_qdata_database_names_map_to_agent_stock_master_fields(self) -> None:
        raw = (
            "current_symbol,current_name,asset_type,exchange,list_date,delist_date,current_status\n"
            "600001,Example Industrial,stock,SH,2019-03-01,,active\n"
        )

        master = self._load(raw)

        row = master.iloc[0]
        self.assertEqual(row["symbol"], "600001.SH")
        self.assertEqual(row["stockName"], "Example Industrial")
        self.assertEqual(row["listDate"], pd.Timestamp("2019-03-01"))
        self.assertEqual(row["listStatus"], "active")

    def test_numeric_yyyymmdd_dates_parse_as_calendar_dates_not_nanoseconds(self) -> None:
        raw = (
            "symbol,name,asset_type,list_date,delist_date,status,reportDate\n"
            "000001.SZ,Numeric Dates,stock,20200102,20200105,delisted,20200103\n"
        )

        master = self._load(raw)
        row = master.iloc[0]
        self.assertEqual(row["listDate"], pd.Timestamp("2020-01-02"))
        self.assertEqual(row["delistDate"], pd.Timestamp("2020-01-05"))
        self.assertEqual(row["reportDate"], pd.Timestamp("2020-01-03"))

        panel = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-04", "2020-01-05"]),
                "symbol": ["000001.SZ"] * 4,
            }
        )
        filtered = apply_point_in_time_stock_master_filter(
            enrich_panel_with_stock_master(panel, master)
        ).data
        self.assertEqual(list(filtered["is_stock_master_member"]), [False, True, True, False])

    def test_list_date_parser_rejects_float_short_fuzzy_time_and_invalid_calendar(self) -> None:
        invalid_values = (
            "20200102.0",
            "202001",
            "2020-01-02T00:00:00",
            "Jan 2 2020",
            "20200230",
        )

        for invalid in invalid_values:
            raw = (
                "symbol,name,asset_type,list_date,delist_date,status\n"
                f"000001.SZ,Invalid Date,stock,{invalid},,active\n"
            )
            with self.subTest(invalid=invalid):
                with self.assertRaises(DataSourceError):
                    self._load_unchecked(raw)

    def test_delist_and_report_dates_use_the_same_date_only_contract(self) -> None:
        fixtures = (
            (
                "symbol,name,asset_type,list_date,delist_date,status\n"
                "000001.SZ,Timed Delist,stock,2020-01-02,2020-01-05T12:00:00,delisted\n"
            ),
            (
                "symbol,name,asset_type,list_date,delist_date,status,reportDate\n"
                "000001.SZ,Timed Report,stock,2020-01-02,,active,2020-01-03 12:00:00\n"
            ),
        )

        for raw in fixtures:
            with self.subTest(raw=raw):
                with self.assertRaises(DataSourceError):
                    self._load_unchecked(raw)

    def test_mapped_qdata_dates_drive_point_in_time_eligibility(self) -> None:
        raw = (
            "symbol,name,asset_type,currency,list_date,delist_date,status\n"
            "000001.SZ,Example Bank,stock,CNY,2020-01-02,2020-01-05,delisted\n"
        )
        master = self._load(raw)
        panel = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-04", "2020-01-05"]),
                "symbol": ["000001.SZ"] * 4,
            }
        )

        enriched = enrich_panel_with_stock_master(panel, master)
        filtered = apply_point_in_time_stock_master_filter(enriched).data

        self.assertEqual(list(filtered["is_stock_master_member"]), [False, True, True, False])

    def test_historical_master_rejects_missing_asset_type(self) -> None:
        raw = (
            "symbol,name,list_date,delist_date,status\n"
            "000001.SZ,Unknown Type,2020-01-02,,active\n"
        )

        with self.assertRaises(DataSourceError):
            self._load_unchecked(raw)

    def test_historical_master_rejects_missing_or_invalid_list_date(self) -> None:
        fixtures = (
            "symbol,name,asset_type,list_date,delist_date,status\n"
            "000001.SZ,Missing Date,stock,,,active\n",
            "symbol,name,asset_type,list_date,delist_date,status\n"
            "000001.SZ,Invalid Date,stock,not-a-date,,active\n",
        )

        for raw in fixtures:
            with self.subTest(raw=raw):
                with self.assertRaises(DataSourceError):
                    self._load_unchecked(raw)

    def test_delisted_master_row_requires_delist_date(self) -> None:
        raw = (
            "symbol,name,asset_type,list_date,delist_date,status\n"
            "000001.SZ,Incomplete Delisting,stock,2020-01-02,,delisted\n"
        )

        with self.assertRaises(DataSourceError):
            self._load_unchecked(raw)

    def test_nonempty_invalid_delist_date_is_rejected(self) -> None:
        raw = (
            "symbol,name,asset_type,list_date,delist_date,status\n"
            "000001.SZ,Invalid Delist,stock,2020-01-02,not-a-date,active\n"
        )

        with self.assertRaises(DataSourceError):
            self._load_unchecked(raw)

    def test_delist_date_cannot_precede_list_date(self) -> None:
        raw = (
            "symbol,name,asset_type,list_date,delist_date,status\n"
            "000001.SZ,Impossible Lifecycle,stock,2020-01-02,2019-12-31,delisted\n"
        )

        with self.assertRaises(DataSourceError):
            self._load_unchecked(raw)

    def test_current_only_master_cannot_claim_historical_point_in_time_coverage(self) -> None:
        raw = "symbol,name,status\n000001.SZ,Current Only,active\n"

        with self.assertRaises(DataSourceError):
            self._load_unchecked(raw)

    def test_point_in_time_filter_fails_closed_for_unknown_lifecycle(self) -> None:
        panel = pd.DataFrame(
            {
                "date": pd.to_datetime(["2020-01-03", "2020-01-03", "2020-01-03"]),
                "symbol": ["000001.SZ", "000002.SZ", "000003.SZ"],
                "listDate": [pd.NaT, pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-01")],
                "delistDate": [pd.NaT, pd.NaT, pd.NaT],
                "stockType": ["A股", pd.NA, "A股"],
                "listStatus": ["active", "active", "delisted"],
            }
        )

        filtered = apply_point_in_time_stock_master_filter(panel).data

        self.assertEqual(list(filtered["is_stock_master_member"]), [False, False, False])

    def test_active_and_delisted_lifecycle_boundaries_remain_explicit(self) -> None:
        panel = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    ["2019-12-31", "2020-01-01", "2020-01-04", "2020-01-05"]
                ),
                "symbol": ["000001.SZ"] * 4,
                "listDate": [pd.Timestamp("2020-01-01")] * 4,
                "delistDate": [pd.Timestamp("2020-01-05")] * 4,
                "stockType": ["A股"] * 4,
                "listStatus": ["delisted"] * 4,
            }
        )

        filtered = apply_point_in_time_stock_master_filter(panel).data

        self.assertEqual(list(filtered["is_stock_master_member"]), [False, True, True, False])

    def test_candidate_symbol_extraction_fails_closed_without_lifecycle_evidence(self) -> None:
        incomplete = pd.DataFrame(
            {
                "symbol": ["000001.SZ"],
                "stockType": [pd.NA],
                "listDate": [pd.NaT],
                "delistDate": [pd.NaT],
                "listStatus": ["active"],
            }
        )

        symbols = symbols_from_stock_master(incomplete, start="2020-01-01", end="2020-12-31")

        self.assertEqual(symbols, ())

    def _load(self, raw: str) -> pd.DataFrame:
        try:
            return self._load_unchecked(raw)
        except Exception as exc:  # The contract requires both QData field families to load.
            self.fail(f"QData stock master should normalize without error: {exc}")

    def _load_unchecked(self, raw: str) -> pd.DataFrame:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "security_master.csv"
            path.write_text(raw, encoding="utf-8")
            return load_stock_master_csv(path).master


if __name__ == "__main__":
    unittest.main()
