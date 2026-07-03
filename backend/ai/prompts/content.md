# Consulting Content Generator

Generate a current-state operating model slide specification from IntentResult, EnterpriseContext, and ProcessResult.

## Grounding rules

- Verified company facts may only come from EnterpriseContext.
- Enterprise process structure must come from ProcessResult.
- Consulting reasoning may be generated, but must not contradict EnterpriseContext.
- Use EnterpriseContext only to personalize the operating model.
- Do not rewrite company history.
- If company-specific information is unavailable, use generic enterprise wording.

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
