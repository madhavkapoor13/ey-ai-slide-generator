#!/usr/bin/env python3
"""
scripts/ingest_asset.py
=======================
Offline ingestion CLI — turns a ``.pptx`` into a registered Presentation Asset.

Flow:

  1. ``Asset Inspector`` analyzes the .pptx (shape enumeration, repeating
     detection, kind heuristics, density proposal).
  2. Write a draft ``asset.json`` next to ``asset.pptx``.
  3. Human edits the draft — fills ``family`` (unless auto-detected),
     ``purpose``, ``audience_tags``, ``style_tags``, ``recommended_for``,
     ``avoid_for``, ``density_range``, ``fits_content_kinds``, and any
     placeholder ``role`` adjustments. The Inspector's auto-filled
     ``binding``/``density``/``repeating``/``kind`` are scaffolding.
  4. Restart the backend — the registry auto-discovers the asset on next
     load. No registration call is required.

Idempotent: re-running on an asset that already has an ``asset.json`` is
a no-op unless ``--force`` is supplied (which OVERWRITES the file and
loses human edits). Use ``--force`` only BEFORE you've started curating.

Usage
-----
::

    python scripts/ingest_asset.py path/to/asset.pptx
    python scripts/ingest_asset.py path/to/asset_dir/            # looks for asset.pptx
    python scripts/ingest_asset.py asset.pptx --asset-id ROADMAP-3PHASE-001
    python scripts/ingest_asset.py asset.pptx --family roadmap
    python scripts/ingest_asset.py asset.pptx --force
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow running as a standalone script (mirrors scripts/run_comparison.py).
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.presentation_assets import asset_inspector  # noqa: E402


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect a .pptx and write a draft asset.json manifest.",
    )
    parser.add_argument(
        "path",
        help="Path to a .pptx file, or a directory containing asset.pptx.",
    )
    parser.add_argument(
        "--asset-id",
        default=None,
        help="Override asset_id (default: derive from filename or parent dir).",
    )
    parser.add_argument(
        "--family",
        default=None,
        help="Pre-fill family (default: derive from parent dir when it is a known family).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing asset.json — loses human edits.",
    )
    return parser.parse_args(argv)


def _resolve_pptx(path: Path) -> Path:
    """Resolve a user-given path to the actual .pptx file."""
    if path.is_dir():
        candidate = path / "asset.pptx"
        if not candidate.exists():
            raise FileNotFoundError(f"No asset.pptx found in directory {path}")
        return candidate
    return path


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    pptx_path = _resolve_pptx(Path(args.path).resolve())
    out_dir = pptx_path.parent
    manifest_path = out_dir / "asset.json"

    if manifest_path.exists() and not args.force:
        print(
            f"[skip] {manifest_path} already exists "
            "(--force to overwrite, which loses human edits)"
        )
        return 0

    report = asset_inspector.inspect(
        pptx_path,
        asset_id=args.asset_id,
        family=args.family,
    )
    draft = report.proposed_manifest.model_dump(mode="json")

    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(draft, f, indent=2)

    print(f"[wrote] {manifest_path}")
    print(f"  asset_id:     {draft['asset_id']}")
    print(f"  family:       {draft['family'] or '(empty — please fill)'}")
    print(f"  density:      {draft['density']}  range {draft['density_range']}")
    print(f"  placeholders: {len(draft['placeholders'])}")
    if draft.get("repeating"):
        print(
            f"  repeating:    template={draft['repeating']['group_template']!r} "
            f"ids={draft['repeating']['placeholders_per_group']} count={draft['repeating']['count']}"
        )
    print("  supports_images: " + ("yes" if draft["supports_images"] else "no"))
    print()
    print("  Next — edit asset.json to fill:")
    print("    family (confirm), purpose, audience_tags, style_tags,")
    print("    recommended_for, avoid_for, density_range, fits_content_kinds")
    print("    and adjust placeholder role/kind/content_schema as needed.")
    print("  Then restart the backend; the registry auto-discovers it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())