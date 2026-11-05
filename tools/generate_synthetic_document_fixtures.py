"""Create deterministic, text-bearing PDF fixtures for runtime regression tests.

The fixture values are entirely synthetic. The script deliberately uses the
already-required ``pypdf`` package rather than a network service or a paid
document-generation dependency.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject


FIXTURE_DIRECTORY = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "documents"


def _text_pdf(lines: list[str]) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    escaped_lines = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") for line in lines]
    commands = " ".join(
        f"{'' if index == 0 else '0 -20 Td '}( {line}) Tj".replace("( ", "(")
        for index, line in enumerate(escaped_lines)
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 72 720 Td {commands} ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def main() -> None:
    FIXTURE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    cases = {
        "CASE01_baseline.pdf": [
            "Synthetic CASE01 document - deliberately conflicts with the form",
            "Loan Amount: 180000",
            "Annual Income: 84000",
            "Monthly Debt Obligations: 950",
            "Debt-to-Income Ratio: 31.5%",
            "Property Value: 210000",
            "Loan Type: FHA",
            "Loan Purpose: purchase",
            "Occupancy: primary_residence",
        ],
        "synthetic_clean_loan_application_demo.pdf": [
            "Synthetic clean loan application - matches the clean form",
            "Loan Amount: 250000",
            "Annual Income: 120000",
            "Monthly Debt Obligations: 1800",
            "Debt-to-Income Ratio: 30%",
            "Property Value: 325000",
            "Loan Type: conventional",
            "Loan Purpose: purchase",
            "Property Type: single_family",
            "Number of Units: 1",
            "Occupancy: primary_residence",
        ],
        "missing_property_value.pdf": [
            "Synthetic incomplete loan application",
            "Loan Amount: 250000",
            "Annual Income: 120000",
            "Monthly Debt Obligations: 1800",
            "Loan Type: conventional",
        ],
    }
    for filename, lines in cases.items():
        (FIXTURE_DIRECTORY / filename).write_bytes(_text_pdf(lines))
    (FIXTURE_DIRECTORY / "low_quality_scanned_no_text.pdf").write_bytes(_blank_pdf())


if __name__ == "__main__":
    main()
