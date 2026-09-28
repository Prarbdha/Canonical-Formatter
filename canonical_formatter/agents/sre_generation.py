from pydantic import BaseModel, Field
from canonical_formatter.llm import  get_structured_llm
from canonical_formatter.schemas.requirement import CanonicalRequirementSet
from canonical_formatter.schemas.srs import SRSDocument, UseCase, TraceabilityEntry


class AcceptanceCriteriaEntry(BaseModel):
    requirement_id: str
    criteria: list[str] = Field(
        description="2-4 concrete, testable acceptance criteria for this requirement"
    )


class SREGenerationLLM(BaseModel):
    project_title: str = Field(
        description="A concise 2-6 word title in Title Case naming the system these "
                    "requirements describe, based on what it does "
                    "(e.g. 'User Authentication and Email Service'). "
                    "Do not use generic words like 'Project', 'System' alone, or 'Untitled'."
    )
    purpose: str = Field(description="1-2 sentence statement of the document's purpose")
    scope: str = Field(description="1-2 sentence statement of what the system does and does not cover")
    constraints: list[str] = Field(
        default_factory=list,
        description="System-wide design/technical constraints implied by the requirements "
                    "(e.g. platform, compliance, integration constraints). Empty if none evident."
    )
    use_cases: list[UseCase] = Field(
        description="One use case per distinct user-facing capability. Each must reference "
                    "the requirement id(s) it relates to in related_requirement_ids."
    )
    acceptance_criteria: list[AcceptanceCriteriaEntry] = Field(
        description="One entry per requirement id, with testable acceptance criteria"
    )


SRE_SYSTEM_PROMPT = """You are a senior software requirements engineer. Given a canonical set \
of validated requirements, produce complete SRS content.

Rules:
- purpose/scope should read like the opening section of a real SRS document.
- constraints should only include things clearly implied by the requirements (e.g. if a \
requirement mentions SMTP, "requires integration with an SMTP provider" is a fair constraint). \
Do not invent constraints not grounded in the requirements.
- Each use case must have a unique id like "UC-001", a clear actor, realistic preconditions, \
a numbered main flow, and must list which requirement id(s) it fulfills.
- Acceptance criteria must be concrete and testable (e.g. "system rejects upload after 3 failed \
password attempts") — not restatements of the requirement text.
- Cover every requirement id with at least one acceptance criteria entry.
- If a criterion needs a number or threshold that is not stated in the requirements, write it as "[ASSUMED: 30 minutes]" so a reviewer can confirm or change it.
- Do not add behavior unrelated to the requirement (e.g. admin unlock flows, dashboards) unless the requirement states it.
"""


def generate_sre_content(canonical_set: CanonicalRequirementSet) -> SRSDocument:
    """
    Main entry point for the SRE Generation Agent.
    Expands the canonical requirement set into full SRS content.
    """
    structured_llm = get_structured_llm(SREGenerationLLM)
   

    requirements_summary = "\n".join(
        f"- {r.id} [{r.type.value}, priority={r.priority.value}]: {r.title} — {r.description}"
        for r in canonical_set.requirements
    )

    result: SREGenerationLLM = structured_llm.invoke(
        f"{SRE_SYSTEM_PROMPT}\n\nProject: {canonical_set.project_name}\n\n"
        f"Requirements:\n{requirements_summary}"
    )

    # Attach acceptance criteria back onto the canonical requirements
    criteria_map = {e.requirement_id: e.criteria for e in result.acceptance_criteria}
    for req in canonical_set.requirements:
        if req.id in criteria_map:
            req.acceptance_criteria = criteria_map[req.id]

    # Build traceability matrix: requirement_id -> use_case_ids referencing it
    trace_map: dict[str, list[str]] = {r.id: [] for r in canonical_set.requirements}
    for uc in result.use_cases:
        for req_id in uc.related_requirement_ids:
            if req_id in trace_map:
                trace_map[req_id].append(uc.id)

    traceability_matrix = [
        TraceabilityEntry(requirement_id=req_id, use_case_ids=uc_ids)
        for req_id, uc_ids in trace_map.items()
    ]

    # Auto-name the project from content, unless the user supplied a real name
    AUTO_NAMES = {"", "untitled project"}
    if canonical_set.project_name.strip().lower() in AUTO_NAMES:
        title = result.project_title.strip().strip('"\'')[:60]
        canonical_set.project_name = title or "Untitled Project"

    return SRSDocument(
        project_name=canonical_set.project_name,
        purpose=result.purpose,
        scope=result.scope,
        constraints=result.constraints,
        use_cases=result.use_cases,
        traceability_matrix=traceability_matrix,
    )