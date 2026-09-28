from pydantic import BaseModel, Field


class UseCase(BaseModel):
    id: str
    title: str
    actor: str
    preconditions: list[str] = Field(default_factory=list)
    main_flow: list[str] = Field(default_factory=list)
    related_requirement_ids: list[str] = Field(default_factory=list)


class TraceabilityEntry(BaseModel):
    requirement_id: str
    use_case_ids: list[str] = Field(default_factory=list)


class SRSDocument(BaseModel):
    project_name: str
    purpose: str
    scope: str
    constraints: list[str] = Field(default_factory=list)
    use_cases: list[UseCase] = Field(default_factory=list)
    traceability_matrix: list[TraceabilityEntry] = Field(default_factory=list)
    # requirements themselves (with acceptance_criteria now populated)
    # are carried via the CanonicalRequirementSet, not duplicated here