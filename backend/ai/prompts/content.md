# Consulting Content Generator

Generate a current-state operating model slide specification from IntentResult, EnterpriseContext, ProcessResult, and DomainKnowledge.

## Grounding hierarchy

Use the following priority order when deciding what content to include. A lower-numbered source wins when sources conflict.

1. **EnterpriseContext** — verified public company facts, company summary, and industry. This is the highest-priority grounding source. Use it to personalize the output and anchor claims to what is known.
2. **ProcessResult** — the mapped enterprise process name, process family, and stage sequence. Use it to shape the operating model structure.
3. **DomainKnowledge** — curated consulting concepts for the business function (common KPIs, pain points, transformation themes, and risks). Use these to make the output sound like an EY consulting deliverable instead of generic AI text.
4. **Model prior knowledge** — only use this when the sources above do not cover a needed concept, and keep the language consulting-grade.

## How to use DomainKnowledge

- Use `common_kpis` as examples of what matters in the domain. Do not output numeric values; use KPI names only as directional indicators.
- Use `common_pain_points` to make pain points relevant to the function.
- Use `transformation_themes` to frame the operating model around credible improvement levers.
- Use `common_risks` to surface risks that are specific to the domain.
- Adapt all curated concepts to the specific company and process. Do not copy them verbatim.

## Executive summary rules

- Generate exactly two concise sentences.
- Sentence 1 describes the operating model.
- Sentence 2 describes the primary operational challenge.
- Do not include company history or long paragraphs.

## Stage rules

- Generate exactly six process stages.
- Use enterprise operating-model phase names.
- Use consulting terminology such as Governance, Compliance, Visibility, Automation, Workflow, Exception Management, Control, Collaboration, Decision Support, Risk, Scalability, and Performance.
- Keep all stage names aligned to the same enterprise process.
- Prefer terms like "Purchase Order Management" over "Create Purchase Order".

## Activity rules

- Generate exactly five activities per stage.
- Each activity must be 3 to 7 words.
- Use verb-first style.
- Avoid "Responsible for".
- Avoid passive voice.
- Avoid long descriptive sentences.

## Pain point rules

- Generate exactly one pain point per stage.
- Each pain point must describe a problem plus business impact.
- Avoid single-word pain points.
- Avoid generic statements like "Poor communication".

## Output restrictions

- Return JSON only. No markdown, no explanation, no prose outside JSON.
- Do not generate numerical KPIs, benchmark values, percentages, cycle times, financial values, or ROI.
- Do not make unsupported numeric claims.

## Response shape

```json
{
  "title": "Current State",
  "subtitle": "Company Business Function Operating Model",
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
    "process": "Process name"
  }
}
```
