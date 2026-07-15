"""
Reusable consulting story templates.

Story templates define the expected narrative spine for a presentation type.
They are deliberately client-agnostic: Microsoft Procurement, Toyota
Manufacturing, and Unilever HR can all instantiate the same Transformation
Proposal template with different enterprise context.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StoryTemplateRole:
    canonical_role: str
    display_role: str
    visualization_type: str
    purpose: str
    required: bool = True


@dataclass(frozen=True)
class StoryTemplate:
    presentation_type: str
    narrative: str
    roles: tuple[StoryTemplateRole, ...]


TRANSFORMATION_PROPOSAL = StoryTemplate(
    presentation_type="Transformation Proposal",
    narrative=(
        "Executive Summary -> Current State -> Case for Change -> Future State -> "
        "Capabilities / Use Cases -> Business Benefits -> Roadmap -> KPIs -> Risks -> Next Steps"
    ),
    roles=(
        StoryTemplateRole(
            "executive summary",
            "Executive Summary",
            "Executive Summary",
            "Summarize the recommendation, value at stake, and decisions required.",
        ),
        StoryTemplateRole(
            "current state",
            "Current State",
            "Process Flow",
            "Describe the current operating process and baseline friction.",
        ),
        StoryTemplateRole(
            "case_for_change",
            "Case for Change",
            "Matrix",
            "Explain why the organization must act now and what is at risk.",
        ),
        StoryTemplateRole(
            "future state",
            "Future State",
            "Capability Map",
            "Describe the target operating model and enabling capabilities.",
        ),
        StoryTemplateRole(
            "ai use cases",
            "Capabilities / Use Cases",
            "Use Case Portfolio",
            "Prioritize capabilities or use cases by value, feasibility, and impact.",
        ),
        StoryTemplateRole(
            "business benefits",
            "Business Benefits",
            "Benefits Stack",
            "Structure the value case across cost, speed, compliance, and performance.",
        ),
        StoryTemplateRole(
            "implementation roadmap",
            "Implementation Roadmap",
            "Roadmap",
            "Sequence phases, milestones, dependencies, and workstreams.",
        ),
        StoryTemplateRole(
            "kpis for success",
            "KPIs for Success",
            "KPI Dashboard",
            "Define the metrics used to track transformation success.",
        ),
        StoryTemplateRole(
            "implementation risks",
            "Risks & Mitigations",
            "Risk Matrix",
            "Surface key implementation risks and practical mitigations.",
        ),
        StoryTemplateRole(
            "next steps",
            "Next Steps / Decisions",
            "Board Decisions",
            "Clarify immediate actions, accountable owners, timing, and decisions.",
        ),
    ),
)


BOARD_UPDATE = StoryTemplate(
    presentation_type="Board Update",
    narrative="Executive Summary -> Progress -> Decisions -> Risks -> Impact -> Next Steps",
    roles=(
        StoryTemplateRole("executive summary", "Executive Summary", "Executive Summary", "Summarize status and decisions required."),
        StoryTemplateRole("progress", "Progress Since Last Update", "Timeline", "Show progress, milestones, and unresolved gaps."),
        StoryTemplateRole("decisions", "Key Decisions", "Board Decisions", "Clarify decisions required from the board."),
        StoryTemplateRole("implementation risks", "Risks / Issues", "Risk Matrix", "Surface material risks and mitigations."),
        StoryTemplateRole("business_impact", "Financial / Operational Impact", "KPI Dashboard", "Quantify impact and performance movement."),
        StoryTemplateRole("next steps", "Next Steps", "Board Decisions", "Define next actions, owners, and timing."),
    ),
)


OPERATING_MODEL_REVIEW = StoryTemplate(
    presentation_type="Operating Model Review",
    narrative="Executive Summary -> Current Model -> Pain Points -> Target Model -> Gaps -> Governance -> Roadmap -> KPIs -> Decisions",
    roles=(
        StoryTemplateRole("executive summary", "Executive Summary", "Executive Summary", "Summarize the operating model recommendation."),
        StoryTemplateRole("current state", "Current Operating Model", "Process Flow", "Describe the current model and ways of working."),
        StoryTemplateRole("case_for_change", "Pain Points", "Matrix", "Identify structural pain points and business impact."),
        StoryTemplateRole("future state", "Target Operating Model", "Capability Map", "Describe the target model and required capabilities."),
        StoryTemplateRole("capability_gaps", "Capability Gaps", "Matrix", "Show gaps between current and target capabilities."),
        StoryTemplateRole("governance", "Governance Model", "Operating Model", "Clarify decision rights, forums, and accountabilities."),
        StoryTemplateRole("implementation roadmap", "Implementation Roadmap", "Roadmap", "Sequence implementation phases and dependencies."),
        StoryTemplateRole("kpis for success", "KPIs", "KPI Dashboard", "Define success metrics."),
        StoryTemplateRole("next steps", "Decisions Required", "Board Decisions", "Clarify decisions and next actions."),
    ),
)


_TEMPLATES = {
    TRANSFORMATION_PROPOSAL.presentation_type.lower(): TRANSFORMATION_PROPOSAL,
    BOARD_UPDATE.presentation_type.lower(): BOARD_UPDATE,
    OPERATING_MODEL_REVIEW.presentation_type.lower(): OPERATING_MODEL_REVIEW,
}


def get_story_template(presentation_type: str) -> StoryTemplate:
    key = (presentation_type or "").lower()
    return _TEMPLATES.get(key, TRANSFORMATION_PROPOSAL)


def find_story_template(presentation_type: str) -> StoryTemplate | None:
    key = (presentation_type or "").lower()
    return _TEMPLATES.get(key)
