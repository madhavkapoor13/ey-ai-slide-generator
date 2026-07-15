"""
Run the Golden Deck Regression Suite.

This script generates the benchmark consulting decks through the real V2
service path, then collects the `.evaluation.json` sidecar produced by demo
mode. It is intended for local quality regression before executive demos.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.slide_service import generate_slide_v2  # noqa: E402


GOLDEN_PROMPTS: dict[str, str] = {
    "microsoft_procurement": (
        "Create a consulting presentation for Microsoft's AI Procurement Transformation initiative. "
        "The audience is the Board of Directors. Include an Executive Summary, current procurement "
        "process, future-state operating model, key business benefits, AI use cases, implementation "
        "roadmap, KPIs for success, implementation risks, and next steps."
    ),
    "amazon_supply_chain": (
        "Create a consulting presentation for Amazon's Supply Chain Modernization initiative for the "
        "Board of Directors. Include executive summary, current supply chain process, case for change, "
        "future operating model, AI use cases, business benefits, implementation roadmap, KPIs, risks, "
        "and next steps."
    ),
    "hsbc_finance_ai": (
        "Create a consulting presentation for HSBC Finance AI Transformation for the Board of Directors. "
        "Include executive summary, current finance process, future-state finance operating model, value "
        "case, AI use cases, roadmap, KPIs, implementation risks, and next steps."
    ),
    "toyota_manufacturing": (
        "Create a consulting presentation for Toyota Manufacturing Operating Model Transformation for "
        "the Board of Directors. Include executive summary, current manufacturing operating model, future "
        "state, AI-enabled capabilities, benefits, roadmap, KPIs, risks, and next steps."
    ),
    "unilever_hr": (
        "Create a consulting presentation for Unilever HR Transformation for the Board of Directors. "
        "Include executive summary, current HR process, future-state operating model, AI use cases, "
        "business benefits, implementation roadmap, KPIs, risks, and next steps."
    ),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run golden deck regression prompts.")
    parser.add_argument("--only", choices=sorted(GOLDEN_PROMPTS), help="Run one golden prompt.")
    parser.add_argument("--output", default="golden_deck_report.json", help="Path for aggregate JSON report.")
    args = parser.parse_args()

    os.environ["EY_GENERATION_MODE"] = "demo"

    selected = {args.only: GOLDEN_PROMPTS[args.only]} if args.only else GOLDEN_PROMPTS
    results: dict[str, Any] = {}

    for name, prompt in selected.items():
        print(f"Generating {name}...")
        pptx_path = generate_slide_v2("Golden Deck Regression", prompt)
        evaluation_path = Path(pptx_path).with_suffix(".evaluation.json")
        evaluation: dict[str, Any] = {}
        if evaluation_path.exists():
            evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
        results[name] = {
            "pptx_path": pptx_path,
            "evaluation_path": str(evaluation_path),
            "demo_ready": bool(evaluation.get("demo_ready", False)),
            "planner_confidence_avg": evaluation.get("planner_confidence"),
            "asset_coverage": evaluation.get("asset_coverage"),
            "asset_diversity": evaluation.get("asset_diversity"),
            "duplicate_roles": evaluation.get("duplicate_roles", []),
            "missing_roles": evaluation.get("missing_roles", []),
            "asset_family_mismatches": evaluation.get("asset_family_mismatches", []),
            "consulting_language_warnings": evaluation.get("consulting_language_warnings", []),
            "placeholder_leakage": evaluation.get("placeholder_leakage", []),
            "overflow_slides": evaluation.get("overflow_slides", []),
        }

    output = Path(args.output)
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")
    passed = sum(1 for result in results.values() if result["demo_ready"])
    print(f"Wrote {output} ({passed}/{len(results)} demo-ready).")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
