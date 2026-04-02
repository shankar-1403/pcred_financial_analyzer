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

# Current & Saving date: "16-02-2023" possibly with time right after
# The double-char dedupe may merge the date and time digits sometimes,
# so we extract the date prefix specifically.
_DATE_CSV_PREFIX_RE = re.compile(r"^(\d{2}-\d{2}-\d{4})")

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
    r"end\s+of\s+statement|computer\s+output|"
    r"omission.*unauthorised|imb\s+users|phish.*always\s+login|"
    r"banking\s+grievance|reserve\s+bank\s+of\s+india|"
    r"toll\s*free\s*no|online\s+complaint",
    re.I,
)

# ePassbook column x-boundaries (from PDF word-position inspection)
_EPASS_COL = {
    "date":        (14,  100),
    "description": (101, 310),
    "credit":      (311, 410),
    "debit":       (411, 510),
    "balance":     (511, 620),
}
_EPASS_SKIP = {
    "date", "particulars", "deposits", "withdrawals", "balance",
    "opening", "closing", "disclaimer", "page",
}

# Current & Saving Account Statement column x-boundaries
_CSV_COL = {
    "date":        (10,  95),    # Txn date
    "value_date":  (96,  190),   # Value date
    "cheque":      (191, 265),   # Cheque No
    "description": (266, 435),   # Description
    "branch":      (436, 515),   # Branch Code
    "debit":       (516, 590),   # Debit
    "credit":      (591, 660),   # Credit
    "balance":     (661, 750),   # Balance
}
_CSV_HEADER_SKIP = {
    "txnd", "valued", "chequeN", "description", "branch", "debit",
    "credit", "balance", "code", "ate", "o.", "page", "of",
}


# ---------------------------------
# DOUBLE-CHAR DEDUPE (Current & Saving format)
# ---------------------------------
def _dedupe_chars(s):
    """
    Current & Saving PDFs encode each character twice: 'TTOOLLLL' → 'TOLL'.
    Only dedupe consecutive identical non-space characters.
    """
    if not s:
        return s
    result = []
    i = 0
    while i < len(s):
        if i + 1 < len(s) and s[i] == s[i + 1] and s[i] != ' ':
            result.append(s[i])
            i += 2
        else:
            result.append(s[i])
            i += 1
    return ''.join(result)


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
    Returns 'loan', 'epassbook', or 'current_saving'.

    Loan format         : 'Loan Account Statement'
    ePassbook format    : 'Statement for A/c'
    Current & Saving    : 'Current & Saving Account Statement' or
                          'Current & Saving Account Statement' (double-encoded)
    """
    for line in lines[:8]:
        l_raw  = (line or "").strip()
        l_dd   = _dedupe_chars(l_raw).lower()
        l_low  = l_raw.lower()

        if "loan account statement" in l_low:
            return "loan"
        if "statement for a/c" in l_low:
            return "epassbook"
        # double-encoded or normal "current & saving account statement"
        if "current" in l_dd and "saving" in l_dd and "account" in l_dd:
            return "current_saving"
        if "current" in l_low and "saving" in l_low and "account" in l_low:
            return "current_saving"

    return "loan"  # default


# ---------------------------------
# ACCOUNT INFO EXTRACTION
# ---------------------------------
def extract_account_info(lines):
    """
    Supports three Canara Bank statement formats:

    LOAN FORMAT (Loan Account Statement)
    ePASSBOOK FORMAT (Statement for A/c)
    CURRENT & SAVING FORMAT (Current & Saving Account Statement)
    """
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME

    # Dedupe lines for format detection (handles double-encoded PDF)
    deduped_lines = [_dedupe_chars(l) for l in lines]
    fmt = _detect_format(deduped_lines)
    full_text_dd = "\n".join(deduped_lines)

    # IFSC — present in all formats
    m = re.search(IFSC_PATTERN, full_text_dd)
    if m:
        info["ifsc"] = m.group(1)

    if fmt == "loan":
        _parse_loan_account_info(deduped_lines, full_text_dd, info)
    elif fmt == "epassbook":
        _parse_epassbook_account_info(deduped_lines, full_text_dd, info)
    else:
        _parse_current_saving_account_info(deduped_lines, full_text_dd, info)

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

        if info["statement_period"]["from"] is None:
            m = _PERIOD_EPASS_RE.search(line_s)
            if m:
                info["statement_period"]["from"] = _reformat_epass_date(m.group(1))
                info["statement_period"]["to"]   = _reformat_epass_date(m.group(2))
            m2 = re.search(r"statement\s+for\s+a/c\s+([X\d]+)", line_s, re.I)
            if m2:
                info["account_number"] = m2.group(1)

        if info["customer_id"] is None:
            m = re.search(r"customer\s+id\s+(\S+)", line_s, re.I)
            if m:
                info["customer_id"] = m.group(1)

        if info["account_holder"] is None:
            m = re.search(r"^name\s+([A-Z][A-Z0-9\s]+?)(?:\s{2,}|branch|$)", line_s, re.I)
            if m:
                info["account_holder"] = m.group(1).strip()

        if info["branch"] is None:
            m = re.search(r"branch\s+name\s+(.+?)(?:\s{2,}|$)", line_s, re.I)
            if m:
                info["branch"] = m.group(1).strip()


def _parse_current_saving_account_info(lines, full_text, info):
    """Parse account info from the double-encoded Current & Saving format."""
    info["currency"] = "INR"

    for line in lines:
        line_s = (line or "").strip()
        if not line_s:
            continue

        if info["account_holder"] is None:
            m = re.search(r"account\s+holders?\s+name\s+(.+)", line_s, re.I)
            if m:
                info["account_holder"] = m.group(1).strip()

        if info["customer_id"] is None:
            m = re.search(r"customer\s+id\s+(\d+)", line_s, re.I)
            if m:
                info["customer_id"] = m.group(1)

        if info["account_number"] is None:
            m = re.search(r"account\s+number\s+(\d+)", line_s, re.I)
            if m:
                info["account_number"] = m.group(1)

        if info["branch"] is None:
            m = re.search(r"branch\s+name\s+(.+)", line_s, re.I)
            if m:
                info["branch"] = m.group(1).strip()

        if info["micr"] is None:
            m = re.search(r"micr\s+code\s+(\d+)", line_s, re.I)
            if m:
                info["micr"] = m.group(1)

        if info["acc_type"] is None:
            m = re.search(r"product\s+name\s+(.+)", line_s, re.I)
            if m:
                info["acc_type"] = m.group(1).strip()

        if info["statement_period"]["from"] is None:
            m = _PERIOD_LOAN_RE.search(line_s)
            if m:
                info["statement_period"]["from"] = m.group(1).strip()
                info["statement_period"]["to"]   = m.group(2).strip()

        m = re.search(r"account\s+statement\s+as\s+of\s+([\d\-]+)", line_s, re.I)
        if m:
            info["statement_request_date"] = m.group(1)

        if info.get("closing_balance") is None:
            m = re.search(r"closing\s+balance\s+(Rs\.?\s*[\d,]+\.\d+)", line_s, re.I)
            if m:
                info["closing_balance"] = _clean_amount_canara(m.group(1))


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
# Fixed: per-page y-filtering, clean description boundaries
# ---------------------------------
def _epass_col_of(w):
    x = w['x0']
    for col, (lo, hi) in _EPASS_COL.items():
        if lo <= x <= hi:
            return col
    return None


def _get_epass_page_lines(page, is_first_page):
    words = page.extract_words(x_tolerance=3, y_tolerance=3)

    # On first page, skip the header block (above the table header row).
    # Find the y-position of the "Date" header word to know where data starts.
    # On continuation pages the table restarts at the top, so we only skip
    # the repeated column-header row (top < ~60).
    if is_first_page:
        # Find the "Date" column header to set the data-start threshold
        date_header_y = None
        for w in words:
            if w['text'].lower() == 'date' and w['x0'] < 60:
                date_header_y = w['top']
                break
        min_y = (date_header_y + 10) if date_header_y else 340
    else:
        # Skip only the repeated column-header row at the very top
        min_y = 55

    txn_words = [
        w for w in words
        if w['top'] >= min_y
        and w['text'].lower() not in _EPASS_SKIP
        # Skip "page N" footer
        and not (w['text'].lower() == 'page' or
                 (w['text'].isdigit() and w['top'] > 780))
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

    Key fix: per-page y-filtering so continuation pages (top=0 based) are
    handled correctly.  Also, description text on the SAME line as the date
    (i.e., text that is in the description column on the anchor row) is
    included; only subsequent description-only lines go into pending for the
    NEXT transaction.
    """
    all_lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for pi, page in enumerate(pdf.pages):
            all_lines.extend(_get_epass_page_lines(page, is_first_page=(pi == 0)))

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
        # Skip lines that are just a Chq reference or header keywords
        skip_desc  = (
            not desc_text
            or desc_text.startswith("Chq:")
            or desc_text.lower() in _EPASS_SKIP
        )

        if is_anchor:
            # Commit the previous transaction
            if current_txn:
                transactions.append(current_txn)

            # Build description: pre-anchor pending lines + inline desc (if any)
            full_parts = [p for p in pending_desc if p]
            if desc_text and not skip_desc:
                full_parts.append(desc_text)

            current_txn = {
                "date":        date_str,
                "description": " ".join(full_parts).strip() or None,
                "credit":      _clean_amount_canara(" ".join(by_col.get("credit", [])).strip()),
                "debit":       _clean_amount_canara(" ".join(by_col.get("debit",  [])).strip()),
                "balance":     _clean_amount_canara(" ".join(by_col.get("balance",[])).strip()),
            }
            # Reset pending — post-anchor description lines on SAME txn
            # are appended only if they appear before the NEXT anchor
            pending_desc = []

        else:
            has_amounts = bool(
                by_col.get("credit") or by_col.get("debit") or by_col.get("balance")
            )
            # Non-anchor lines with only description text are pre-description
            # for the NEXT transaction (the ePassbook layout places description
            # lines BEFORE the anchor row for that transaction).
            # However lines that have amounts but no date are continuation
            # lines of the previous transaction (rare but possible).
            if has_amounts and current_txn:
                # Merge amounts into current txn if missing
                if current_txn["debit"] is None:
                    v = _clean_amount_canara(" ".join(by_col.get("debit", [])).strip())
                    if v is not None:
                        current_txn["debit"] = v
                if current_txn["credit"] is None:
                    v = _clean_amount_canara(" ".join(by_col.get("credit", [])).strip())
                    if v is not None:
                        current_txn["credit"] = v
                if current_txn["balance"] is None:
                    v = _clean_amount_canara(" ".join(by_col.get("balance", [])).strip())
                    if v is not None:
                        current_txn["balance"] = v
                # Also append any description fragment
                if not skip_desc:
                    current_txn["description"] = (
                        (current_txn["description"] or "") + " " + desc_text
                    ).strip()
            elif not has_amounts and not skip_desc:
                pending_desc.append(desc_text)

    if current_txn:
        transactions.append(current_txn)

    return transactions


# ---------------------------------
# CURRENT & SAVING FORMAT TRANSACTION EXTRACTION
# (word-position based, 8-column, double-char encoded)
# ---------------------------------
def _csv_col_of(w):
    x = w['x0']
    for col, (lo, hi) in _CSV_COL.items():
        if lo <= x <= hi:
            return col
    return None


def _get_csv_page_lines(page):
    words = page.extract_words(x_tolerance=3, y_tolerance=3)

    # Dedupe each word's text
    proc_words = []
    for w in words:
        txt = _dedupe_chars(w['text']).strip()
        if txt:
            w2 = dict(w)
            w2['text'] = txt
            proc_words.append(w2)

    lines_map = defaultdict(list)
    for w in proc_words:
        bucket = round(w['top'] / 3) * 3
        lines_map[bucket].append(w)

    sorted_y = sorted(lines_map.keys())
    if not sorted_y:
        return []

    merged, group = [], [sorted_y[0]]
    for y in sorted_y[1:]:
        if y - group[-1] <= 5:
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


def _extract_current_saving_transactions(pdf_path):
    """
    Extract transactions from the Current & Saving Account Statement format.

    Layout: 8 columns (Txn Date | Value Date | Cheque No | Description |
                        Branch Code | Debit | Credit | Balance)
    Text is double-char encoded (each letter appears twice in raw PDF text).
    We decode with _dedupe_chars() per word before processing.

    The date column sometimes has the time concatenated to it; we extract
    just the DD-MM-YYYY prefix.
    """
    all_lines = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            all_lines.extend(_get_csv_page_lines(page))

    transactions = []
    current_txn  = None

    for line_words in all_lines:
        by_col = defaultdict(list)
        for w in line_words:
            col = _csv_col_of(w)
            if col:
                by_col[col].append(w['text'])

        # Extract date — the raw token may have time concatenated
        date_tok  = " ".join(by_col.get("date", [])).strip()
        date_match = _DATE_CSV_PREFIX_RE.match(date_tok)
        date_str   = date_match.group(1) if date_match else None

        desc_words = by_col.get("description", [])
        desc_text  = " ".join(desc_words).strip()

        # Skip header / footer lines
        if desc_text.lower() in {"description", "code"}:
            continue
        if date_tok.lower() in {"txnd ate", "txnd"}:
            continue
        if _SKIP_ROW_RE.search(desc_text):
            continue

        if date_str:
            # Commit previous
            if current_txn:
                transactions.append(current_txn)

            cheque_raw = " ".join(by_col.get("cheque", [])).strip() or None
            # Strip leading zeros from cheque number; treat "000000000000" as None
            if cheque_raw and re.fullmatch(r"0+", cheque_raw):
                cheque_raw = None

            current_txn = {
                "date":        date_str,
                "description": desc_text or None,
                "ref_no":      cheque_raw,
                "debit":       _clean_amount_canara(" ".join(by_col.get("debit",   [])).strip()),
                "credit":      _clean_amount_canara(" ".join(by_col.get("credit",  [])).strip()),
                "balance":     _clean_amount_canara(" ".join(by_col.get("balance", [])).strip()),
            }

        else:
            # Continuation line — append description to current transaction
            if current_txn and desc_text and not _SKIP_ROW_RE.search(desc_text):
                current_txn["description"] = (
                    (current_txn["description"] or "") + " " + desc_text
                ).strip()

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
      - 'epassbook'      → word-position based (Statement for A/c)
      - 'current_saving' → word-position based, double-encoded
                           (Current & Saving Account Statement)
      - 'loan'           → 7-column table (Loan Account Statement)
    """
    with pdfplumber.open(pdf_path) as pdf:
        first_page  = pdf.pages[0]
        raw_text    = first_page.extract_text() or ""
        dd_text     = _dedupe_chars(raw_text).lower()

    if "statement for a/c" in raw_text.lower():
        return _extract_epassbook_transactions(pdf_path)
    elif "current" in dd_text and "saving" in dd_text and "account" in dd_text:
        return _extract_current_saving_transactions(pdf_path)
    else:
        return _extract_loan_transactions(pdf_path)