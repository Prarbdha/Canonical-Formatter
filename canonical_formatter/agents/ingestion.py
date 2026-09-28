import os
import pytesseract
from PIL import Image
import pdfplumber

# Point pytesseract to your Tesseract install if it's not on PATH
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


def read_plain_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def read_pdf_text(path: str) -> str:
    """Extracts text from a text-based PDF. Falls back to OCR per-page if a page has no text."""
    full_text = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text and text.strip():
                full_text.append(text)
            else:
                # Scanned page with no extractable text -> OCR fallback
                img = page.to_image(resolution=300).original
                ocr_text = pytesseract.image_to_string(img)
                full_text.append(ocr_text)
    return "\n".join(full_text)


def read_image_text(path: str) -> str:
    img = Image.open(path)
    return pytesseract.image_to_string(img)


def normalize_text(raw_text: str) -> str:
    """Basic cleanup: collapse excess whitespace, strip control chars."""
    lines = [line.strip() for line in raw_text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def ingest(path: str, input_type: str) -> str:
    """
    Main entry point for the Ingestion Agent.
    input_type: 'text' | 'pdf' | 'image'
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Input file not found: {path}")

    if input_type == "text":
        raw = read_plain_text(path)
    elif input_type == "pdf":
        raw = read_pdf_text(path)
    elif input_type == "image":
        raw = read_image_text(path)
    else:
        raise ValueError(f"Unsupported input_type: {input_type}")

    return normalize_text(raw)