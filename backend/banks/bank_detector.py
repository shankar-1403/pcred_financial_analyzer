import re
from typing import Optional, List

# Bank identifiers: (key used in dispatcher, regex for filename, regex for content)
# Axis Neo must appear before Axis so "axis neo" → axis_neo.py, "AXIS" / "axis bank" → axis.py
BANK_SIGNATURES = [
    ("axis neo", r"axis\s*neo|neo\s*for\s*corporates", r"axis\s*neo|neo\s*for\s*corporates"),
    ("axis", r"axis\s*bank|\baxis\b", r"axis\s*bank|\baxis\b"),  # "AXIS CA JUN25..." or "axis bank"
    ("hdfc", r"hdfc", r"\bhdfc\s*bank\b"),
    ("icici", r"icici", r"\bicici\s*bank\b"),
    ("sbi", r"sbi", r"\bstate\s*bank\s*of\s*india\b|\bsbi\b"),
    ("kotak", r"kotak", r"\bkotak\s*mahindra\s*bank\b"),
    ("indusind", r"indusind", r"\bindusind\s*bank\b"),
    ("au", r"\bau\d*\b|aubl", r"au\s*small\s*finance\s*bank"),
    ("boi", r"\bboi\b|bank\s*of\s*india", r"bank\s*of\s*india"),
    ("bob", r"\bbob\b|bank\s*of\s*baroda|baroda", r"bank\s*of\s*baroda|barb0|bob\s*world"),
]

def detect_bank_from_filename(file_path: str) -> Optional[str]:
    if not file_path:
        return None
    name = file_path.replace("\\", "/").split("/")[-1].lower()
    for key, pattern, _ in BANK_SIGNATURES:
        if re.search(pattern, name, re.I):
            return key
    return None


# IFSC is 11 chars (4-letter bank + 7 alphanumeric). Check IndusInd (INDB) before HDFC so
# we don't pick "HDFC" from a transaction when the statement is actually IndusInd.
IFSC_BANK_MAP = [
    ("axis", r"\bUTIB[A-Z0-9]{7}\b"),       # Axis Bank (e.g. UTIB0003525)
    ("indusind", r"\bINDB\s*[A-Z0-9]{7}\b"), # IndusInd (allow space: INDB 0001234)
    ("hdfc", r"\bHDFC0[A-Z0-9]{6}\b"),      # HDFC Bank
    ("icici", r"\bICIC[A-Z0-9]{7}\b"),      # ICICI Bank
    ("sbi", r"\bSBIN[A-Z0-9]{7}\b"),        # State Bank of India
    ("kotak", r"\bKKBK[A-Z0-9]{7}\b"),      # Kotak
    ("au", r"\bAUBL[A-Z0-9]{7}\b"),         #AU Bank
    ("boi", r"\bBKID[A-Z0-9]{7}\b"),        #BOI Bank
    ("bob",  r"\bBARB[A-Z0-9]{7}\b"),       # Bank of Baroda (BARB0MARINE etc.)
]


# Lines to scan for Neo / bank name / IFSC (account block can be on first or second page)
_NEO_CHECK_LINES = 120
_IFSC_HEADER_LINES = 60  
_HEADER_ONLY_LINES = 25   


def _is_axis_neo_content(lines: List[str]) -> bool:
    """True if any of the first N lines suggest Axis Neo (Neo for Corporates / Axis Bank Neo)."""
    block = " ".join((line or "") for line in lines[:_NEO_CHECK_LINES]).lower()
    if "axis neo" in block or "neo for corporates" in block or "axis bank neo" in block:
        return True
    if re.search(r"\bneo\b", block) and ("axis" in block or "axis bank" in block):
        return True
    # Axis Neo statements often have "MCA" (Ministry of Corporate Affairs) in account type
    if re.search(r"\bmca\b", block) and re.search(r"\baxis\b", block):
        return True
    return False


def detect_bank_from_text(lines):

    if not lines:
        return None

    # Wide block for IFSC and bank name (account block can be on page 2)
    header_wide = " ".join((line or "") for line in lines[:_IFSC_HEADER_LINES])
    header_wide_lower = header_wide.lower()
    # Strict header: only first N lines — "HDFC Bank" here = statement bank; in txns = ignore
    header_only = " ".join((line or "") for line in lines[:_HEADER_ONLY_LINES]).lower()

    # 1) IFSC in statement (IndusInd INDB checked before HDFC so we don't mis-id from txn text)
    for key, pattern in IFSC_BANK_MAP:
        if re.search(pattern, header_wide, re.I):
            if key == "axis":
                if _is_axis_neo_content(lines):
                    return "axis neo"
                return "axis"
            return key

    # 2) Axis Neo before Axis
    if _is_axis_neo_content(lines):
        return "axis neo"

    # 3) Axis Bank only (no neo) → axis.py
    if "axis bank" in header_wide_lower or re.search(r"\baxis\b", header_wide_lower):
        return "axis"

    # 4) IndusInd: match in full block so we don't miss it
    if "indusind bank" in header_wide_lower or re.search(r"\bindusind\b", header_wide_lower):
        return "indusind"

    # 5) HDFC only if "hdfc bank" is in the statement header (first 25 lines), not in a txn
    if "hdfc bank" in header_only:
        return "hdfc"

    if "state bank of india" in header_wide_lower or "sbi" in header_wide_lower:
        return "sbi"

    if "kotak mahindra bank" in header_wide_lower:
        return "kotak"

    if "icici bank" in header_wide_lower:
        return "icici"

    if "au bank" in header_wide_lower:
        return "au bank"

    return None


def detect_bank(pdf_path: str, text_lines: Optional[List[str]] = None) -> str:
    key = detect_bank_from_filename(pdf_path)
    if key:
        # When filename says "axis", still check content so Axis Neo PDFs show "Axis Bank Neo"
        if key == "axis" and text_lines:
            from_text = detect_bank_from_text(text_lines)
            if from_text == "axis neo":
                return "axis neo"
        return key
    if text_lines:
        key = detect_bank_from_text(text_lines)
        if key:
            return key
    return "generic"
