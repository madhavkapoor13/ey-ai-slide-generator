"""
backend/presentation_assets/asset_registry.py
==============================================
Presentation Asset Registry — auto-discovery of asset manifests on disk.

The registry walks ``presentation_assets/**/*.json`` (every file named
``asset.json``), validates each into an ``AssetManifest``, and caches
the result. Discovery is automatic: drop a folder under
``presentation_assets/<family>/<asset_id>/`` containing ``asset.pptx``
and ``asset.json``, restart the backend, and the asset is available.
No registration call is required.

Design principles:
- A single invalid manifest is skipped with a logged warning; it never
  breaks the runtime. Auto-discovery must be resilient.
- Duplicate ``asset_id`` values are skipped (first occurrence wins) with
  a warning.
- Lookups are O(1) by id and O(N) by family over the in-memory cache.
- The registry never imports python-pptx; it handles JSON only.

When an explicit ``assets_dir`` is supplied (used by tests), a one-off
scan is performed and the default cache is left untouched. This keeps
test isolation simple without bespoke test fixtures in production code.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, Optional

from schemas.presentation_asset import AssetManifest

logger = logging.getLogger(__name__)

_ASSETS_DIR = Path(__file__).resolve().parents[2] / "presentation_assets"

_cache: dict[str, AssetManifest] | None = None
_path_index: dict[str, Path] | None = None


def _load_manifest_file(path: Path) -> AssetManifest:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    manifest = AssetManifest.model_validate(data)
    return _enrich_manifest_metadata(manifest)


_FAMILY_METADATA_DEFAULTS: dict[str, tuple[str, str]] = {
    "capability_map": ("operating_model", "capability_map"),
    "comparison": ("comparison", "comparison"),
    "executive_summary": ("executive_summary", "summary"),
    "journey": ("transformation_journey", "sequence"),
    "kpi": ("kpi_dashboard", "metrics"),
    "list": ("list", "list"),
    "process": ("process_flow", "sequence"),
    "roadmap": ("implementation_roadmap", "sequence"),
    "strategy": ("strategy_pillars", "portfolio"),
    "timeline": ("timeline", "sequence"),
}


def _enrich_manifest_metadata(manifest: AssetManifest) -> AssetManifest:
    """Backfill minimal V2 selection metadata for legacy manifests.

    Explicit manifest fields always win. This keeps selection data-driven for
    new assets while making the existing asset library usable with V2
    compatibility scoring.
    """
    message_type = manifest.message_type
    information_shape = manifest.information_shape
    defaults = _FAMILY_METADATA_DEFAULTS.get(manifest.family.lower())
    if defaults is not None:
        message_type = message_type or defaults[0]
        information_shape = information_shape or defaults[1]
    return manifest.model_copy(
        update={
            "message_type": message_type,
            "information_shape": information_shape,
        }
    )


def _scan(target: Path | str) -> tuple[dict[str, AssetManifest], dict[str, Path]]:
    """
    One-off scan of ``target`` for every ``asset.json`` file.

    Returns ``(manifests, asset_dirs)``. Malformed manifests are skipped
    with a warning. Duplicate asset ids keep the first occurrence.
    """
    target = Path(target)
    manifests: dict[str, AssetManifest] = {}
    paths: dict[str, Path] = {}

    if not target.exists():
        return manifests, paths

    for path in sorted(target.rglob("asset.json")):
        try:
            manifest = _load_manifest_file(path)
        except Exception as exc:
            logger.warning("asset_registry: skipping invalid manifest %s: %s", path, exc)
            continue

        asset_id = manifest.asset_id
        if asset_id in manifests:
            logger.warning(
                "asset_registry: duplicate asset_id %r in %s keeping first, skipping",
                asset_id,
                path,
            )
            continue

        manifests[asset_id] = manifest
        paths[asset_id] = path.parent

    return manifests, paths


def load_assets(assets_dir: Path | None = None) -> dict[str, AssetManifest]:
    """
    Load and cache all asset manifests discovered on disk.

    When ``assets_dir`` is omitted, the default ``presentation_assets/``
    directory at the repo root is used and the result is cached. When an
    explicit ``assets_dir`` is supplied (used by tests), no caching is
    performed and the default cache is left untouched.

    Returns a mapping of ``asset_id`` to ``AssetManifest``. Returns an
    empty dict if the assets directory does not exist.
    """
    global _cache, _path_index

    if assets_dir is None and _cache is not None:
        return _cache

    target = assets_dir if assets_dir is not None else _ASSETS_DIR
    manifests, paths = _scan(target)

    logger.info("asset_registry: loaded %d assets from %s", len(manifests), target)

    if assets_dir is None:
        _cache = manifests
        _path_index = paths

    return manifests


def clear_cache() -> None:
    """Clear the cached manifests. Useful for tests."""
    global _cache, _path_index
    _cache = None
    _path_index = None


def iter_assets() -> Iterable[AssetManifest]:
    """Iterate over all loaded manifests."""
    return load_assets().values()


def get(asset_id: str, assets_dir: Path | None = None) -> Optional[AssetManifest]:
    """Return the manifest for ``asset_id`` or ``None`` if not found."""
    return load_assets(assets_dir).get(asset_id)


def by_family(family: str, assets_dir: Path | None = None) -> list[AssetManifest]:
    """Return all manifests whose ``family`` or ``family_aliases`` match."""
    family_lower = family.lower()
    matches: list[AssetManifest] = []
    for manifest in load_assets(assets_dir).values():
        if manifest.family.lower() == family_lower:
            matches.append(manifest)
            continue
        if any(a.lower() == family_lower for a in manifest.family_aliases):
            matches.append(manifest)
    return matches


def get_asset_path(asset_id: str, assets_dir: Path | None = None) -> Optional[Path]:
    """
    Return the directory containing ``asset.pptx`` for ``asset_id``,
    or ``None`` if the asset is not registered.

    When ``assets_dir`` is supplied, a one-off scan of that directory is
    performed (no cache pollution). Otherwise the cached default-dir
    index is used.
    """
    if assets_dir is not None:
        _, paths = _scan(assets_dir)
        return paths.get(asset_id)

    load_assets()
    if _path_index is None:
        return None
    return _path_index.get(asset_id)


def count(assets_dir: Path | None = None) -> int:
    """Number of registered manifests."""
    return len(load_assets(assets_dir))
