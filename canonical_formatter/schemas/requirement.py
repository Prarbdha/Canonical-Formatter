from pydantic import BaseModel, Field
from typing import Literal, Optional
from enum import Enum


class RequirementType(str, Enum):
    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"


class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IssueType(str, Enum):
    AMBIGUOUS = "ambiguous"
    MISSING_INFO = "missing_info"
    INCONSISTENT = "inconsistent"
    CONFLICT = "conflict"
    DUPLICATE = "duplicate"


class SourceSpan(BaseModel):
    """Traceability back to the original raw input."""
    document_id: str
    start_char: int
    end_char: int
    raw_text: str


class ValidationIssue(BaseModel):
    requirement_id: str
    issue_type: IssueType
    description: str
    related_requirement_ids: list[str] = Field(default_factory=list)


class Requirement(BaseModel):
    id: str
    type: RequirementType
    title: str
    description: str
    priority: Priority = Priority.MEDIUM
    source_span: Optional[SourceSpan] = None
    dependencies: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    flagged_issues: list[str] = Field(default_factory=list)  # ValidationIssue ids


class ValidationReport(BaseModel):
    issues: list[ValidationIssue] = Field(default_factory=list)
    is_clean: bool = True

    def add_issue(self, issue: ValidationIssue):
        self.issues.append(issue)
        self.is_clean = False


class CanonicalRequirementSet(BaseModel):
    """The single source of truth passed to every downstream agent."""
    project_name: str
    requirements: list[Requirement] = Field(default_factory=list)
    validation_report: ValidationReport = Field(default_factory=ValidationReport)

    def get_functional(self) -> list[Requirement]:
        return [r for r in self.requirements if r.type == RequirementType.FUNCTIONAL]

    def get_non_functional(self) -> list[Requirement]:
        return [r for r in self.requirements if r.type == RequirementType.NON_FUNCTIONAL]