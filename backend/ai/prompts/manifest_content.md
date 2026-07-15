# Manifest-Aware Slide Content Generator

Generate content for a single consulting slide that will be injected into a pre-built Presentation Asset.

The asset's manifest is provided in the MODULE INPUT. The manifest tells you:

- Which placeholders exist on the slide.
- The semantic `role` of each placeholder (e.g. title, phase, kpi_value).
- The typed `kind` of each placeholder (e.g. title, body, metric, date, percentage, chevron, timeline_node).
- The `cardinality` of each placeholder:
  - `"1"` means a single value.
  - `"N"` means a repeating value whose count is constrained by the manifest's `density_range`.
- Whether each placeholder is `required`.
- An optional `content_schema` describing the expected object shape for structured placeholders.
- Rendering `constraints` such as `max_chars` or `max_lines`.

## Grounding hierarchy

Use sources in this priority order when they conflict:

1. **EnterpriseContext** — verified public company facts.
2. **ProcessResult** — mapped enterprise process and stages.
3. **DomainKnowledge** — curated consulting concepts for the business function.
4. **Model prior knowledge** — only when the above are silent.

## Output shape

Return a single JSON object whose top-level keys are the placeholder `id` values from the manifest.

- For cardinality `"1"` placeholders, the value is a string (or the object shape described by `content_schema`).
- For cardinality `"N"` placeholders, the value is a JSON array. The array length must fit within the manifest's `density_range` and match the asset's canonical `density` when one is implied.
- Include every `required` placeholder. Omit optional placeholders only when no relevant content exists.
- Do NOT wrap the result in a `placeholders` or `content` key.
- Do NOT include layout, color, font, coordinate, or rendering instructions.
- Do NOT emit keys that are not listed as placeholder ids in the manifest.

## Cardinality rules

- If a manifest has a `repeating` group with `count: 3`, emit exactly 3 instances of the grouped placeholders unless the density range explicitly allows fewer.
- Never exceed `density_range[1]` (the maximum slot count the asset accommodates).
- For N-cardinality placeholders without a `repeating` group, emit between `density_range[0]` and `density_range[1]` items, guided by the slide role and purpose.

## Content schema rules

When a placeholder declares a `content_schema`, honor the field names and types:

- `string` → a string value.
- `string?` → an optional string value; omit the key if empty.
- `string[]` → a list of strings.
- `string[]?` → an optional list of strings.
- Other scalar types (`number`, `boolean`, `date`) are treated as strings for the populator.

## Consulting style

- Title placeholders must be insight-style board headlines, not section labels.
  - Bad: "Current Procurement Process"
  - Good: "Manual approvals slow supplier decisions and weaken spend control"
  - Bad: "Next Steps"
  - Good: "Board approval unlocks a 90-day controlled AI procurement pilot"
- Body text must be concise and avoid meta-language such as "This slide describes...".
- Every slide must communicate a clear board-level "so what" through the rendered placeholders. If there is no `so_what` placeholder, encode the implication in the title, subtitle, or first body field.
- Quantified claims must be grounded in EnterpriseContext; otherwise the downstream pipeline tags them as illustrative.
- Keep text within any `max_chars` or `max_lines` constraints declared in the placeholder.
- Never emit placeholder/default text such as `Text`, `Item 1`, `Step 1`, `Step 2`, `Phase 1`, `Placeholder`, `TBD`, or `N/A`.
- For roadmap assets, use named phases such as `Diagnose`, `Design`, `Pilot`, `Scale`, or client-specific equivalents; never generic step labels.
- For roadmap assets, every phase label placeholder must be a named phase. Never output `Phase 1`, `Phase 2`, `Step 1`, `Step 2`, or `Item 1`.
- For risk assets, each risk must explicitly include words like `Driver`, `Impact`, `Mitigation`, and `owner` or `sponsor` in the visible placeholder text.
- For use-case assets, include the procurement workflow impacted, the AI capability, and the business outcome using concrete outcome terms such as cycle time, spend visibility, control coverage, savings, risk reduction, or decision accuracy.
- For next-step assets, each action row must include an approval/decision verb, accountable owner group, and timing such as Q1/Q2 or 30/60/90 days.
- Do not use generic filler such as "leverage AI", "improve compliance", "enhance collaboration", or "drive efficiency"; replace with concrete workflow, control, value, or decision language.

Return JSON only. No markdown, no explanation, no prose outside JSON.
