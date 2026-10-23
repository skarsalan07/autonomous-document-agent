from pathlib import Path

import pytest
from docx import Document

from app.config import Settings
from app.document_generator import generate_docx
from app.quality_checker import check_document
from app.schemas import ContentSection, DocumentDraft


def sample_draft() -> DocumentDraft:
    return DocumentDraft(
        title="Customer Support Implementation Plan",
        executive_summary="This plan outlines a practical, phased approach for improving customer support while protecting customer data and measuring results.",
        sections=[
            ContentSection(heading="Objectives", paragraphs=["Reduce avoidable support effort while preserving a clear route to human help."]),
            ContentSection(heading="Delivery Roadmap", bullets=["Assess current support needs.", "Pilot with a limited set of workflows."]),
        ],
        conclusion="Begin with a measured pilot, review outcomes with the support team, and expand only after quality and privacy gates are met.",
    )


def test_docx_generation_and_quality_validation(tmp_path: Path):
    file_path = generate_docx(sample_draft(), "Implementation Plan", ["Budget figures are illustrative."], tmp_path)
    assert file_path.is_file()
    assert file_path.name.startswith("document-")
    opened = Document(file_path)
    assert "Customer Support Implementation Plan" in "\n".join(p.text for p in opened.paragraphs)
    result = check_document(
        file_path,
        ["Objectives", "Delivery Roadmap"],
        "Customer Support Implementation Plan",
        Settings(min_document_characters=100),
    )
    assert result.passed
    assert result.file_size_bytes > 0


def test_empty_content_is_rejected_by_schema():
    with pytest.raises(ValueError, match="substantive content"):
        ContentSection(heading="Empty section")
