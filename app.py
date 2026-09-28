import time
import uuid
from pathlib import Path

import streamlit as st

from canonical_formatter.agents.formatting import FORMATS, write_all
from canonical_formatter.graph.pipeline import build_pipeline

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

FORMAT_LABELS = {
    "ieee_srs": "IEEE SRS (ISO/IEC/IEEE 29148)",
    "tech_report": "Technical Report",
    "readme": "README",
    "project_doc": "Project Documentation",
}
STEP_LABELS = {
    "ingestion": "1/6  Ingesting input",
    "extraction": "2/6  Extracting requirements",
    "validation": "3/6  Validating requirements",
    "transformation": "4/6  Building canonical schema",
    "sre_generation": "5/6  Generating SRS content",
    "formatting": "6/6  Formatting documents",
}
EXT_TO_TYPE = {".txt": "text", ".md": "text", ".pdf": "pdf",
               ".png": "image", ".jpg": "image", ".jpeg": "image"}
MIME = {
    "md": "text/markdown",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

st.set_page_config(page_title="Canonical Formatter", page_icon="\U0001F4C4", layout="wide")


@st.cache_resource
def get_pipeline():
    return build_pipeline()


def save_input(uploaded, pasted: str):
    """Save the user's input to disk and return (path, input_type)."""
    if uploaded is not None:
        ext = Path(uploaded.name).suffix.lower()
        path = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}{ext}"
        path.write_bytes(uploaded.getbuffer())
        return path, EXT_TO_TYPE[ext]
    path = UPLOAD_DIR / f"pasted_{uuid.uuid4().hex[:8]}.txt"
    path.write_text(pasted, encoding="utf-8")
    return path, "text"


def run_pipeline(path, input_type, project_name, formats, export_types, status):
    app = get_pipeline()
    state = {
        "raw_input_path": str(path),
        "input_type": input_type,
        "output_format": formats[0],
        "export_types": export_types,
        "errors": [],
    }
    if project_name.strip():
        state["project_name"] = project_name.strip()

    final = dict(state)
    for chunk in app.stream(state, stream_mode="updates"):
        for node, update in chunk.items():
            if update:
                final.update(update)
            status.write(f"\u2705 {STEP_LABELS.get(node, node)}")

    canonical, srs = final.get("canonical_set"), final.get("srs_content")
    files = {}
    if canonical is not None and srs is not None:
        for fmt in formats:
            try:
                files[fmt] = write_all(canonical, srs, fmt, export_types)
            except PermissionError:
                final.setdefault("errors", []).append(
                    f"Could not write {fmt}: a file with that name is open in another program. Close it and retry."
                )
    return final, files


def show_results(result: dict, files: dict, elapsed: float):
    canonical, srs = result.get("canonical_set"), result.get("srs_content")
    errors = result.get("errors", [])

    if canonical is None or srs is None or not canonical.requirements:
        st.error("No document could be generated.")
        for e in errors:
            st.code(e[:600])
        return

    st.subheader(canonical.project_name)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Functional", len(canonical.get_functional()))
    c2.metric("Non-functional", len(canonical.get_non_functional()))
    c3.metric("Quality issues", len(canonical.validation_report.issues))
    c4.metric("Time", f"{elapsed:.0f}s")

    if errors:
        with st.expander(f"\u26A0\uFE0F {len(errors)} warning(s) during processing"):
            for e in errors:
                st.code(e[:600])

    st.markdown("### Download")
    for fmt, paths in files.items():
        st.markdown(f"**{FORMAT_LABELS[fmt]}**")
        cols = st.columns(len(paths))
        for col, (ext, p) in zip(cols, paths.items()):
            p = Path(p)
            col.download_button(
                f"\u2B07\uFE0F {ext.upper()}", data=p.read_bytes(), file_name=p.name,
                mime=MIME[ext], key=f"dl_{fmt}_{ext}", use_container_width=True,
            )

    tab_req, tab_issues, tab_uc, tab_prev = st.tabs(
        ["Requirements", "Validation issues", "Use cases", "Document preview"]
    )
    with tab_req:
        st.dataframe(
            [{
                "ID": r.id, "Type": r.type.value, "Title": r.title,
                "Priority": r.priority.value,
                "Depends on": ", ".join(r.dependencies) or "-",
                "Issues": len(r.flagged_issues),
            } for r in canonical.requirements],
            use_container_width=True, hide_index=True,
        )
    with tab_issues:
        issues = canonical.validation_report.issues
        if not issues:
            st.success("No ambiguities, conflicts or missing information detected.")
        for i in issues:
            related = f" (with {', '.join(i.related_requirement_ids)})" if i.related_requirement_ids else ""
            st.markdown(f"**{i.requirement_id}** `{i.issue_type.value}`{related}  \n{i.description}")
    with tab_uc:
        for uc in srs.use_cases:
            with st.expander(f"{uc.id} - {uc.title}"):
                st.markdown(f"**Actor:** {uc.actor}  \n**Requirements:** {', '.join(uc.related_requirement_ids)}")
                st.markdown("**Preconditions**\n" + "\n".join(f"- {p}" for p in uc.preconditions))
                st.markdown("**Main flow**\n" + "\n".join(f"{n}. {s}" for n, s in enumerate(uc.main_flow, 1)))
    with tab_prev:
        first = next(iter(files.values()), {})
        if "md" in first:
            st.markdown(Path(first["md"]).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ UI
st.title("\U0001F4C4 Canonical Formatter")
st.caption("Turn unstructured requirements (text, PDF, image) into structured engineering documents.")

with st.sidebar:
    st.header("Output settings")
    project_name = st.text_input("Project name (optional)", help="Leave blank to auto-generate from the content.")
    formats = st.multiselect(
        "Document formats", options=list(FORMATS), default=["ieee_srs"],
        format_func=lambda k: FORMAT_LABELS[k],
    )
    export_types = st.multiselect("File types", ["docx", "pdf"], default=["docx", "pdf"])
    st.caption("Markdown is always included.")

tab_up, tab_paste = st.tabs(["Upload a file", "Paste text"])
with tab_up:
    uploaded = st.file_uploader("Text, PDF or image", type=["txt", "md", "pdf", "png", "jpg", "jpeg"])
with tab_paste:
    pasted = st.text_area("Requirements text", height=220, placeholder="The system shall ...")

has_input = uploaded is not None or bool(pasted.strip())
if st.button("Generate documents", type="primary", disabled=not (has_input and formats)):
    export_list = ["md"] + export_types
    path, input_type = save_input(uploaded, pasted)
    started = time.time()
    with st.status("Running pipeline...", expanded=True) as status:
        try:
            result, files = run_pipeline(path, input_type, project_name, formats, export_list, status)
            status.update(label="Done", state="complete")
        except Exception as exc:  # keep the UI alive on unexpected failures
            status.update(label="Failed", state="error")
            st.exception(exc)
            st.stop()
    st.session_state["run"] = (result, files, time.time() - started)

if "run" in st.session_state:  # persists across download-button reruns
    show_results(*st.session_state["run"])