from __future__ import annotations

import io
import re
import urllib.request
import unicodedata
from dataclasses import dataclass
from pathlib import Path


QUESTION_HEADER_RE = re.compile(
    r"\bTOSS\s*[-–—]?\s*UP\s+(\d+)\s*[).]\s*"
    r"([A-Z][A-Z\s/&.]{2,}?)\s*[-–—\ufffd]?\s+"
    r"(?:Short\s+Answer|Multiple\s+Choice)",
    re.IGNORECASE | re.MULTILINE,
)


@dataclass(frozen=True)
class SubjectMatch:
    question_number: int
    subject: str


def normalize_subject(raw: str) -> str:
    words = raw.replace("\n", " ").replace("&", "AND").split()
    raw = " ".join(words).upper()
    aliases = {"MATHEMATICS": "MATH", "EARTH AND SPACE": "EARTH AND SPACE SCIENCE"}
    raw = aliases.get(raw, raw)
    allowed = {"BIOLOGY", "CHEMISTRY", "PHYSICS", "MATH", "EARTH SCIENCE",
               "GENERAL SCIENCE", "ASTRONOMY", "ENERGY", "EARTH AND SPACE SCIENCE"}
    if raw not in allowed:
        raise ValueError(f"Unrecognized toss-up subject: {raw}")
    words = raw.split()
    return " ".join(word.capitalize() for word in words)


def infer_subjects_from_text(text: str) -> dict[int, str]:
    text = unicodedata.normalize("NFKC", text).replace("\u00ad", "")
    subjects: dict[int, str] = {}
    for match in QUESTION_HEADER_RE.finditer(text):
        question_number = int(match.group(1))
        subject = normalize_subject(match.group(2))
        if question_number in subjects:
            raise ValueError(f"Repeated toss-up number {question_number}; import one round PDF at a time")
        subjects[question_number] = subject
    return subjects


def extract_pdf_text(path_or_url: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("Install pypdf to infer subjects from PDF files") from exc

    if path_or_url.startswith(("http://", "https://")):
        request = urllib.request.Request(path_or_url, headers={"User-Agent": "ScienceBowlLogger/2.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read(20 * 1024 * 1024 + 1)
        if len(data) > 20 * 1024 * 1024:
            raise ValueError("PDF exceeds the 20 MB limit")
        if not data.lstrip().startswith(b"%PDF-"):
            raise ValueError("The URL did not return a PDF. Use a direct PDF download link.")
        reader = PdfReader(io.BytesIO(data))
    else:
        reader = PdfReader(str(Path(path_or_url)))

    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def infer_subjects_from_pdf(path_or_url: str) -> dict[int, str]:
    subjects = infer_subjects_from_text(extract_pdf_text(path_or_url))
    if not subjects:
        raise ValueError("No toss-up headers found. Scanned PDFs need OCR first.")
    missing = sorted(set(range(1, max(subjects) + 1)) - subjects.keys())
    if missing:
        raise ValueError(f"Missing toss-up numbers {missing}; no subjects were imported")
    return subjects
