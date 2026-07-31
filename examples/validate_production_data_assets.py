from __future__ import annotations

import argparse
from pathlib import Path

from a_share_quant_agent.vendor_assets import validate_production_asset_bundle, write_production_asset_validation_artifacts


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    args = _parse_args()
    output_dir = Path(args.output_dir) if args.output_dir else Path(args.asset_root) / "manifests" / "production_import"
    validation = validate_production_asset_bundle(
        args.asset_root,
        start=args.start,
        end=args.end,
        min_stock_master_rows=args.historical_stock_master_min_rows,
        min_delisted_rows=args.min_delisted_rows,
        include_bj=args.include_bj,
    )
    paths = write_production_asset_validation_artifacts(output_dir, validation)
    quote = validation.get("quote_metrics", {})
    print(f"Status: {validation.get('status')}")
    print(f"Production ready: {validation.get('production_data_ready')}")
    print(f"Hard failed: {validation.get('hard_failed')}")
    print(f"Rows: {quote.get('rows', 0)}")
    print(f"Eligible coverage: {quote.get('eligible_symbol_coverage_rate', 0.0):.2%}")
    print(f"JSON: {paths['production_asset_validation']}")
    print(f"Report: {paths['production_asset_validation_report']}")
    return 0 if validation.get("production_data_ready") else 3


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate canonical production data assets under data_assets/.")
    parser.add_argument("--asset-root", default=str(ROOT / "data_assets"))
    parser.add_argument("--output-dir")
    parser.add_argument("--start", default="20210101")
    parser.add_argument("--end", default="20260724")
    parser.add_argument("--historical-stock-master-min-rows", type=int, default=3000)
    parser.add_argument("--min-delisted-rows", type=int, default=50)
    parser.add_argument("--include-bj", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
