# backend/modules/__init__.py
"""
Phase 2 AI Orchestration Modules
=================================
Each module in this package has a single responsibility and exposes
exactly one public function with typed inputs and outputs.

Module map
----------
intent          → extract_intent()       — classifies user intent
context         → build_context()        — enriches with enterprise knowledge
process_mapper  → identify_process()     — maps to a business process structure
content_generator → generate_content()  — produces the SlideSpec payload
validator       → validate_content()     — quality-gates the spec before rendering
"""
