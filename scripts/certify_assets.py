#!/usr/bin/env python3
"""Certify Presentation Assets and print a JSON report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.presentation_assets import asset_registry
from backend.presentation_assets.asset_certifier import certify_all, certify_asset


def main() -> int:
    parser = argparse.ArgumentParser(description="Certify Presentation Assets.")
    parser.add_argument("--asset-id", help="Certify one asset id instead of all assets.")
    parser.add_argument("--assets-dir", type=Path, help="Optional presentation_assets root.")
    args = parser.parse_args()

    if args.asset_id:
        result = {args.asset_id: certify_asset(args.asset_id, assets_dir=args.assets_dir)}
    else:
        result = certify_all(assets_dir=args.assets_dir)

    print(json.dumps({k: v.model_dump(mode="json") for k, v in result.items()}, indent=2))
    failures = [
        asset_id
        for asset_id, item in result.items()
        if not item.certified and not _is_quarantined(asset_id, args.assets_dir)
    ]
    return 1 if failures else 0


def _is_quarantined(asset_id: str, assets_dir: Path | None) -> bool:
    manifest = asset_registry.get(asset_id, assets_dir=assets_dir)
    if manifest is None:
        return False
    return (
        not manifest.certification.certified
        and any(
            str(error).lower().startswith("quarantined:")
            for error in manifest.certification.errors
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
