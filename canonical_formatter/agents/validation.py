from pydantic import BaseModel, Field
from canonical_formatter.llm import get_llm, get_structured_llm
from canonical_formatter.schemas.requirement import IssueType


class ValidationIssueLLM(BaseModel):
    requirement_id: str = Field(description="The id of the requirement this issue relates to")
    issue_type: IssueType
    description: str = Field(description="Clear explanation of the issue and why it matters")
    related_requirement_ids: list[str] = Field(
        default_factory=list,
        description="Other requirement ids involved, only for conflict/duplicate/inconsistent issues"
    )


class ValidationResult(BaseModel):
    issues: list[ValidationIssueLLM]


VALIDATION_SYSTEM_PROMPT = """You are a requirements quality reviewer. You will be given a \
list of extracted requirements (id, type, title, description, priority). Review them \
holistically — not one at a time in isolation — and identify quality issues.

Look for:
- AMBIGUOUS: vague or unquantified language (e.g. "fast", "secure", "user-friendly") with no \
measurable acceptance criteria.
- MISSING_INFO: a requirement that is incomplete or lacks necessary detail to be implementable \
(e.g. a performance requirement with no target metric, an NFR with no measurable threshold).
- INCONSISTENT: two requirements that use conflicting terminology or make contradictory \
implicit assumptions about the same feature.
- CONFLICT: two requirements that directly contradict each other's stated behavior.
- DUPLICATE: two requirements that describe the same thing in different words.

Only report real issues. Do not invent problems that aren't there. If a requirement is clear \
and complete, do not flag it. Reference requirement ids exactly as given.
"""


def validate_requirements(requirements: list[dict]) -> ValidationResult:
    """
    Main entry point for the Validation Agent.
    Takes the list of requirement dicts (as produced by Extraction) and returns
    a structured list of validation issues.
    """
    if not requirements:
        return ValidationResult(issues=[])

    structured_llm = get_structured_llm(ValidationResult)
    
    requirements_summary = "\n".join(
        f"- {r['id']} [{r['type']}, priority={r['priority']}]: {r['title']} — {r['description']}"
        for r in requirements
    )

    result: ValidationResult = structured_llm.invoke(
        f"{VALIDATION_SYSTEM_PROMPT}\n\nRequirements:\n{requirements_summary}"
    )
    return result