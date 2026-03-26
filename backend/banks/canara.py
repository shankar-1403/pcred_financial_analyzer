import re
import pdfplumber
from datetime import datetime
from collections import defaultdict

from .base import (
    default_account_info,
    clean_amount,
)

BANK_KEY          = "canara"
BANK_DISPLAY_NAME = "Canara Bank"


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
IFSC_PATTERN = r"\b(CNRB[A-Z0-9]{7})\b"

# Loan PDF date  : "25 Apr 2025"  (DD Mon YYYY)
_DATE_LOAN_RE = re.compile(r"^\d{1,2}\s+[A-Za-z]{3}\s+\d{4}$")

# ePassbook date : "18-01-2024"   (DD-MM-YYYY)
_DATE_EPASS_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")

# Statement period patterns
_PERIOD_LOAN_RE = re.compile(
    r"[Ff]rom\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})\s+[Tt]o\s+(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})"
)
_PERIOD_EPASS_RE = re.compile(
    r"between\s+(\d{2}-[A-Za-z]{3}-\d{4})\s+and\s+(\d{2}-[A-Za-z]{3}-\d{4})",
    re.I
)

_RS_PREFIX_RE = re.compile(r"^Rs\.?\s*", re.I)

_SKIP_ROW_RE = re.compile(
    r"unless\s+the\s+constituent|beware\s+of\s+phishing|"
    r"end\s+of\s+statement|computer\s+output",
    re.I,
)

# ePassbook column x-boundaries (from PDF word-position inspection)
_EPASS_COL = {
    "date":        (14,  100),
    "description": (101, 310),
    "credit":      (311, 410),
    "debit":       (411, 510),
    "balance":     (511, 600),
}
_EPASS_SKIP = {
    "date", "particulars", "deposits", "withdrawals", "balance",
    "opening", "closing", "disclaimer", "page",
}


# ---------------------------------
# DATE REFORMAT
# ---------------------------------
def _reformat_loan_date(date_str: str) -> str:
    """'25 Apr 2025' → '25-04-2025'"""
    if not date_str:
        return date_str
    try:
        return datetime.strptime(date_str.strip(), "%d %b %Y").strftime("%d-%m-%Y")
    except ValueError:
        return date_str


def _reformat_epass_date(date_str: str) -> str:
    """'18-Jan-2024' or '18-01-2024' → '18-01-2024'"""
    if not date_str:
        return date_str
    for fmt in ("%d-%b-%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    return date_str


# ---------------------------------
# AMOUNT CLEANER
# ---------------------------------
def _clean_amount_canara(value):
    if value is None:
        return None
    value = str(value).strip()
    if not value or value in ("-", "", "None", "null"):
        return None
    value = _RS_PREFIX_RE.sub("", value).strip()
    value = value.replace(",", "").replace(" ", "")
    try:
        return float(value)
    except ValueError:
        return None


# ---------------------------------
# FORMAT DETECTOR
# ---------------------------------
def _detect_format(lines):
    """
    Returns 'loan' or 'epassbook' based on statement header text.
    Loan format    : 'Loan Account Statement'
    ePassbook fmt  : 'Statement for A/c'
    """
    for line in lines[:5]:
        l = (line or "").strip().lower()
        if "loan account statement" in l:
            return "loan"
        if "statement for a/c" in l:
            return "epassbook"
    return "loan"  # default


# ---------------------------------
# ACCOUNT INFO EXTRACTION
# ---------------------------------
def extract_account_info(lines):
    """
    Supports two Canara Bank statement formats:

    LOAN FORMAT (Loan Account Statement):
        'Customer Name GALAXY MACHINERY PVT LTD'
        'Customer Id. 26008933'
        'Account No. 0558768000015'
        'Account Currency INR'
        'searched By From 01 Apr 2025 To 28 Jul 2025'
        'Closing Balance Rs. 69,373.00'
        'Product Name LOANS TO MSME - SERVICES'

    ePASSBOOK FORMAT (Statement for A/c):
        'Statement for A/c XXXXXXXXX0170 between 18-Jan-2024 and 12-Feb-2024'
        'Customer Id XXXXXXX57  Branch Code 5901'
        'Name AAIMATAJIELECTRICALS  Branch Name HYDERABAD DAMMAIGUDA'
        'Phone +918686257882  IFSC Code CNRB0005901'
    """
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME

    fmt = _detect_format(lines)
    full_text = "\n".join(lines)

    # IFSC — present in both formats
    m = re.search(IFSC_PATTERN, full_text)
    if m:
        info["ifsc"] = m.group(1)

    if fmt == "loan":
        _parse_loan_account_info(lines, full_text, info)
    else:
        _parse_epassbook_account_info(lines, full_text, info)

    return info


def _parse_loan_account_info(lines, full_text, info):
    m = re.search(r"account\s+statement\s+as\s+of\s+(\d{2}-\d{2}-\d{4})", full_text, re.I)
    if m:
        info["statement_request_date"] = m.group(1)

    for line in lines:
        line_s = (line or "").strip()
        if not line_s:
            continue

        if info["account_holder"] is None:
            m = re.search(r"customer\s+name\s+(.+)", line_s, re.I)
            if m:
                info["account_holder"] = m.group(1).strip()

        if info["customer_id"] is None:
            m = re.search(r"customer\s+id\.?\s+(\d+)", line_s, re.I)
            if m:
                info["customer_id"] = m.group(1)

        if info["account_number"] is None:
            m = re.search(r"account\s+no\.?\s+(\d+)", line_s, re.I)
            if m:
                info["account_number"] = m.group(1)

        if info["currency"] is None:
            m = re.search(r"account\s+currency\s+(\w+)", line_s, re.I)
            if m:
                info["currency"] = m.group(1).upper()

        if info["acc_type"] is None:
            m = re.search(r"product\s+name\s+(.+)", line_s, re.I)
            if m:
                info["acc_type"] = m.group(1).strip()

        if info["statement_period"]["from"] is None:
            m = _PERIOD_LOAN_RE.search(line_s)
            if m:
                info["statement_period"]["from"] = m.group(1).strip()
                info["statement_period"]["to"]   = m.group(2).strip()

        if info.get("closing_balance") is None:
            m = re.search(r"closing\s+balance\s+(Rs\.?\s*[\d,]+\.\d+)", line_s, re.I)
            if m:
                info["closing_balance"] = _clean_amount_canara(m.group(1))

        if info.get("account_status") is None:
            m = re.search(r"account\s+status\s+(.+)", line_s, re.I)
            if m:
                info["account_status"] = m.group(1).strip()

    info["currency"] = info["currency"] or "INR"


def _parse_epassbook_account_info(lines, full_text, info):
    info["currency"] = "INR"

    for line in lines[:10]:
        line_s = (line or "").strip()
        if not line_s:
            continue

        # "Statement for A/c XXXXXXXXX0170 between 18-Jan-2024 and 12-Feb-2024"
        if info["statement_period"]["from"] is None:
            m = _PERIOD_EPASS_RE.search(line_s)
            if m:
                info["statement_period"]["from"] = _reformat_epass_date(m.group(1))
                info["statement_period"]["to"]   = _reformat_epass_date(m.group(2))
            # Also extract masked account number
            m2 = re.search(r"statement\s+for\s+a/c\s+([X\d]+)", line_s, re.I)
            if m2:
                info["account_number"] = m2.group(1)

        # "Customer Id XXXXXXX57  Branch Code 5901"
        if info["customer_id"] is None:
            m = re.search(r"customer\s+id\s+(\S+)", line_s, re.I)
            if m:
                info["customer_id"] = m.group(1)

        # "Name AAIMATAJIELECTRICALS  Branch Name HYDERABAD DAMMAIGUDA"
        if info["account_holder"] is None:
            m = re.search(r"^name\s+([A-Z][A-Z0-9\s]+?)(?:\s{2,}|branch|$)", line_s, re.I)
            if m:
                info["account_holder"] = m.group(1).strip()

        # Branch name
        if info["branch"] is None:
            m = re.search(r"branch\s+name\s+(.+?)(?:\s{2,}|$)", line_s, re.I)
            if m:
                info["branch"] = m.group(1).strip()


# ---------------------------------
# LOAN FORMAT TRANSACTION EXTRACTION
# (7-column table: exact-match column detection)
# ---------------------------------
def _detect_loan_cols(row):
    mapping = {}
    for idx, cell in enumerate(row):
        c = (cell or "").replace("\n", " ").strip().lower()
        if c == "transaction date":   mapping["date"] = idx
        elif c == "value date":        mapping["value_date"] = idx
        elif c in ("reference no.", "reference no"): mapping["ref_no"] = idx
        elif c == "description":       mapping["description"] = idx
        elif c == "debit":             mapping["debit"] = idx
        elif c == "credit":            mapping["credit"] = idx
        elif c == "balance":           mapping["balance"] = idx
    return mapping if "date" in mapping else {}


def _extract_loan_transactions(pdf_path):
    transactions   = []
    column_mapping = None
    last_txn       = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables(
                {"vertical_strategy": "lines", "horizontal_strategy": "lines"}
            )
            if not tables:
                continue
            for table in tables:
                if not table or len(table[0]) != 7:
                    continue
                for row in table:
                    if not row:
                        continue
                    row_text = " ".join((cell or "") for cell in row)
                    if _SKIP_ROW_RE.search(row_text):
                        continue
                    detected = _detect_loan_cols(row)
                    if detected:
                        column_mapping = detected
                        continue
                    if column_mapping is None:
                        continue
                    txn = _build_loan_txn(row, column_mapping, last_txn)
                    if txn:
                        transactions.append(txn)
                        last_txn = txn

    return transactions


def _build_loan_txn(row, col, last_txn):
    def _get(key):
        idx = col.get(key)
        if idx is None or idx >= len(row):
            return None
        return (row[idx] or "").replace("\n", " ").strip() or None

    date_raw = _get("date")
    if not date_raw:
        if last_txn:
            extra = _get("description")
            if extra:
                last_txn["description"] = (
                    (last_txn["description"] or "") + " " + extra
                ).strip()
        return None
    if not _DATE_LOAN_RE.match(date_raw):
        return None

    desc = _get("description")
    if desc:
        desc = re.sub(r"\s+", " ", desc).strip()

    return {
        "date":        _reformat_loan_date(date_raw),
        "description": desc,
        "ref_no":      _get("ref_no") or None,
        "debit":       _clean_amount_canara(_get("debit")),
        "credit":      _clean_amount_canara(_get("credit")),
        "balance":     _clean_amount_canara(_get("balance")),
    }


# ---------------------------------
# ePASSBOOK FORMAT TRANSACTION EXTRACTION
# (word-position based, 5-column)
# ---------------------------------
def _epass_col_of(w):
    x = w['x0']
    for col, (lo, hi) in _EPASS_COL.items():
        if lo <= x <= hi:
            return col
    return None


def _get_epass_page_lines(page):
    words = page.extract_words(x_tolerance=3, y_tolerance=3)
    txn_words = [
        w for w in words
        if w['top'] > 340
        and w['text'].lower() not in _EPASS_SKIP
    ]
    lines_map = defaultdict(list)
    for w in txn_words:
        bucket = round(w['top'] / 3) * 3
        lines_map[bucket].append(w)
    sorted_y = sorted(lines_map.keys())
    if not sorted_y:
        return []
    merged, group = [], [sorted_y[0]]
    for y in sorted_y[1:]:
        if y - group[-1] <= 4:
            group.append(y)
        else:
            merged.append(group)
            group = [y]
    merged.append(group)
    result = []
    for g in merged:
        gw = []
        for y in g:
            gw.extend(lines_map[y])
        gw.sort(key=lambda w: w['x0'])
        result.append(gw)
    return result


def _line_cols_epass(line_words):
    by_col = defaultdict(list)
    for w in line_words:
        col = _epass_col_of(w)
        if col:
            by_col[col].append(w['text'])
    return by_col


def _extract_epassbook_transactions(pdf_path):
    """
    ePassbook layout: description lines appear BEFORE the date+amount line.
    Strategy: accumulate pending description lines; when a date+amount line
    is found, assign pending lines as that transaction's description.
    Post-anchor lines (no amounts) become pending for the next transaction.
    """
    all_lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            all_lines.extend(_get_epass_page_lines(page))

    transactions = []
    current_txn  = None
    pending_desc = []

    for line_words in all_lines:
        by_col   = _line_cols_epass(line_words)
        date_tok = by_col.get("date", [])
        date_str = " ".join(date_tok).strip()
        is_anchor = bool(date_tok) and bool(_DATE_EPASS_RE.match(date_str))

        desc_words = by_col.get("description", [])
        desc_text  = " ".join(desc_words).strip()
        skip_desc  = (
            not desc_text
            or desc_text.startswith("Chq:")
            or desc_text.lower() in _EPASS_SKIP
        )

        if is_anchor:
            if current_txn:
                transactions.append(current_txn)

            full_parts = pending_desc[:]
            if desc_text and not skip_desc:
                full_parts.append(desc_text)

            current_txn = {
                "date":        date_str,
                "description": " ".join(full_parts).strip() or None,
                "credit":      _clean_amount_canara(" ".join(by_col.get("credit", [])).strip()),
                "debit":       _clean_amount_canara(" ".join(by_col.get("debit", [])).strip()),
                "balance":     _clean_amount_canara(" ".join(by_col.get("balance", [])).strip()),
            }
            pending_desc = []

        else:
            has_amounts = bool(
                by_col.get("credit") or by_col.get("debit") or by_col.get("balance")
            )
            if not has_amounts and not skip_desc:
                pending_desc.append(desc_text)

    if current_txn:
        transactions.append(current_txn)

    return transactions


# ---------------------------------
# UNIFIED TRANSACTION EXTRACTION
# ---------------------------------
def extract_transactions(pdf_path):
    """
    Auto-detects Canara Bank statement format and routes to the
    appropriate extractor:
      - 'loan'       → 7-column table (Loan Account Statement)
      - 'epassbook'  → word-position based (Statement for A/c)
    """
    # Detect format from first-page text
    with pdfplumber.open(pdf_path) as pdf:
        first_text = (pdf.pages[0].extract_text() or "").lower()

    if "statement for a/c" in first_text:
        return _extract_epassbook_transactions(pdf_path)
    else:
        return _extract_loan_transactions(pdf_path)