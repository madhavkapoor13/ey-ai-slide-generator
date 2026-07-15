# Visual Pattern Library

> **Sprint V1 — Analysis & Design Only**  
> This document and the accompanying JSON metadata define a reusable visual pattern library for the EY AI Slide Generator. No renderer, orchestrator, or template-engine code is changed in this sprint.

---

## 1. Philosophy

The AI should never think in terms of *"Slide 3"* or *"the third layout in Templates.pptx"*. It should think in terms of reusable visual communication patterns:

- **Four Insight Cards**
- **Process Flow**
- **Comparison Cards**
- **Roadmap**
- **Matrix**
- **Capability Map**

A template file is only one *example* of a pattern. The pattern is the abstract structure: how many items, how they relate, what visual devices are allowed, and what content each slot accepts. The Visual Pattern Library decouples *what the AI wants to say* from *how it ends up drawn on a slide*.

Benefits:

- **Reusability** — one pattern can be rendered by many future templates.
- **Composability** — complex decks combine simple, well-understood patterns.
- **Testability** — patterns have explicit constraints (min/max items, supported content types) that can be validated before rendering.
- **Template independence** — the AI does not need to know EY fonts, colors, or exact coordinates.

---

## 2. Terminology

| Term | Definition | Example |
|------|------------|---------|
| **Template** | A concrete PowerPoint file containing branded layouts, colors, fonts, and placeholder shapes. | `Templates.pptx` from EY |
| **Visual Pattern** | A reusable abstraction that describes *how* information is communicated visually, independent of any template. | **Four Insight Cards**, **Process Flow**, **Matrix** |
| **Renderer** | Code that takes a pattern + content and draws the actual PowerPoint shapes. | `OperatingModelRenderer`, future `VisualPatternRenderer` |
| **Slide Content** | The raw business content produced by the AI pipeline (title, bullets, facts, process steps, KPIs, etc.). | `{"title": "Procure-to-Pay", "stages": [...]}` |
| **SlidePlan** | A planning artifact from the orchestrator that describes the role of a slide in the narrative. | `SlideRole: "Current State"`, `VisualizationType: "Process Flow"` |
| **Visual Planner** | A future component that maps a `SlidePlan` + `Slide Content` to a `Visual Pattern`. | (not implemented in this sprint) |

Key distinction:

- The **Visual Planner** decides *which pattern fits the message*.
- The **Renderer** decides *how to draw that pattern*.
- The **Template** decides *the exact branded look and feel*.

---

## 3. Categories

For Sprint V1, the library is intentionally limited to two top-level categories. Frameworks (e.g., maturity models, pyramids, canvases) are out of scope.

### 3.1 Creative Listings

Patterns that present a collection of related ideas as cards, columns, grids, or bars. They emphasize *reading* and *comparison* rather than *spatial relationships*.

Typical traits:

- Items are peers or near-peers.
- Layouts are grids, columns, or horizontal stacks.
- Each item has a title + short description, often with an icon or KPI.

### 3.2 Infographics

Patterns that emphasize *spatial, temporal, or relational structure*. They show how parts connect, sequence, or compare across dimensions.

Typical traits:

- Items have explicit relationships (before/after, center/spoke, row/column, step-to-step).
- Layouts use arrows, axes, matrices, maps, or timelines.
- The structure itself carries meaning.

---

## 4. Pattern Catalog

Full metadata lives in:

- `backend/visual_patterns/creative_patterns.json`
- `backend/visual_patterns/infographic_patterns.json`

### 4.1 Creative Listings

| ID | Name | Purpose | Min / Max Items | Icons | Percentages | Images |
|----|------|---------|-----------------|-------|-------------|--------|
| CL-01 | Four Insight Cards | Four related insights with equal weight | 4 / 4 | Yes | Yes | Yes |
| CL-02 | Three Strategy Cards | Three strategic options, pillars, or themes | 3 / 3 | Yes | Yes | Yes |
| CL-03 | KPI Cards | Prominent numeric metrics or KPIs | 3 / 6 | Yes | Yes | No |
| CL-04 | Comparison Cards | Side-by-side comparison of two item sets | 2 / 8 | Yes | Yes | No |
| CL-05 | Two Column Listing | Compact two-column text comparison | 2 / 10 | Yes | No | No |
| CL-06 | Executive Summary Cards | 3-5 high-level takeaways | 3 / 5 | Yes | Yes | Yes |
| CL-07 | Icon Grid | 6-9 items in a uniform icon grid | 4 / 9 | Yes | No | No |
| CL-08 | Image Grid | 4-6 visual cards with images and captions | 4 / 6 | No | No | Yes |

### 4.2 Infographics

| ID | Name | Purpose | Min / Max Items | Icons | Percentages | Images |
|----|------|---------|-----------------|-------|-------------|--------|
| IG-01 | Timeline | Chronological events on an axis | 3 / 8 | Yes | No | No |
| IG-02 | Roadmap | Phase-based execution plan with milestones | 3 / 12 | Yes | No | No |
| IG-03 | Process Flow | Linear sequence of steps or stages | 3 / 8 | Yes | No | No |
| IG-04 | Matrix | Two-dimensional comparison grid | 4 / 12 | Yes | Yes | No |
| IG-05 | Journey | Stages of a customer or process journey | 4 / 8 | Yes | No | No |
| IG-06 | Capability Map | Hierarchical capability grouping | 6 / 20 | Yes | No | No |
| IG-07 | Pyramid | Hierarchical layers from base to apex | 3 / 5 | Yes | No | No |
| IG-08 | Circular Flow | Cyclical process or feedback loop | 3 / 8 | Yes | No | No |
| IG-09 | Value Chain | End-to-end value-adding activities | 4 / 10 | Yes | No | No |
| IG-10 | Hub and Spoke | Central concept with surrounding elements | 4 / 8 | Yes | No | No |
| IG-11 | Annotated Visual | Callouts overlaid on a central image or diagram | 2 / 6 | Yes | Yes | Yes |

---

## 5. Patterns Observed in the EY Reference Deck

The reference deck (`Templates.pptx`) is treated as a source of visual language, not as a hardcoded template. The slides map to generalized patterns as follows:

| Reference Slide | Observed Structure | Mapped Pattern(s) |
|-----------------|--------------------|-------------------|
| Slide 1 | Title + hero image with three connected insight cards on the right | CL-02 Three Strategy Cards (with optional hero image), IG-11 Annotated Visual |
| Slide 2 | Two columns of four horizontal stat bars with percentages | CL-04 Comparison Cards |
| Slide 3 | Grid of cards on the left + central hub with six radiating items on the right | IG-10 Hub and Spoke (with supporting card grid) |
| Slide 4 | Central image with four callout labels and a bottom CTA banner | IG-11 Annotated Visual |
| Slide 5 | Three vertical rounded cards with header badges and body text | CL-02 Three Strategy Cards |
| Slide 6 | Three vertical pillar cards with circular icons and stacked text | CL-02 Three Strategy Cards |
| Slide 7 | 3×3 table: business opportunities × digital themes × impact KPIs | IG-04 Matrix |
| Slide 8 | 3×2 grid of image cards with captions | CL-08 Image Grid |
| Slide 9 | Gantt-style schedule with activity rows, week columns, and milestone markers | IG-02 Roadmap |

No slide is copied; each is interpreted as an instance of one or more reusable patterns.

---

## 6. Future Architecture Flow

The Visual Pattern Library is the middle layer between AI reasoning and PowerPoint rendering. The intended future flow is:

```
SlidePlan
    │
    ▼
Slide Content  (AI-generated facts, narrative, process, KPIs)
    │
    ▼
Visual Planner  (decides HOW the information should be communicated)
    │
    ▼
Visual Pattern  (selected from the library: e.g., "Matrix", "Roadmap")
    │
    ▼
Template Selector  (chooses a branded template that can express the pattern)
    │
    ▼
Renderer  (draws the pattern using the chosen template's visual language)
    │
    ▼
PowerPoint
```

Responsibilities:

- **Visual Planner** — reads the `SlidePlan` and `Slide Content`, validates item counts and content types, then selects the best `Visual Pattern`. It does not draw anything.
- **Template Selector** — given a `Visual Pattern`, picks a concrete EY or client-branded template that supports that pattern. It does not decide the pattern.
- **Renderer** — consumes the pattern metadata + content + template and emits PowerPoint shapes. It owns coordinates, colors, fonts, and layout mechanics.

### Guiding principle

> **The AI decides what the deck should say. The Visual Planner decides how it should be communicated. The Renderer decides how it looks.**

---

## 7. Out of Scope for This Sprint

The following are intentionally **not** implemented:

- Renderer changes
- Orchestrator / slide-service / content-generator changes
- Frontend changes
- Template loading or template-engine code
- Framework-level patterns (e.g., maturity pyramids as full canvases — individual pyramid infographics are included)
- Automatic pattern selection logic

This sprint produces only the catalog and metadata. Future sprints will consume these JSON files.
