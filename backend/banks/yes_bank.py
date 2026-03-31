import re
import pdfplumber
from datetime import datetime
from collections import defaultdict
from .base import (
    default_account_info,
    clean_amount,
)


BANK_KEY = "yes_bank"
BANK_DISPLAY_NAME = "YES Bank"


# ---------------------------------------------------------------------------
# Column x-boundaries (derived from PDF word-position inspection)
# Transaction Date : x0 ~  28 –  75
# Value Date       : x0 ~  76 – 125
# Description      : x0 ~ 126 – 250
# Reference Number : x0 ~ 251 – 340
# Withdrawals      : x0 ~ 341 – 435
# Deposits         : x0 ~ 436 – 495
# Running Balance  : x0 ~ 496 – 580
# ---------------------------------------------------------------------------
_COL = {
    "date":        (28,  75),
    "value_date":  (76,  125),
    "description": (126, 250),
    "ref_no":      (251, 340),
    "debit":       (341, 435),
    "credit":      (436, 495),
    "balance":     (496, 580),
}

# Words below this y-position on a page are in the transaction table
_TXN_TOP_MIN = 300

# Yes Bank transaction date format in extracted text
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_HEADER_WORDS = {
    "transaction", "date", "value", "description", "reference",
    "number", "withdrawals", "deposits", "running", "balance",
}


def _reformat_date(date_str: str) -> str:
    """Convert YYYY-MM-DD (Yes Bank PDF format) to DD-MM-YYYY."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d-%m-%Y")
    except (ValueError, TypeError):
        return date_str


def _col_of(word):
    """Return the column key for a word based on its x0 position, or None."""
    x = word["x0"]
    for col, (lo, hi) in _COL.items():
        if lo <= x <= hi:
            return col
    return None


def _is_header_word(text):
    return text.lower() in _HEADER_WORDS


def _sort_key(txn: dict):
    """Parse DD-MM-YYYY for chronological sort. Unparseable dates sort last."""
    try:
        return datetime.strptime(txn["date"], "%d-%m-%Y")
    except (ValueError, TypeError, KeyError):
        return datetime.max


# ---------------------------------------------------------------------------
# Account info extraction
# ---------------------------------------------------------------------------

def extract_account_info(lines):
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME

    # FIX: Use newline join to preserve multi-space field boundaries
    full_text = "\n".join(line for line in lines if line)
    full_text_space = " ".join(line for line in lines if line)  # for single-line patterns

    # Account number — "Statement of account : 000263700005130"
    m = re.search(
        r"(?:statement\s+of\s+account|account\s+(?:no|number))\s*[:\-\.#]?\s*(\d{9,18})",
        full_text_space, re.I
    )
    if m:
        info["account_number"] = m.group(1).strip()

    # Statement period — "01 Apr 2025 - 29 Jun 2025"
    m = re.search(
        r"(\d{1,2}[\s\-][A-Za-z]{3}[\s\-]\d{4})\s*(?:to|[-\u2013]+)\s*(\d{1,2}[\s\-][A-Za-z]{3}[\s\-]\d{4})",
        full_text_space, re.I,
    )
    if m:
        info["statement_period"]["from"] = m.group(1).strip()
        info["statement_period"]["to"]   = m.group(2).strip()

    # Customer name — FIX: use newline as boundary instead of \s{2,}
    m = re.search(
        r"customer\s+name\s*[:\-]\s*([\w\s\.&]+?)(?:\n|\r|(?=\s{2,})|\baddress\b|\bbranch\b|\bmobile\b|\bemail\b|\bcust\b)",
        full_text, re.I,
    )
    if m:
        info["account_holder"] = m.group(1).strip()

    # Fallback: Primary Holder line
    if not info["account_holder"]:
        m = re.search(
            r"primary\s+holder\s+([\w\s\.&]+?)(?:\n|\r|\bnominee\b|\baccount\b)",
            full_text, re.I,
        )
        if m:
            info["account_holder"] = m.group(1).strip()

    # Branch — FIX: newline boundary
    m = re.search(
        r"branch\s+name\s*[:\-]\s*([A-Za-z0-9\s,]+?)(?:\n|\r|(?=\s{2,})|\baddress\b|\bifsc\b)",
        full_text, re.I,
    )
    if m:
        info["branch"] = m.group(1).strip()

    # IFSC — "YESB0000002"
    m = re.search(r"ifsc\s*(?:code)?\s*[:\-]\s*(YESB[A-Z0-9]{7})", full_text_space, re.I)
    if m:
        info["ifsc"] = m.group(1).strip()
    else:
        m = re.search(r"\b(YESB[A-Z0-9]{7})\b", full_text_space)
        if m:
            info["ifsc"] = m.group(1).strip()

    # MICR
    m = re.search(r"micr\s*(?:code)?\s*[:\-]?\s*(\d{9})", full_text_space, re.I)
    if m:
        info["micr"] = m.group(1).strip()

    # Customer ID
    m = re.search(r"cust(?:omer)?\s*(?:id|no)\s*[:\-]?\s*(\d+)", full_text_space, re.I)
    if m:
        info["customer_id"] = m.group(1).strip()

    info["currency"] = "INR"

    # Account type (CA/SA)
    m = re.search(r"\(([A-Z]{2,4}/[A-Z]{2,4})\s+product\s+name\)", full_text_space, re.I)
    if m:
        info["acc_type"] = m.group(1).strip()

    return info


# ---------------------------------------------------------------------------
# Transaction extraction — word-position based
# ---------------------------------------------------------------------------

def extract_transactions(pdf_path: str):
    """
    Extract transactions from a Yes Bank PDF statement.

    Yes Bank PDFs are laid out newest-page-first (page 1 = most recent txns).
    We collect all transactions in extraction order, then:
      1. reverse()  → oldest page first, preserving within-page sequence
      2. stable sort by date → correct chronological order (oldest → newest)
         without scrambling same-day transaction order.
    """
    transactions = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(
                keep_blank_chars=False,
                x_tolerance=3,
                y_tolerance=3,
            )

            # Keep only words in the transaction body area, skip column headers
            txn_words = [
                w for w in words
                if w["top"] >= _TXN_TOP_MIN and not _is_header_word(w["text"])
            ]

            if not txn_words:
                continue

            # ----------------------------------------------------------------
            # Group words into visual lines by y-coordinate proximity (±4 px)
            # ----------------------------------------------------------------
            lines_map = defaultdict(list)
            for w in txn_words:
                bucket = round(w["top"] / 4) * 4
                lines_map[bucket].append(w)

            sorted_y = sorted(lines_map.keys())

            # Merge adjacent y-buckets that are within 4 px of each other
            merged_groups = []
            current_group = [sorted_y[0]]
            for y in sorted_y[1:]:
                if y - current_group[-1] <= 4:
                    current_group.append(y)
                else:
                    merged_groups.append(current_group)
                    current_group = [y]
            merged_groups.append(current_group)

            # Build ordered list of lines, each line = list of words sorted by x
            page_lines = []
            for group in merged_groups:
                group_words = []
                for y in group:
                    group_words.extend(lines_map[y])
                group_words.sort(key=lambda w: w["x0"])
                page_lines.append(group_words)

            # ----------------------------------------------------------------
            # Parse transactions
            # ----------------------------------------------------------------
            current_txn = None

            for line_words in page_lines:
                by_col = defaultdict(list)
                for w in line_words:
                    col = _col_of(w)
                    if col:
                        by_col[col].append(w["text"])

                date_tokens = by_col.get("date", [])
                date_str    = " ".join(date_tokens).strip()
                is_new_txn  = bool(date_tokens) and bool(_DATE_RE.match(date_str))

                if is_new_txn:
                    if current_txn:
                        transactions.append(_finalise(current_txn))

                    desc_text  = " ".join(by_col.get("description", [])).strip()
                    ref_text   = " ".join(by_col.get("ref_no",      [])).strip()
                    debit_raw  = " ".join(by_col.get("debit",        [])).strip()
                    credit_raw = " ".join(by_col.get("credit",       [])).strip()
                    bal_raw    = " ".join(by_col.get("balance",      [])).strip()

                    current_txn = {
                        "date":        _reformat_date(date_str),
                        "description": desc_text or None,
                        "_ref_parts":  [ref_text] if ref_text else [],
                        "debit":       clean_amount(debit_raw)  if debit_raw  else None,
                        "credit":      clean_amount(credit_raw) if credit_raw else None,
                        "balance":     clean_amount(bal_raw)    if bal_raw    else None,
                    }

                else:
                    # Continuation line — append to current transaction
                    if current_txn is not None:
                        extra_desc = " ".join(by_col.get("description", [])).strip()
                        extra_ref  = " ".join(by_col.get("ref_no",      [])).strip()
                        if extra_desc:
                            current_txn["description"] = (
                                (current_txn["description"] or "") + " " + extra_desc
                            ).strip()
                        if extra_ref:
                            current_txn["_ref_parts"].append(extra_ref)

            if current_txn:
                transactions.append(_finalise(current_txn))

    # ----------------------------------------------------------------
    # FIX: PDF pages are newest-first → reverse to get oldest-first,
    # then stable-sort by date to handle any cross-page date overlaps.
    # Stable sort preserves within-page sequence for same-day txns.
    # ----------------------------------------------------------------
    transactions.reverse()
    transactions = sorted(transactions, key=_sort_key)

    return transactions


def _finalise(txn: dict) -> dict:
    """Merge accumulated ref parts into the description and remove the temp key."""
    ref_parts = txn.pop("_ref_parts", [])
    if ref_parts:
        ref_str = " ".join(ref_parts).strip()
        if ref_str:
            txn["description"] = (
                (txn["description"] or "") + " | REF:" + ref_str
            ).strip()
    return txn