from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from a_share_quant_agent.data_sources import (
    apply_point_in_time_stock_master_filter,
    enrich_panel_with_stock_master,
    load_stock_master_csv,
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

    def _load(self, raw: str) -> pd.DataFrame:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "security_master.csv"
            path.write_text(raw, encoding="utf-8")
            try:
                return load_stock_master_csv(path).master
            except Exception as exc:  # The contract requires both QData field families to load.
                self.fail(f"QData stock master should normalize without error: {exc}")


if __name__ == "__main__":
    unittest.main()
