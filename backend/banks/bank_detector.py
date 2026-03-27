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
    ("au bank", r"\bau\d*\b|aubl", r"au\s*small\s*finance\s*bank"),
    ("boi", r"\bboi\b|bank\s*of\s*india", r"bank\s*of\s*india"),
    ("bob", r"\bbob\b|bank\s*of\s*baroda|baroda", r"bank\s*of\s*baroda|barb0|bob\s*world"),
    ("csb", r"\bcsb\b|catholic\s*syrian\s*bank", r"\bcsb\s*bank\b|catholic\s*syrian\s*bank"),
    ("kokan", r"\bkokan\b|kokan\s*mercantile", r"kokan\s*mercantile|kkbkokmcb"),
    ("canara", r"canara", r"canara\s*bank|cnrb"),
    ("federal", r"federal", r"federal\s*bank|fdrl"),
    ("indian", r"indian\s*bank|\bidib\b", r"indian\s*bank|\bidib\b"),
    ("standard_chartered",
    r"standard[\s_-]*charter|stadard[\s_-]*charter",
    r"standard\s*chartered\s*(bank)?"),
    ("cosmos", r"cosmos", r"cosmos\s*co[\s-]*op|the\s*cosmos"),
    ("bom", r"\bbom\b|bank\s*of\s*maharashtra|mahabank", r"bank\s*of\s*maharashtra|mahb"),
    ("bandhan", r"bandhan", r"bandhan\s*bank"),
    ("yes_bank", r"yes[\s_-]*bank|\byesb\b", r"yes\s*bank|\byesb\b"),
    ("union_bank", r"union[\s_-]*bank|ubin", r"union\s*bank\s*of\s*india|\bubin\b"),
    ("cbi", r"central[\s_-]*bank|cbi|\bcbin\b", r"central\s*bank\s*of\s*india|\bcbin\b"),
    ("dcb", r"dcb", r"dcb\s*bank|development\s*credit\s*bank|dcbl"),
    ("pnb", r"pnb|punjab[\s_-]*national|punb", r"punjab\s*national\s*bank|\bpunb\b"),
    ("idfc", r"idfc", r"idfc\s*first\s*bank|idfb"),
    ("idbi", r"idbi", r"idbi\s*bank|industrial\s+development\s+bank"),
    ("rbl", r"rbl[\s_-]*bank|rbl", r"rbl\s*bank|\bratn\b"),
    ("karnataka",r"karnataka\s*bank|karb|your\s+family\s+bank",r"karnataka\s*bank\s*ltd|karb[a-z0-9]{7}"),

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
    ("au bank", r"\bAUBL[A-Z0-9]{7}\b"),         #AU Bank
    ("boi", r"\bBKID[A-Z0-9]{7}\b"),        #BOI Bank
    ("bob",  r"\bBARB[A-Z0-9]{7}\b"),       # Bank of Baroda (BARB0MARINE etc.)
     ("csb", r"\bCSBK[A-Z0-9]{7}\b"),        # CSB Bank
    ("kokan", r"\bKKBKOKMCB[A-Z0-9]+\b"),   # Kokan Mercantile — add BEFORE kotak
    ("canara", r"\bCNRB[A-Z0-9]{7}\b"),     #Canara Bank
    ("federal", r"\bFDRL[A-Z0-9]{7}\b"),    #Federal Bank
    ("indian", r"\bIDIB[A-Z0-9]{7}\b"),     #Indian Bank
    ("saraswat", r"\bSRCB[A-Z0-9]{7}\b"),   #Saraswat Bank
    ("standard_chartered", r"\bSCBL[A-Z0-9]{7}\b"),# Standard_chartered Bank
    ("cosmos", r"\bCOSB[A-Z0-9]{7}\b"),     #Cosmos Bank
    ("bom", r"\bMAHB[A-Z0-9]{7}\b"),        #Bank Of Maharashtra
    ("bandhan", r"\bBDBL[A-Z0-9]{7}\b"),    #Bandhan Bank
    ("yes_bank", r"\bYESB[A-Z0-9]{7}\b"),   #Yes Bank
    ("union_bank", r"\bUBIN[A-Z0-9]{7}\b"), # Union Bank of India
    ("cbi", r"\bCBIN[A-Z0-9]{7}\b"),        # Central Bank of India
    ("dcb", r"\bDCBL[A-Z0-9]{7}\b"),        #DCB Bank
    ("pnb", r"\bPUNB[A-Z0-9]{7}\b"),        # Punjab National Bank
    ("idfc", r"\bIDFB[A-Z0-9]{7}\b"),       #IDFC Bank
    ("idbi", r"\bIBKL[A-Z0-9]{7}\b"),       #IDBI Bank
    ("karnataka", r"\bKARB[A-Z0-9]{7}\b"),  #KBL Bank
    ("rbl", r"\bRATN[A-Z0-9]{7}\b"),        #RBL Bank
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

    # if "saraswat" in header_wide_lower or re.search(r"\bsrcb\b", header_wide_lower):
    #     return "saraswat"
    # if re.search(r"\b810000000\d{6}\b", header_wide_lower):
    #     return "saraswat"
    
    # # SCB must be first — its statements contain UTIB (Axis) IFSCs in txn descriptions
    if "standard chartered" in header_wide_lower or re.search(r"\bscbl\b", header_wide_lower):
        return "standard_chartered"


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
    
    if re.search(r"general\s+details", header_wide, re.I) and \
   re.search(r"\b(47\d{8}|10\d{8})\b", header_wide):
        return "karnataka"
    if re.search(r"\bKARB[A-Z0-9]{7}\b", header_wide):
        return "karnataka"
    if re.search(r"karnataka\s*bank|your\s+family\s+bank", header_wide, re.I):
        return "karnataka"

    if "state bank of india" in header_wide_lower or "sbi" in header_wide_lower:
        return "sbi"

    if "kotak mahindra bank" in header_wide_lower:
        return "kotak"

    if "icici bank" in header_wide_lower:
        return "icici"

    if "au bank" in header_wide_lower:
        return "au bank"
    
    if "canara bank" in header_wide_lower or re.search(r"\bcnrb\b", header_wide_lower):
        return "canara"
    
    if "federal bank" in header_wide_lower or re.search(r"\bfdrl\b", header_wide_lower):
        return "federal"
    
    if "indian bank" in header_wide_lower or re.search(r"\bidib\b", header_wide_lower):
        return "indian"
    
    if "rbl bank" in header_wide_lower or re.search(r"\bratn\b", header_wide_lower):
        return "rbl"
    
    if "cosmos co-op" in header_wide_lower \
            or "cosmos co op" in header_wide_lower \
            or re.search(r"the\s+cosmos", header_wide_lower) \
            or re.search(r"\bcosb\b", header_wide_lower):
        return "cosmos"

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
