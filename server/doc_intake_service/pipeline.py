"""Bounded document decoding; called only by background workers."""
from __future__ import annotations

import io
import os
import time
import warnings

from pypdf import PdfReader
from pypdf.errors import PdfReadError
import pypdfium2 as pdfium
import pytesseract
from PIL import Image, UnidentifiedImageError

from .classify import classify
from .extract import extract
from .rules import normalize_record

MAX_PAGES = 10
MAX_PIXELS = 16_000_000
MAX_TEXT = 500_000
OCR_SECONDS = 20
JOB_SECONDS = 240
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
if os.environ.get("TESSERACT_CMD"):
    pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]

def image_text(image):
    if image.width * image.height > MAX_PIXELS:
        raise ValueError("Image exceeds 16 megapixels; resize the scan")
    return pytesseract.image_to_string(image.convert("RGB"), lang="eng", timeout=OCR_SECONDS)

def read_document(data, kind):
    text, ocr_used, pages = [], False, 0
    deadline = time.monotonic() + JOB_SECONDS
    def append(value):
        text.append(value)
        if sum(map(len, text)) > MAX_TEXT:
            raise ValueError("Extracted text exceeds 500000 characters")
        if time.monotonic() > deadline:
            raise ValueError("Document processing exceeded the time budget")
    if kind == "text/plain":
        value = data.decode("utf-8-sig")
        if "\x00" in value:
            raise ValueError("Text upload contains binary NUL bytes")
        append(value)
        pages = 1
    elif kind == "application/pdf":
        try:
            reader = PdfReader(io.BytesIO(data), strict=True)
            if reader.is_encrypted:
                raise ValueError("Encrypted PDFs are unsupported; provide an unlocked copy")
            if not 1 <= len(reader.pages) <= MAX_PAGES:
                raise ValueError("PDF must contain 1 to 10 pages")
            pages = len(reader.pages)
            rendered = None
            try:
                for index, page in enumerate(reader.pages):
                    value = page.extract_text() or ""
                    if len(value.strip()) < 20:
                        if rendered is None:
                            rendered = pdfium.PdfDocument(data)
                        pdf_page = rendered[index]
                        try:
                            width, height = pdf_page.get_size()
                            if width * height * 4 > MAX_PIXELS:
                                raise ValueError("PDF page exceeds the 16 megapixel rendering limit")
                            bitmap = pdf_page.render(scale=2)
                            try:
                                value = image_text(bitmap.to_pil())
                            finally:
                                bitmap.close()
                            ocr_used = True
                        finally:
                            pdf_page.close()
                    append(value)
            finally:
                if rendered is not None:
                    rendered.close()
        except (PdfReadError, pdfium.PdfiumError) as exc:
            raise ValueError(f"Cannot read PDF: {exc}") from exc

    else:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    frames = getattr(image, "n_frames", 1)
                    if frames > MAX_PAGES:
                        raise ValueError("Image must contain at most 10 frames")
                    for frame in range(frames):
                        image.seek(frame)
                        append(image_text(image))
                    pages, ocr_used = frames, True
        except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning, OSError) as exc:
            raise ValueError(f"Cannot read image: {exc}") from exc
    value = "\n\n".join(text)
    if not value.strip():
        raise ValueError("No readable text found; provide a clearer scan or a text document")
    return value, ocr_used, pages

def process_document(data, kind):
    text, ocr_used, pages = read_document(data, kind)
    prediction = classify(text).as_dict()
    return dict(text=text, ocr_used=ocr_used, pages=pages,
                record=normalize_record(extract(text).as_dict()), prediction=prediction)
