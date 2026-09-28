"""
Exporters: convert the rendered Markdown (a small, controlled subset produced by our
Jinja templates) into DOCX and PDF. One parser, two writers, so all four document
formats get both exports for free.
"""
import re
from pathlib import Path
from xml.sax.saxutils import escape

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

# ----------------------------------------------------------------------------
# 1. Markdown -> blocks
# ----------------------------------------------------------------------------
_HEADING = re.compile(r"^(#{1,6})\s+(.*)")
_BULLET = re.compile(r"^\s*[-*]\s+(.*)")
_NUMBERED = re.compile(r"^\s*\d+\.\s+(.*)")
_QUOTE = re.compile(r"^>\s?(.*)")
_SEPARATOR_CELL = re.compile(r":?-{3,}:?")
_INLINE = re.compile(r"(\*\*.+?\*\*|(?<!\w)_.+?_(?!\w))")


def _is_special(line: str) -> bool:
    s = line.strip()
    return (
        s == "---"
        or bool(_HEADING.match(line))
        or s.startswith("|")
        or bool(_BULLET.match(line))
        or bool(_NUMBERED.match(line))
        or bool(_QUOTE.match(line))
    )


def parse_markdown(md: str) -> list[tuple]:
    """
    Returns blocks:
      ("h", level, text) | ("p", text) | ("ul", [items]) | ("ol", [items])
      ("table", header, rows) | ("quote", text) | ("hr",)
    """
    lines = md.splitlines()
    blocks: list[tuple] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip():
            i += 1
            continue

        if line.strip() == "---":
            blocks.append(("hr",))
            i += 1
            continue

        m = _HEADING.match(line)
        if m:
            blocks.append(("h", len(m.group(1)), m.group(2).strip()))
            i += 1
            continue

        if line.lstrip().startswith("|"):
            rows = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                rows.append(cells)
                i += 1
            rows = [r for r in rows if not all(_SEPARATOR_CELL.fullmatch(c) for c in r)]
            if rows:
                blocks.append(("table", rows[0], rows[1:]))
            continue

        if _BULLET.match(line):
            items = []
            while i < len(lines) and _BULLET.match(lines[i]):
                items.append(_BULLET.match(lines[i]).group(1).strip())
                i += 1
            blocks.append(("ul", items))
            continue

        if _NUMBERED.match(line):
            items = []
            while i < len(lines) and _NUMBERED.match(lines[i]):
                items.append(_NUMBERED.match(lines[i]).group(1).strip())
                i += 1
            blocks.append(("ol", items))
            continue

        if _QUOTE.match(line):
            parts = []
            while i < len(lines) and _QUOTE.match(lines[i]):
                parts.append(_QUOTE.match(lines[i]).group(1).strip())
                i += 1
            blocks.append(("quote", " ".join(p for p in parts if p)))
            continue

        # plain paragraph: consecutive lines become line breaks
        para = []
        while i < len(lines) and lines[i].strip() and not _is_special(lines[i]):
            para.append(lines[i].strip())
            i += 1
        if para:
            blocks.append(("p", "\n".join(para)))
        else:  # safety: never loop forever on an unexpected line
            i += 1
    return blocks


def _runs(text: str) -> list[tuple[str, bool, bool]]:
    """Split inline markdown into (text, bold, italic) runs."""
    out = []
    for part in _INLINE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            out.append((part[2:-2], True, False))
        elif part.startswith("_") and part.endswith("_") and len(part) > 2:
            out.append((part[1:-1], False, True))
        else:
            out.append((part, False, False))
    return out


def _plain(text: str) -> str:
    return "".join(t for t, _, _ in _runs(text))


# ----------------------------------------------------------------------------
# 2. DOCX writer
# ----------------------------------------------------------------------------
def _shade(cell, fill_hex: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill_hex)
    tcPr.append(shd)


def _add_page_number(section) -> None:
    p = section.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.add_run("Page ")
    run = p.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)


def _add_runs(par, text: str, size: float | None = None, italic_all: bool = False) -> None:
    for li, line in enumerate(text.split("\n")):
        if li:
            par.add_run().add_break()
        for t, bold, italic in _runs(line):
            r = par.add_run(t)
            r.bold = True if bold else None
            r.italic = True if (italic or italic_all) else None
            if size:
                r.font.size = Pt(size)


def write_docx(blocks: list[tuple], path: Path) -> Path:
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)  # A4
    sec.left_margin = sec.right_margin = Cm(2.2)
    sec.top_margin = sec.bottom_margin = Cm(2.2)
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)
    _add_page_number(sec)

    for block in blocks:
        kind = block[0]

        if kind == "h":
            level, text = block[1], _plain(block[2])
            doc.add_heading(text, 0 if level == 1 else min(level - 1, 4))

        elif kind == "p":
            _add_runs(doc.add_paragraph(), block[1])

        elif kind == "ul":
            for item in block[1]:
                _add_runs(doc.add_paragraph(style="List Bullet"), item)

        elif kind == "ol":
            for n, item in enumerate(block[1], start=1):
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Cm(1.0)
                p.paragraph_format.first_line_indent = Cm(-0.6)
                _add_runs(p, f"{n}. {item}")

        elif kind == "quote":
            p = doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.8)
            _add_runs(p, block[1], italic_all=True)

        elif kind == "hr":
            p = doc.add_paragraph()
            pPr = p._p.get_or_add_pPr()
            borders = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            for k, v in (("w:val", "single"), ("w:sz", "6"), ("w:space", "1"), ("w:color", "999999")):
                bottom.set(qn(k), v)
            borders.append(bottom)
            pPr.append(borders)

        elif kind == "table":
            header, rows = block[1], block[2]
            n = len(header)
            table = doc.add_table(rows=1, cols=n)
            table.style = "Table Grid"
            for i, h in enumerate(header):
                cell = table.rows[0].cells[i]
                run = cell.paragraphs[0].add_run(_plain(h))
                run.bold = True
                run.font.size = Pt(9.5)
                _shade(cell, "D9E2F3")
            trPr = table.rows[0]._tr.get_or_add_trPr()
            repeat = OxmlElement("w:tblHeader")
            repeat.set(qn("w:val"), "true")
            trPr.append(repeat)
            for row in rows:
                cells = table.add_row().cells
                for i in range(n):
                    _add_runs(cells[i].paragraphs[0], row[i] if i < len(row) else "", size=9.5)
            doc.add_paragraph()

    doc.save(str(path))
    return path


# ----------------------------------------------------------------------------
# 3. PDF writer
# ----------------------------------------------------------------------------
def _markup(text: str) -> str:
    """Inline markdown -> ReportLab paragraph markup (Helvetica-safe characters only)."""
    text = text.encode("cp1252", "replace").decode("cp1252")
    lines = []
    for line in text.split("\n"):
        s = ""
        for t, bold, italic in _runs(line):
            t = escape(t)
            if bold:
                t = f"<b>{t}</b>"
            if italic:
                t = f"<i>{t}</i>"
            s += t
        lines.append(s)
    return "<br/>".join(lines)


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawCentredString(A4[0] / 2, 1.0 * cm, f"Page {doc.page}")
    canvas.restoreState()


def write_pdf(blocks: list[tuple], path: Path) -> Path:
    ss = getSampleStyleSheet()
    dark = colors.HexColor("#1a1a2e")
    body = ParagraphStyle("body", parent=ss["Normal"], fontSize=10, leading=14.5, spaceAfter=6)
    cell = ParagraphStyle("cell", parent=body, fontSize=8.5, leading=11, spaceAfter=0)
    cell_head = ParagraphStyle("cellh", parent=cell, fontName="Helvetica-Bold", textColor=colors.white)
    quote = ParagraphStyle(
        "quote", parent=body, leftIndent=14, fontName="Helvetica-Oblique",
        textColor=colors.HexColor("#444444"),
    )
    heads = {
        1: ParagraphStyle("h1", parent=ss["Title"], fontSize=22, leading=26, spaceAfter=12, textColor=dark),
        2: ParagraphStyle("h2", parent=ss["Heading1"], fontSize=15, spaceBefore=16, spaceAfter=6, textColor=dark, keepWithNext=1),
        3: ParagraphStyle("h3", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, spaceBefore=12, spaceAfter=5, textColor=dark, keepWithNext=1),
        4: ParagraphStyle("h4", parent=ss["Heading3"], fontName="Helvetica-Bold", fontSize=11, spaceBefore=10, spaceAfter=4, textColor=dark, keepWithNext=1),
    }

    margin = 2.0 * cm
    content_width = A4[0] - 2 * margin
    story = []

    for block in blocks:
        kind = block[0]

        if kind == "h":
            story.append(Paragraph(_markup(_plain(block[2])), heads[min(block[1], 4)]))

        elif kind == "p":
            story.append(Paragraph(_markup(block[1]), body))

        elif kind == "ul":
            story.append(ListFlowable(
                [ListItem(Paragraph(_markup(x), body), leftIndent=14) for x in block[1]],
                bulletType="bullet", start="\u2022", leftIndent=14, bulletFontSize=9,
            ))

        elif kind == "ol":
            story.append(ListFlowable(
                [ListItem(Paragraph(_markup(x), body), leftIndent=16) for x in block[1]],
                bulletType="1", bulletFormat="%s.", leftIndent=16, bulletFontSize=10,
            ))

        elif kind == "quote":
            story.append(Paragraph(_markup(block[1]), quote))

        elif kind == "hr":
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceBefore=4, spaceAfter=8))

        elif kind == "table":
            header, rows = block[1], block[2]
            n = len(header)
            padded = [(r + [""] * n)[:n] for r in rows]
            data = [[Paragraph(_markup(h), cell_head) for h in header]]
            data += [[Paragraph(_markup(c), cell) for c in r] for r in padded]
            weights = [
                max(6, min(40, max(len(x) for x in col)))
                for col in zip(header, *padded)
            ]
            widths = [content_width * w / sum(weights) for w in weights]
            table = Table(data, colWidths=widths, repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b2d42")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f4f8")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(table)
            story.append(Spacer(1, 10))

    SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=margin, rightMargin=margin, topMargin=margin, bottomMargin=2.2 * cm,
    ).build(story, onFirstPage=_footer, onLaterPages=_footer)
    return path