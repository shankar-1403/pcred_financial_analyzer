"""
Bank statement parser. Delegates to bank-specific parsers in banks/ package.
OCR and text extraction live in ocr_engine; parsing logic is split by bank (ICICI, Axis, SBI, HDFC, etc.).
"""
from banks import parse_bank_statement
from ocr_engine import (
    extract_text_from_pdf,
    extract_pdf_text_fast,
)

# Re-export for backward compatibility
__all__ = [
    "parse_bank_statement",
    "extract_text_from_pdf",
    "extract_pdf_text_fast",
]

if __name__ == "__main__":
    import sys
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "statement.pdf"
    data = parse_bank_statement(pdf_path)
    from pprint import pprint
    pprint(data)
