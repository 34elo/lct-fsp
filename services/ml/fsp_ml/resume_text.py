"""Текст из файла резюме (шаг 1): PDF — PyMuPDF, DOCX — python-docx.

Тип проверяем по сигнатуре, а не по заявленному `mime`.
"""

from __future__ import annotations

import io
import re
import zipfile

PDF_MIME = "application/pdf"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
MIN_TEXT_CHARS = 200  # меньше — считаем сканом


class ResumeFileError(Exception):
    """`code`: bad_file (не тот формат или битый файл), scanned_pdf (нет текстового слоя)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def sniff(data: bytes) -> str | None:
    """MIME по сигнатуре: PDF, DOCX (zip с word/document.xml) или None."""
    if data.startswith(b"%PDF-"):
        return PDF_MIME
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                if "word/document.xml" in z.namelist():
                    return DOCX_MIME
        except zipfile.BadZipFile:
            return None
    return None


def _pdf_text(data: bytes) -> str:
    import pymupdf

    pages = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            pages.append(page.get_text("text", sort=True))
    return "\n".join(pages)


def _docx_text(data: bytes) -> str:
    """Абзацы и таблицы в порядке документа (выгрузка hh.ru кладёт опыт в таблицу).

    Ячейки строки таблицы через « | »; если в ячейке несколько абзацев (дата и длительность,
    компания, город, должность), каждый идёт отдельной строкой — как в PDF.
    """
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = docx.Document(io.BytesIO(data))
    lines: list[str] = []
    for el in d.element.body.iterchildren():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "p":
            lines.append(Paragraph(el, d).text)
        elif tag == "tbl":
            for row in Table(el, d).rows:
                cells = list(
                    dict.fromkeys(c.text.strip() for c in row.cells)
                )  # объединённые ячейки
                cells = [c for c in cells if c]
                if any("\n" in c for c in cells):
                    lines.extend(ln for c in cells for ln in c.splitlines())
                else:
                    lines.append(" | ".join(cells))
    return "\n".join(lines)


_TRAILING = re.compile(r"[ \t]+\n")
_BLANKS = re.compile(r"\n{3,}")


_LIGATURES = str.maketrans(
    {"\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl"}
)  # PDF: \u00abAir\ufb02ow\u00bb \u2192 \u00abAirflow\u00bb


def clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\xa0", " ").replace("\u200b", "")
    text = text.translate(_LIGATURES)
    text = _TRAILING.sub("\n", text)
    return _BLANKS.sub("\n\n", text).strip()


def extract_text(data: bytes) -> str:
    """Текст резюме. Формат — по сигнатуре, заявленный `mime` не используем."""
    mime = sniff(data)
    if mime is None:
        raise ResumeFileError("bad_file")
    try:
        text = _pdf_text(data) if mime == PDF_MIME else _docx_text(data)
    except Exception as e:  # битый файл: любая ошибка парсера одинаково означает bad_file
        raise ResumeFileError("bad_file") from e
    text = clean(text)
    if len(text) < MIN_TEXT_CHARS:
        # скан: OCR через vision-модель ещё не подключён
        raise ResumeFileError("scanned_pdf" if mime == PDF_MIME else "bad_file")
    return text
