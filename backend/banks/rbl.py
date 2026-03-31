import re
import pdfplumber
from collections import defaultdict
from datetime import datetime
from itertools import groupby

from .base import (
    default_account_info,
    clean_amount,
)

BANK_KEY          = "rbl"
BANK_DISPLAY_NAME = "RBL Bank"


# =============================================================================
# RBL BANK — PDF CHARACTERISTICS
# =============================================================================
# - Text-based PDF but pdfplumber's table extractor returns only a 1-column
#   merged blob — unusable for field splitting.
# - Word-coordinate extraction is the reliable approach.
#
# 7-column layout (x0 positions, empirically determined):
#   Transaction Date  : x0  ~29  (< 100)
#   Transaction Details: x0 ~139 – 340
#   Cheque ID         : x0 ~345 – 425  (almost always empty)
#   Value Date        : x0 ~428 – 540
#   Withdrawal Amt    : x0 ~541 – 682
#   Deposit Amt       : x0 ~683 – 860
#   Balance           : x0 ~861 +
#
# Date format : DD/MM/YYYY  →  output DD-MM-YYYY
# Amounts     : Indian comma format '23,600.00', '2,00,000.00'
# Empty cells : simply absent (no '-' placeholder)
# Description : multi-line; the date word acts as the row anchor and we
#               collect description words from the midpoint above to
#               the midpoint below the anchor.
# Footer stop : "Statement Summary" heading on the last page marks the
#               end of transaction data — words below it are ignored.
#
# Account info: page 1 header text (no structured sub-table).
#   Account Name / CIF ID / A/C Type / A/c Status / Account Number / Period
#   Opening/Closing balance from the "Statement Summary" block (last page).
#
# SORT ORDER:
#   RBL PDF is printed newest-first (13/06 at top, 20/05 at bottom).
#   Steps:
#     1. Collect transactions in PDF order (newest-first).
#     2. reverse() → oldest-first (preserves intra-day PDF order within each date).
#     3. stable sort by date → correct chronological order.
#     4. For each same-date group, use balance chain to fix intra-day order.
#     5. Assign row_id: 1 = oldest, N = newest.
# =============================================================================


# ---------------------------------
# COLUMN X-BOUNDARIES
# ---------------------------------
_DATE_X_MAX   = 100
_DESC_X_MIN   = 130
_DESC_X_MAX   = 420
_VDATE_X_MIN  = 428
_VDATE_X_MAX  = 540
_WDL_X_MIN    = 541
_WDL_X_MAX    = 682
_DEP_X_MIN    = 683
_DEP_X_MAX    = 860
_BAL_X_MIN    = 861


# ---------------------------------
# REGEX PATTERNS
# ---------------------------------
_DATE_RE    = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_AMOUNT_RE  = re.compile(r"^[\d,]+\.\d{2}$")
_IFSC_RE    = re.compile(r"\b(RATN[A-Z0-9]{7})\b")   # RBL IFSC prefix
_ACCT_RE    = re.compile(r"account\s*number\s*[:\-]?\s*(\d{9,})", re.I)
_PERIOD_RE  = re.compile(
    r"period\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})", re.I
)
_CIF_RE     = re.compile(r"cif\s*id\s*[:\-]?\s*(\d+)", re.I)
_ACCTYPE_RE = re.compile(r"a/c\s*type\s*[:\-]?\s*(.+)", re.I)
_ACCNAME_RE = re.compile(r"account\s*name\s*[:\-]?\s*(.+)", re.I)
_BRANCH_RE  = re.compile(r"home\s*branch\s*[:\-]?\s*(.+)", re.I)
_OPEN_BAL_RE  = re.compile(r"opening\s*balance\s*[:\-]?\s*[₹]?\s*([\d,]+\.\d{2})", re.I)
_CLOSE_BAL_RE = re.compile(r"closing\s*balance\s*[:\-]?\s*[₹]?\s*([\d,]+\.\d{2})", re.I)

# Words to skip when building description
_SKIP_WORDS = frozenset({
    '(₹)', 'Date', 'Amt', 'Withdrawl', 'Withdrawal', 'Deposit',
    'Balance', 'Details', 'Transaction', 'Cheque', 'ID', 'Value',
    'List', '-', '.', '₹', 'Page', 'of',
})

# Footer sentinel — stop collecting when we hit this
_FOOTER_RE = re.compile(r"statement\s+summary", re.I)


# ---------------------------------
# HELPERS
# ---------------------------------
def _reformat_date(date_str: str) -> str:
    """Convert 'DD/MM/YYYY' → 'DD-MM-YYYY'."""
    if not date_str:
        return date_str
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y").strftime("%d-%m-%Y")
    except ValueError:
        return date_str


def _clean_amount_rbl(value) -> float | None:
    """Strip Indian commas, return float or None."""
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s in ("-", "", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _find_table_top(by_y: dict) -> float:
    """
    Find the y-coordinate of the column header row
    ('Transaction Details' side by side) so we skip the account info block.
    Returns the y just below the header, or 0 if not found.
    """
    for y in sorted(by_y.keys()):
        texts = {w['text'] for w in by_y[y]}
        if 'Transaction' in texts and 'Details' in texts:
            return y + 30   # skip the header itself
    return 0


def _find_footer_top(by_y: dict) -> float:
    """
    Find the y-coordinate of 'Statement Summary' heading so we stop there.
    'Statement' and 'Summary' are separate words in the PDF, so we join
    each row's words into a single string before matching.
    Returns inf if not found.
    """
    for y in sorted(by_y.keys()):
        line_text = " ".join(w['text'] for w in by_y[y])
        if _FOOTER_RE.search(line_text):
            return y
    return float('inf')


def _sort_key(txn: dict):
    try:
        return datetime.strptime(txn["date"], "%d-%m-%Y")
    except (ValueError, TypeError, KeyError):
        return datetime.max


def _order_same_date_group(group: list[dict]) -> list[dict]:
    """
    For same-date transactions, reconstruct correct order using balance chain.

    Each transaction's balance is the AFTER balance.
    So: txn[n].prev_balance = txn[n].balance + debit - credit
    The first transaction in the sequence is the one whose prev_balance
    does not match any other transaction's after-balance.

    Fallback: if chain is broken (e.g. duplicate amounts cause ambiguity),
    the remaining transactions are appended in their current order.
    """
    if len(group) == 1:
        return group

    all_balances = {round(t["balance"], 2) for t in group if t["balance"] is not None}

    # Find the first txn: its prev_balance is not in any other txn's balance set
    first = None
    for txn in group:
        debit    = txn["debit"]  or 0
        credit   = txn["credit"] or 0
        prev_bal = round((txn["balance"] or 0) + debit - credit, 2)
        if prev_bal not in all_balances:
            first = txn
            break

    if first is None:
        # Can't determine chain start — return as-is (reversed PDF order = best guess)
        return group

    ordered   = [first]
    remaining = [t for t in group if t is not first]

    while remaining:
        last_bal = round(ordered[-1]["balance"], 2)
        matched  = False
        for txn in remaining:
            debit    = txn["debit"]  or 0
            credit   = txn["credit"] or 0
            prev_bal = round((txn["balance"] or 0) + debit - credit, 2)
            if prev_bal == last_bal:
                ordered.append(txn)
                remaining.remove(txn)
                matched = True
                break
        if not matched:
            # Chain broken — append rest in current order
            ordered.extend(remaining)
            break

    return ordered


# =============================================================================
# ACCOUNT INFO EXTRACTION
# =============================================================================
def extract_account_info(lines: list[str], pdf_path: str = None) -> dict:
    """
    Extract account metadata from RBL Bank statement page 1.

    Relevant header text:
        Account Name: BEAUTY & BEYOND PRIVATE LIMITED
        Home Branch: JANAKPURI (0270)
        CIF ID: 203133408
        A/C Type: Current Accounts
        A/c Status: Active
        Statement Of Transactions  409001966894    ← account number (next token)
        Period: 20/05/2025 to 13/06/2025
        (Opening/Closing balance from Statement Summary on last page)
    """
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)

    # Account number: appears after "Statement Of Transactions in Account Number:"
    m = re.search(
        r"statement\s+of\s+transactions\s+in\s+account\s+number\s*[:\-]?\s*(\d{9,})",
        full_text, re.I
    )
    if not m:
        # Fallback: bare account number after "Statement Of Transactions"
        m = re.search(r"statement\s+of\s+transactions\s+(\d{9,})", full_text, re.I)
    if m:
        info["account_number"] = m.group(1)

    # Statement period
    m = _PERIOD_RE.search(full_text)
    if m:
        info["statement_period"]["from"] = _reformat_date(m.group(1))
        info["statement_period"]["to"]   = _reformat_date(m.group(2))

    # CIF ID
    m = _CIF_RE.search(full_text)
    if m:
        info["customer_id"] = m.group(1)

    # IFSC (may be blank in the header — just attempt)
    m = _IFSC_RE.search(full_text)
    if m:
        info["ifsc"] = m.group(1)

    # Line-by-line for name, branch, account type
    for line in lines:
        s = line.strip()
        if not s:
            continue

        if info["account_holder"] is None:
            m = _ACCNAME_RE.search(s)
            if m:
                candidate = m.group(1).strip()
                if candidate and len(candidate) > 1:
                    info["account_holder"] = candidate

        if info["branch"] is None:
            m = _BRANCH_RE.search(s)
            if m:
                candidate = m.group(1).strip()
                # Strip branch code suffix like "(0270)"
                candidate = re.sub(r"\s*\(\d+\)\s*$", "", candidate).strip()
                if candidate and len(candidate) > 1:
                    info["branch"] = candidate

        if info["acc_type"] is None:
            m = _ACCTYPE_RE.search(s)
            if m:
                val = m.group(1).strip()
                if val and val.upper() not in ("₹", "INR"):
                    info["acc_type"] = val

    # Opening / closing balance from Statement Summary (last page)
    m = _OPEN_BAL_RE.search(full_text)
    if m:
        info["opening_balance"] = _clean_amount_rbl(m.group(1))

    m = _CLOSE_BAL_RE.search(full_text)
    if m:
        info["closing_balance"] = _clean_amount_rbl(m.group(1))

    return info


def extract_account_info_full(pdf_path: str, lines: list[str]) -> dict:
    """Dispatcher-compatible wrapper — also reads all pages for summary."""
    # Collect lines from all pages so Statement Summary is included
    all_lines = list(lines)
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages[1:]:
                t = page.extract_text() or ""
                all_lines.extend(t.splitlines())
    except Exception:
        pass
    return extract_account_info(all_lines, pdf_path=pdf_path)


# =============================================================================
# TRANSACTION EXTRACTION
# =============================================================================
def extract_transactions(pdf_path: str) -> list[dict]:
    """
    Extract all transactions from an RBL Bank PDF statement.

    Strategy (word-coordinate based):

    1.  For each page, call extract_words() to get word bounding boxes.
    2.  Find the column header row y ('Transaction Details' keyword) —
        all words above this are account-info header, ignored.
    3.  Find 'Statement Summary' y on the last page — stop at this line.
    4.  Group remaining words into y-bands (5 pt buckets).
    5.  Identify "anchor" rows: rows where a DD/MM/YYYY date word appears
        at x0 < 100 (the Transaction Date column).
    6.  For each anchor, collect all words in the half-open band between
        the midpoint-above and midpoint-below.
    7.  Classify each word into its column by x0 position.
    8.  Build the transaction dict from classified words.

    SORT ORDER:
    -----------
    RBL PDF is printed newest-first. Steps to get correct chronological order:
      1. Collect in PDF order (newest-first).
      2. reverse() → oldest-first, preserving intra-day PDF sequence.
      3. stable sort by date → correct cross-date order.
      4. Balance chain fix for each same-date group.
      5. Assign row_id: 1 = oldest, N = newest.
    """
    transactions: list[dict] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(
                keep_blank_chars=False,
                x_tolerance=3,
                y_tolerance=3,
            )
            if not words:
                continue

            # Build y→words index
            by_y: dict = defaultdict(list)
            for w in words:
                by_y[round(w['top'])].append(w)

            table_top   = _find_table_top(by_y)
            footer_top  = _find_footer_top(by_y)

            # Group into 5-pt y-bands, only in transaction area
            rows: dict = defaultdict(list)
            for w in words:
                if table_top <= w['top'] < footer_top:
                    key = round(w['top'] / 5) * 5
                    rows[key].append(w)

            if not rows:
                continue

            # Find anchor date rows
            date_rows: list = []
            for y in sorted(rows.keys()):
                line = sorted(rows[y], key=lambda w: w['x0'])
                for w in line:
                    if w['x0'] < _DATE_X_MAX and _DATE_RE.match(w['text']):
                        date_rows.append((y, w['text']))
                        break

            if not date_rows:
                continue

            date_ys = [dr[0] for dr in date_rows]

            for i, (date_y, date_str) in enumerate(date_rows):
                # Vertical band: midpoint-above to midpoint-below
                prev_mid = (date_ys[i - 1] + date_y) // 2 if i > 0 else table_top
                next_mid = (date_y + date_ys[i + 1]) // 2 \
                           if i + 1 < len(date_ys) else footer_top

                band_words = []
                for y in sorted(rows.keys()):
                    if prev_mid < y <= next_mid:
                        band_words.extend(rows[y])

                txn = _build_txn(band_words, date_str)
                if txn:
                    transactions.append(txn)

    # ------------------------------------------------------------------
    # Step 1: reverse — PDF is newest-first, so reversing gives
    #         oldest-first while preserving intra-day PDF sequence.
    # ------------------------------------------------------------------
    transactions.reverse()

    # ------------------------------------------------------------------
    # Step 2: stable sort by date — same-date txns keep the order from
    #         Step 1 (reversed PDF order) as their initial sequence.
    # ------------------------------------------------------------------
    transactions.sort(key=_sort_key)

    # ------------------------------------------------------------------
    # Step 3: fix same-date ordering using balance chain.
    #         This is the authoritative tiebreaker — more reliable than
    #         PDF position for intra-day sequencing.
    # ------------------------------------------------------------------
    final: list[dict] = []
    for _, grp in groupby(transactions, key=lambda t: t["date"]):
        final.extend(_order_same_date_group(list(grp)))
    transactions = final

    # ------------------------------------------------------------------
    # Step 4: assign row_id — 1 = oldest, N = newest.
    #         _normalize_df_with_rowid does the same thing, but we assign
    #         here too so callers that work with the raw list also get it.
    # ------------------------------------------------------------------
    for i, txn in enumerate(transactions, 1):
        txn["row_id"] = i

    return transactions


def _build_txn(band_words: list, date_str: str) -> dict | None:
    """Classify band words into columns and return a transaction dict."""
    desc_parts:  list[str] = []
    value_date:  str | None  = None
    withdrawal:  float | None = None
    deposit:     float | None = None
    balance:     float | None = None

    for w in band_words:
        x    = w['x0']
        text = w['text']

        if text in _SKIP_WORDS:
            continue

        # Transaction date anchor — skip
        if x < _DATE_X_MAX and _DATE_RE.match(text):
            continue

        # Value date
        if _VDATE_X_MIN <= x < _VDATE_X_MAX and _DATE_RE.match(text):
            value_date = text
            continue

        # Withdrawal (debit)
        if _WDL_X_MIN <= x < _WDL_X_MAX and _AMOUNT_RE.match(text):
            withdrawal = _clean_amount_rbl(text)
            continue

        # Deposit (credit)
        if _DEP_X_MIN <= x < _DEP_X_MAX and _AMOUNT_RE.match(text):
            deposit = _clean_amount_rbl(text)
            continue

        # Balance
        if x >= _BAL_X_MIN and _AMOUNT_RE.match(text):
            balance = _clean_amount_rbl(text)
            continue

        # Description words
        if _DESC_X_MIN <= x < _DESC_X_MAX:
            desc_parts.append(text)

    # Deduplicate adjacent identical tokens (PDF layout artefact)
    deduped: list[str] = []
    for p in desc_parts:
        if not deduped or deduped[-1] != p:
            deduped.append(p)

    description = re.sub(r"\s+", " ", " ".join(deduped)).strip() or None

    return {
        "date":        _reformat_date(date_str),
        "description": description,
        "ref_no":      None,   # Cheque ID col is empty for all digital txns
        "debit":       withdrawal,
        "credit":      deposit,
        "balance":     balance,
    }