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
- **Other roles**: Follow the same consulting principles and align content to the stated `purpose`.

## Grounding hierarchy

Use sources in this priority order when they conflict:

1. **EnterpriseContext** — verified public company facts.
2. **ProcessResult** — mapped enterprise process and stages.
3. **DomainKnowledge** — curated consulting concepts for the business function.
4. **Model prior knowledge** — only when the above are silent.

## Output shape

Return JSON only. No markdown, no explanation, no prose outside JSON.

```json
{
  "title": "Slide Role",
  "subtitle": "Company Function — purpose of this slide",
  "description": "One-sentence description of this slide's message.",
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
- Generate exactly six process stages.
- Generate exactly five activities per stage, 3–7 words each, verb-first.
- Generate exactly one pain point per stage with a business impact.
- Do not generate numerical KPIs, benchmark values, percentages, cycle times, financial values, or ROI.
- Do not make unsupported numeric claims.
- Do not include layout, color, font, coordinate, or rendering instructions.
