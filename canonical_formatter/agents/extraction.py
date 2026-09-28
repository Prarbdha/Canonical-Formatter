from pydantic import BaseModel, Field
from canonical_formatter.llm import get_structured_llm
from canonical_formatter.schemas.requirement import (
    Requirement, RequirementType, Priority, SourceSpan
)


# --- LLM-facing schema: only the content the model needs to produce ---
class ExtractedRequirementLLM(BaseModel):
    title: str = Field(description="Short 3-8 word summary of the requirement")
    description: str = Field(description="Full requirement statement, reworded clearly if needed")
    type: RequirementType
    priority: Priority
    source_sentence: str = Field(
        description="The exact sentence or phrase from the input text this requirement was derived from"
    )


class ExtractionResult(BaseModel):
    requirements: list[ExtractedRequirementLLM]


EXTRACTION_SYSTEM_PROMPT = """You are a requirements analyst. Read the input text and extract \
every distinct functional and non-functional requirement.

Rules:
- A FUNCTIONAL requirement is any behavior the system performs or enforces, including \
security behaviors (lockouts, logging, notifications, validation).
- A NON-FUNCTIONAL requirement is a measurable quality of how well the system works: \
performance targets, capacity, availability, compliance, usability, portability.
- When unsure, ask: "Can this be described as the system doing something?" If yes, it is functional.
- Split compound sentences into separate requirements if they describe more than one thing.
- Do not invent requirements that aren't stated or clearly implied in the text.
- For source_sentence, copy the exact original wording from the input text (not reworded), \
so it can be located later.
- Assign priority based on language cues (e.g. "must"/"shall" = high, "should" = medium, \
"may"/"could" = low) when not explicitly stated.
"""


def find_source_span(source_sentence: str, normalized_text: str, doc_id: str) -> SourceSpan | None:
    """Locate the source sentence in the normalized text for traceability."""
    idx = normalized_text.find(source_sentence.strip())
    if idx == -1:
        # fallback: try a shorter fragment match
        fragment = source_sentence.strip()[:30]
        idx = normalized_text.find(fragment)
        if idx == -1:
            return None
    return SourceSpan(
        document_id=doc_id,
        start_char=idx,
        end_char=idx + len(source_sentence.strip()),
        raw_text=source_sentence.strip(),
    )


def extract_requirements(normalized_text: str, doc_id: str = "input_doc") -> list[Requirement]:
    """
    Main entry point for the Requirement Extraction Agent.
    Returns a list of fully-formed Requirement objects with generated IDs.
    """
    structured_llm = get_structured_llm(ExtractionResult)
    result = structured_llm.invoke(f"{EXTRACTION_SYSTEM_PROMPT}\n\nInput text:\n{normalized_text}")

    result: ExtractionResult = structured_llm.invoke(
        f"{EXTRACTION_SYSTEM_PROMPT}\n\nInput text:\n{normalized_text}"
    )

    requirements: list[Requirement] = []
    func_count = 0
    nonfunc_count = 0

    for item in result.requirements:
        if item.type == RequirementType.FUNCTIONAL:
            func_count += 1
            req_id = f"FR-{func_count:03d}"
        else:
            nonfunc_count += 1
            req_id = f"NFR-{nonfunc_count:03d}"

        span = find_source_span(item.source_sentence, normalized_text, doc_id)

        requirements.append(Requirement(
            id=req_id,
            type=item.type,
            title=item.title,
            description=item.description,
            priority=item.priority,
            source_span=span,
        ))

    return requirements