from pydantic import BaseModel, Field
from canonical_formatter.llm import get_llm, get_structured_llm
from canonical_formatter.schemas.requirement import (
    Requirement, ValidationIssue, ValidationReport, CanonicalRequirementSet
)


class DependencyLink(BaseModel):
    requirement_id: str = Field(description="The requirement that has a dependency")
    depends_on: list[str] = Field(
        default_factory=list,
        description="IDs of other requirements this one depends on to be implementable. Empty if none."
    )


class DependencyResult(BaseModel):
    links: list[DependencyLink]


DEPENDENCY_SYSTEM_PROMPT = """You are a systems analyst. Given a list of requirements, \
identify genuine implementation dependencies between them — cases where one requirement \
cannot be built or makes no sense without another already existing.

Rules:
- Only report a dependency if it is clearly implied by the requirements' content \
(e.g. "reset password via email" depends on a requirement about sending emails, if one exists).
- Do not invent dependencies between unrelated requirements.
- Most requirements will have zero dependencies — that is expected and correct.
- Only include requirements in the output that have at least one real dependency.
"""


def infer_dependencies(requirements: list[Requirement]) -> dict[str, list[str]]:
    """Returns a mapping of requirement_id -> list of requirement_ids it depends on."""
    if len(requirements) < 2:
        return {}

    structured_llm = get_structured_llm(DependencyResult)
    
    summary = "\n".join(
        f"- {r.id} [{r.type.value}]: {r.title} — {r.description}" for r in requirements
    )

    result: DependencyResult = structured_llm.invoke(
        f"{DEPENDENCY_SYSTEM_PROMPT}\n\nRequirements:\n{summary}"
    )
    return {link.requirement_id: link.depends_on for link in result.links}


def transform_to_canonical(
    candidate_requirements: list[dict],
    validation_issues: list[dict],
    project_name: str = "",
) -> CanonicalRequirementSet:
    """
    Main entry point for the Structured Data Transformation Agent.
    Assembles the final canonical schema — the single source of truth for
    every agent downstream.
    """
    requirements = [Requirement.model_validate(r) for r in candidate_requirements]

    report = ValidationReport()
    for issue_dict in validation_issues:
        issue = ValidationIssue.model_validate(issue_dict)
        report.add_issue(issue)

    # Infer and attach dependencies
    try:
        dependency_map = infer_dependencies(requirements)
        for req in requirements:
            if req.id in dependency_map:
                req.dependencies = dependency_map[req.id]
    except Exception as e:
        print(f"[Transformation] dependency inference failed: {e}")
    return CanonicalRequirementSet(
        project_name=project_name,
        requirements=requirements,
        validation_report=report,
    )