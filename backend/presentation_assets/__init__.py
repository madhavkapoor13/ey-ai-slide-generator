"""
backend/presentation_assets
===========================
Presentation Asset Library runtime package.

Replaces the legacy drawing renderer with a retrieve-and-populate flow:
the Asset Selector picks a finished, professionally designed PowerPoint
element from the local ``presentation_assets/`` library, the Content
Generator emits manifest-shaped content, and the Asset Populator fills
the asset's placeholders without ever drawing a shape.

Modules:
- ``asset_registry``  — auto-discovery of manifests on disk; lookup/filter.
- ``asset_loader``     — opens .pptx files; enumerates bindable shapes.
- ``asset_selector``  — deterministic metadata scoring (Sprint C).
- ``asset_populator`` — fills placeholders, appends slide (Sprint E).
- ``asset_inspector`` — shape analysis -> manifest draft (Sprint B).
"""