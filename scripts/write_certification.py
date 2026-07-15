#!/usr/bin/env python3
"""Write successful certification results back into each manifest."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.presentation_assets.asset_certifier import certify_all


def main():
    results = certify_all(assets_dir=Path("presentation_assets"))
    for asset_id, cert in results.items():
        if not cert.certified:
            continue
        asset_dir = Path("presentation_assets")
        # find the family folder
        for family_dir in asset_dir.iterdir():
            if not family_dir.is_dir():
                continue
            candidate = family_dir / asset_id / "asset.json"
            if candidate.exists():
                manifest = json.loads(candidate.read_text(encoding="utf-8"))
                manifest["certification"] = cert.model_dump(mode="json")
                candidate.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                print(f"[certified] {asset_id}")
                break


if __name__ == "__main__":
    main()
