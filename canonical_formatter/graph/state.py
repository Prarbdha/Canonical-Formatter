from typing import TypedDict, Optional, Literal
from canonical_formatter.schemas.requirement import CanonicalRequirementSet
from canonical_formatter.schemas.srs import SRSDocument

class PipelineState(TypedDict, total=False):
    # Input
    raw_input_path: str
    input_type: Literal["text", "pdf", "image"]

    # After Ingestion Agent
    normalized_text: str

    # After Extraction Agent
    candidate_requirements: list[dict]

    # After Validation Agent
    validation_issues: list[dict]
    needs_reextraction: bool

    # After Transformation Agent
    canonical_set: Optional[CanonicalRequirementSet]

    # After SRE Generation Agent
    srs_content: Optional[dict]

    # Output choice + final result
    output_format: Literal["ieee_srs", "tech_report", "readme", "project_doc"]
    final_document_path: str

    # Error tracking
    errors: list[str]
    extraction_attempts: int

    srs_content: Optional[SRSDocument]
    project_name: str

    export_types: list[str]
    final_document_paths: dict