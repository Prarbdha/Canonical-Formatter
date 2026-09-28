import re
from datetime import date
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from canonical_formatter.schemas.requirement import CanonicalRequirementSet, RequirementType
from canonical_formatter.schemas.srs import SRSDocument
from canonical_formatter.agents.exporters import parse_markdown, write_docx, write_pdf

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
OUTPUT_DIR = Path("outputs")

# format key -> (template file, filename suffix)
FORMATS = {
    "ieee_srs": ("ieee_srs.md.j2", "SRS"),
    "tech_report": ("tech_report.md.j2", "Technical_Report"),
    "readme": ("readme.md.j2", "README"),
    "project_doc": ("project_doc.md.j2", "Project_Doc"),
}

# Special typography that LLMs emit and that some fonts/exporters can't render
CHAR_MAP = {
    "\u2010": "-", "\u2011": "-", "\u2013": "-", "\u2014": "-",
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"', "\u00a0": " ",
}

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATE_DIR)),
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)


def _clean(text: str) -> str:
    for bad, good in CHAR_MAP.items():
        text = text.replace(bad, good)
    return re.sub(r"\n{3,}", "\n\n", text)


def render_document(canonical: CanonicalRequirementSet, srs: SRSDocument, output_format: str) -> str:
    if output_format not in FORMATS:
        raise ValueError(f"Unknown output format '{output_format}'. Choose from {list(FORMATS)}")

    template = _env.get_template(FORMATS[output_format][0])
    text = template.render(
        project_name=canonical.project_name,
        date=date.today().isoformat(),
        srs=srs,
        canonical=canonical,
        requirements=canonical.requirements,
        functional=canonical.get_functional(),
        nonfunctional=canonical.get_non_functional(),
        issues=canonical.validation_report.issues,
        actors=sorted({uc.actor for uc in srs.use_cases}),
    )
    return _clean(text)


def write_document(canonical: CanonicalRequirementSet, srs: SRSDocument, output_format: str) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9]+", "_", canonical.project_name).strip("_") or "project"
    path = OUTPUT_DIR / f"{slug}_{FORMATS[output_format][1]}.md"
    path.write_text(render_document(canonical, srs, output_format), encoding="utf-8")
    return path

def write_all(
    canonical: CanonicalRequirementSet,
    srs: SRSDocument,
    output_format: str,
    export_types=("md", "docx", "pdf"),
) -> dict[str, Path]:
    """Render once, then export to every requested file type. Markdown is always kept
    because the RAG pipeline (Phase 7) will index it."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    md_text = render_document(canonical, srs, output_format)

    slug = re.sub(r"[^A-Za-z0-9]+", "_", canonical.project_name).strip("_") or "project"
    base = OUTPUT_DIR / f"{slug}_{FORMATS[output_format][1]}"

    paths = {"md": Path(f"{base}.md")}
    paths["md"].write_text(md_text, encoding="utf-8")

    blocks = parse_markdown(md_text)
    if "docx" in export_types:
        paths["docx"] = write_docx(blocks, Path(f"{base}.docx"))
    if "pdf" in export_types:
        paths["pdf"] = write_pdf(blocks, Path(f"{base}.pdf"))
    return paths