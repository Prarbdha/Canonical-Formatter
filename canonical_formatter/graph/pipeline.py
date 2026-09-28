import time

from langgraph.graph import StateGraph, END
from canonical_formatter.graph.state import PipelineState
from canonical_formatter.agents.ingestion import ingest
from canonical_formatter.agents.extraction import extract_requirements
from canonical_formatter.agents.validation import validate_requirements
from canonical_formatter.agents.transformation import transform_to_canonical
from canonical_formatter.agents.sre_generation import generate_sre_content
from canonical_formatter.agents.formatting import write_all


def ingestion_node(state: PipelineState) -> PipelineState:
    print("[Ingestion] running")
    try:
        state["normalized_text"] = ingest(
            state["raw_input_path"], state["input_type"]
        )
    except Exception as e:
        state.setdefault("errors", []).append(f"Ingestion error: {e}")
        state["normalized_text"] = ""
    return state

def extraction_node(state: PipelineState) -> PipelineState:
    print("[Extraction] running")
    attempts = state.get("extraction_attempts", 0)
    if attempts > 0:
        time.sleep(5)
    state["extraction_attempts"] = attempts + 1
    try:
        requirements = extract_requirements(state["normalized_text"])
        state["candidate_requirements"] = [r.model_dump() for r in requirements]
    except Exception as e:
        state.setdefault("errors", []).append(f"Extraction error: {e}")
        state["candidate_requirements"] = []
    return state

def validation_node(state: PipelineState) -> PipelineState:
    print("[Validation] running")
    requirements = state.get("candidate_requirements", [])
    attempts = state.get("extraction_attempts", 0)

    if not requirements and state.get("normalized_text", "").strip():
        if attempts >= 2:
            state.setdefault("errors", []).append(
                "Extraction failed after 2 attempts (likely rate limit or API error). Stopping."
            )
            state["needs_reextraction"] = False
            state["validation_issues"] = []
            return state
        state["needs_reextraction"] = True
        state["validation_issues"] = []
        state["extraction_attempts"] = attempts + 1
        return state

    # ... rest unchanged (try/except validate_requirements block) ...

def transformation_node(state: PipelineState) -> PipelineState:
    print("[Transformation] running")
    try:
        canonical_set = transform_to_canonical(
            candidate_requirements=state.get("candidate_requirements", []),
            validation_issues=state.get("validation_issues", []),
            project_name=state.get("project_name", ""),
        )
        state["canonical_set"] = canonical_set
    except Exception as e:
        state.setdefault("errors", []).append(f"Transformation error: {e}")
        state["canonical_set"] = None
    return state


def sre_generation_node(state: PipelineState) -> PipelineState:
    print("[SRE Generation] running")
    canonical_set = state.get("canonical_set")
    if canonical_set is None or not canonical_set.requirements:
        state.setdefault("errors", []).append("SRE Generation skipped: no requirements available")
        state["srs_content"] = None
        return state
    try:
        state["srs_content"] = generate_sre_content(canonical_set)
    except Exception as e:
        state.setdefault("errors", []).append(f"SRE Generation error: {e}")
        state["srs_content"] = None
    return state


def formatting_node(state: PipelineState) -> PipelineState:
    print("[Formatting] running")
    canonical_set = state.get("canonical_set")
    srs = state.get("srs_content")
    if canonical_set is None or srs is None:
        state.setdefault("errors", []).append("Formatting skipped: missing canonical set or SRS content")
        state["final_document_path"] = ""
        return state
    try:
        paths = write_all(
            canonical_set, srs,
            state.get("output_format", "ieee_srs"),
            state.get("export_types", ["md", "docx", "pdf"]),
        )
        state["final_document_paths"] = {k: str(v) for k, v in paths.items()}
        state["final_document_path"] = str(paths["md"])
    except Exception as e:
        state.setdefault("errors", []).append(f"Formatting error: {e}")
        state["final_document_path"] = ""
    return state


def route_after_validation(state: PipelineState) -> str:
    """Conditional edge: loop back to extraction if critical issues found."""
    if state.get("needs_reextraction"):
        return "extraction"
    return "transformation"


def build_pipeline() -> StateGraph:
    graph = StateGraph(PipelineState)

    graph.add_node("ingestion", ingestion_node)
    graph.add_node("extraction", extraction_node)
    graph.add_node("validation", validation_node)
    graph.add_node("transformation", transformation_node)
    graph.add_node("sre_generation", sre_generation_node)
    graph.add_node("formatting", formatting_node)

    graph.set_entry_point("ingestion")
    graph.add_edge("ingestion", "extraction")
    graph.add_edge("extraction", "validation")
    graph.add_conditional_edges(
        "validation",
        route_after_validation,
        {"extraction": "extraction", "transformation": "transformation"},
    )
    graph.add_edge("transformation", "sre_generation")
    graph.add_edge("sre_generation", "formatting")
    graph.add_edge("formatting", END)

    return graph.compile()