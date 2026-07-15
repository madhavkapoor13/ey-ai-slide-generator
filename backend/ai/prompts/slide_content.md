# Consulting Slide Content Generator

Generate a single slide's content from a SlidePlan, IntentResult, EnterpriseContext, ProcessResult, and DomainKnowledge.

The SlidePlan tells you the consulting role of this slide, its purpose, and its position in the deck narrative. Use it to shape the content so the slide earns its place in the deck.

## SlidePlan context

You will receive:

- `slide_role`: the consulting role of the slide (e.g., `Executive Summary`, `Current State`, `Opportunities`, `Future State`, `Roadmap`, `Next Steps`).
- `purpose`: one sentence describing what this slide must communicate.
- `slide_number`: the 1-indexed position of this slide in the deck.
- `dependencies`: slide roles that logically come before this slide.
- `visualization_type`: the recommended semantic visualization.

Adapt the generated content to the `slide_role`:

- **Executive Summary**: Lead with the headline conclusion. Summarize the deck's single most important message and the decision required.
- **Current State**: Describe the present operating model and baseline challenges.
- **Opportunities**: Identify improvement areas and value drivers.
- **Future State**: Articulate the target operating model or vision.
- **Roadmap**: Outline sequencing and key milestones.
- **Next Steps**: Define immediate actions, owners, and decision points.
- **Implementation Risks**: Emit only `risks` (each with `quadrant` = `{impact, likelihood}` values `Low`/`Medium`/`High`). Do NOT include mitigations in the same array. When mitigations are wanted, emit `metadata.mitigations` as `[{risk, mitigation}]`.
- **Business Benefits**: Separate cost, speed, compliance, and supplier-performance value. Avoid generic benefit labels.
- **AI Use Cases**: For each use case, name the procurement workflow impacted, the AI capability, and the business outcome.
- **KPIs for Success**: Use procurement outcome metrics, not maturity labels. Include a target direction or threshold only when grounded or clearly illustrative.
- **Other roles**: Follow the same consulting principles and align content to the stated `purpose`.

## Base fields by slide role

Emit `stages` and `pain_points` **only** when:

- `slide_role` is `Current State`, `Process Flow`, or `Operating Model`, **or**
- `visual_pattern` is `IG-03`.

For all other roles, omit `stages` and `pain_points` and rely on the pattern-native field matching the supplied `visual_pattern`.

Always emit `title`, `subtitle`, `description`, `executive_summary`, and `metadata` — downstream validators and fallback renderers rely on them.

## Grounding hierarchy

Use sources in this priority order when they conflict:

1. **EnterpriseContext** — verified public company facts.
2. **ProcessResult** — mapped enterprise process and stages.
3. **DomainKnowledge** — curated consulting concepts for the business function.
4. **Model prior knowledge** — only when the above are silent.

## Visual pattern awareness

When a visual pattern is provided in the input (`visual_pattern.pattern_id`), the output must also include pattern-native fields that the renderer can consume directly. A pattern-specific instruction will be prepended to this prompt when applicable; prioritize that instruction over the generic six-stage shape below.

Common pattern-native fields (include only the field matching the supplied pattern):

- **CL-01** / **CL-02** / **CL-06** → `cards`: array of `{title, description}` cards. CL-01 expects 4 cards; CL-02 and CL-06 expect 3.
- **CL-03** → `kpis`: array of `{label, value, trend, description}`.
- **CL-04** / **CL-05** → `columns`: array of two `{label, items}` columns. CL-04 items are `{name, text}`; CL-05 items are `{text}`.
- **IG-01** → `events`: array of `{title, description, date}` timeline events.
- **IG-02** → `phases`: array of `{name, duration, deliverables}` roadmap phases.
- **IG-03** → `steps`: array of `{name, description, owner}` process steps.
- **IG-04** → `cells`: array of `{value}` matrix cells, or `rows` with nested `cells`.
- **IG-05** → `journey_stages`: array of `{name, touchpoints, pain_point, opportunity}`.
- **IG-06** → `domains`: array of `{name, capabilities}` capability domains, where `capabilities` is a list of `{name}` objects.

Always continue to emit the base fields (`title`, `subtitle`, `description`, `executive_summary`, `metadata`) because downstream validators and fallback renderers rely on them. Emit `stages` and `pain_points` only for the process roles named above (Current State, Process Flow, Operating Model) or when `visual_pattern` is `IG-03`.

## Output shape

Return JSON only. No markdown, no explanation, no prose outside JSON.

```json
{
  "title": "Slide Role",
  "subtitle": "Company Function — concrete scope of this slide",
  "description": "The single headline finding or message this slide must communicate to the board.",
  "executive_summary": "Sentence one. Sentence two.",
  "stages": [
    {
      "label": "Enterprise Stage Name",
      "activities": [
        "Validate supplier quotations",
        "Approve purchase requisitions",
        "Monitor inventory availability",
        "Execute invoice reconciliation",
        "Govern workflow exceptions"
      ]
    }
  ],
  "pain_points": [
    {
      "stage": "Enterprise Stage Name",
      "text": "Problem statement creates business impact."
    }
  ],
  "metadata": {
    "company": "Company",
    "industry": "Industry",
    "process": "Process name",
    "slide_role": "Slide Role",
    "slide_number": "1"
  }
}
```

## Constraints

- Generate exactly two concise sentences for `executive_summary`.
- Never use placeholder/default labels such as `Text`, `Item 1`, `Step 1`, `Step 2`, `Phase 1`, `Placeholder`, `TBD`, or `N/A`.
- Roadmap phase names must be named consulting phases such as `Diagnose`, `Design`, `Pilot`, `Scale`, or equivalent client-specific names; never generic step labels.
- Risk slide labels must be real implementation risks and should pair naturally with mitigation metadata.
- Next-step slides must include concrete actions, accountable owner groups, and timing.
- `subtitle` must be a real, board-facing subtitle (e.g. "Microsoft Procurement — Target Operating Model"). It must NOT echo the `purpose` field or contain phrases like "purpose of this slide", "detail", "outline", "articulate", or "communicate".
- `description` must state the headline finding or message itself. It must NOT be meta-text such as "This slide outlines...", "This slide describes...", or "One-sentence description of this slide's message".
- When stages are required: emit 4–7 stages, 3–6 verb-first activities each, 3–7 words per activity.
- When pain points are required: emit one pain point per stage with a business impact.
- Numerics are permitted only when explicitly grounded in EnterpriseContext facts. Otherwise, you may include illustrative numerics; the downstream pipeline will tag them `(illustrative)`.
- Do not include layout, color, font, coordinate, or rendering instructions.
