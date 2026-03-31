import re
import pdfplumber
from collections import defaultdict
from datetime import datetime
from itertools import groupby

from .base import default_account_info

BANK_KEY          = "apna"
BANK_DISPLAY_NAME = "Apna Sahakari Bank"

# --- Column boundaries ---
_DATE_X_MAX  = 70
_DESC_X_MIN  = 70
_DESC_X_MAX  = 230
_INSTR_X_MIN = 230
_INSTR_X_MAX = 310
_DR_X_MIN    = 310
_DR_X_MAX    = 393
_CR_X_MIN    = 393
_CR_X_MAX    = 488
_BAL_X_MIN   = 488

# --- Patterns ---
_DATE_RE      = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_AMOUNT_RE    = re.compile(r"^[\d,]+\.\d{2}$")
_DASHES_RE    = re.compile(r"^-{10,}$")
_FOOTER_RE    = re.compile(r"totals\s*/\s*balance", re.I)
IFSC_PATTERN  = r"\b(ASBL[A-Z0-9]{7})\b"

# A continuation line that is PURELY: <9+digit ref> <8-digit DDMMYYYY>
# e.g. "308919167804 30032023"
# These lines appear under "IMPS Charges" rows and carry the instrument ref.
# They have NO alphabetic characters at all.
_REF_DATE_LINE_RE = re.compile(r'^(\d{9,})\s+(\d{8})$')

# Account info patterns
_CBS_ACCT_RE  = re.compile(r"cbs\s+account\s+no\s*[:\-]+\s*(\d+)", re.I)
_ACCT_RE      = re.compile(r"account\s*[:\-]\s*(\S+)\s+name\s*[:\-]\s*(.+)", re.I)
_ACCT_NO_RE   = re.compile(r"account\s*[:\-]\s*(\S+)", re.I)
_NAME_RE      = re.compile(r"\bname\s*[:\-]\s*(.+)", re.I)
_BRANCH_RE    = re.compile(r"branch\s*[:\-]\s*(.+)", re.I)
_FROM_DATE_RE = re.compile(r"from\s+date\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})", re.I)
_TO_DATE_RE   = re.compile(r"to\s+date\s*[:\-]?\s*(\d{2}/\d{2}/\d{4})", re.I)
_IFSC_RE      = re.compile(r"ifsc\s+code\s*[:\-]?\s*(ASBL[A-Z0-9]{7})", re.I)
_IFSC_ANY_RE  = re.compile(IFSC_PATTERN)
_OPEN_BAL_RE  = re.compile(r"opening\s+balance\s*[:\-]?\s*([\d,]+\.\d{2})", re.I)
_CLOSE_BAL_RE = re.compile(r"closing\s+balance\s+as\s+on\s+\S+\s+([\d,]+\.\d{2})", re.I)

# Words to skip globally (header/footer noise)
_SKIP_WORDS = frozenset({
    'Date','Particulars','Instruments','Dr','Amount','Cr','Total','Page','of',
    'APNA','SAHAKARI','BANK','LTD.','DADAR','THANE','(W)','User','Id',
    'ARSA','AR5A','R045006','-','STATEMENT','OF','ACCOUNTS','Printed','On',
})


# ---------------------------------
# HELPERS
# ---------------------------------

def _reformat_date(date_str):
    if not date_str:
        return date_str
    try:
        return datetime.strptime(date_str.strip(), "%d/%m/%Y").strftime("%d-%m-%Y")
    except ValueError:
        return date_str


def _clean_amount(value):
    """Parse Indian number format. Returns None for 0.00 (no transaction)."""
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s in ("-", "", "None"):
        return None
    try:
        f = float(s)
        return f if f != 0.0 else None
    except ValueError:
        return None


def _clean_balance(value):
    """Parse balance — 0.00 IS a valid balance."""
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s in ("-", "", "None"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _date_key(txn):
    try:
        return datetime.strptime(txn["date"], "%d-%m-%Y")
    except Exception:
        return datetime.max


def _order_same_date_group(group):
    if len(group) == 1:
        return group
    all_bal = {round(t["balance"], 2) for t in group if t["balance"] is not None}
    first = None
    for txn in group:
        prev = round(
            (txn["balance"] or 0) + (txn["debit"] or 0) - (txn["credit"] or 0), 2
        )
        if prev not in all_bal:
            first = txn
            break
    if first is None:
        return group
    ordered = [first]
    remaining = [t for t in group if t is not first]
    while remaining:
        lb = round(ordered[-1]["balance"], 2)
        matched = False
        for txn in remaining:
            prev = round(
                (txn["balance"] or 0) + (txn["debit"] or 0) - (txn["credit"] or 0), 2
            )
            if prev == lb:
                ordered.append(txn)
                remaining.remove(txn)
                matched = True
                break
        if not matched:
            ordered.extend(remaining)
            break
    return ordered


def _find_table_top(by_y):
    sorted_ys = sorted(by_y.keys())
    for y in sorted_ys:
        texts = {w['text'] for w in by_y[y]}
        if 'Particulars' in texts and 'Instruments' in texts:
            for y2 in sorted_ys:
                if y2 > y:
                    lt = " ".join(w['text'] for w in by_y[y2])
                    if _DASHES_RE.match(lt.strip()):
                        return y2 + 5
            return y + 30
    return 0


def _find_footer_top(by_y):
    for y in sorted(by_y.keys()):
        line = " ".join(w['text'] for w in by_y[y])
        if _FOOTER_RE.search(line):
            return y
    return float('inf')


def _row_text_in_zone(row_words, x_min, x_max):
    """Return joined text of all words in a row within x bounds."""
    return " ".join(
        w['text'] for w in sorted(row_words, key=lambda w: w['x0'])
        if x_min <= w['x0'] < x_max
    ).strip()


def _build_txn(band_words, date_str):
    """
    Build a single transaction dict from all words in a transaction's band.

    KEY INSIGHT from the actual PDF:
    ---------------------------------
    "IMPS Charges" transactions always have a continuation line of the form:
        <9+digit ref>  <8-digit DDMMYYYY>
    e.g. "308919167804 30032023"

    This continuation line falls in the description x-zone (x=70-230) because
    pdfplumber sees it as left-aligned text. It must be:
      - Recognised as a ref/date continuation (all digits, no alpha)
      - The 9+ digit part extracted as ref_no
      - The whole line EXCLUDED from description text

    All other continuation lines (e.g. "FINANCIAL SERVICES L", "MONTH 3/2023",
    "For 100001") contain alphabetic characters and are real description text.
    """
    # Group band words by y-row
    by_y = defaultdict(list)
    for w in band_words:
        by_y[round(w['top'] / 5) * 5].append(w)

    desc_parts = []
    instrument = None
    debit      = None
    credit     = None
    balance    = None

    for y in sorted(by_y.keys()):
        row_words = sorted(by_y[y], key=lambda w: w['x0'])

        # ----------------------------------------------------------------
        # Check if this entire row is a ref+date continuation line.
        # These lines look like: "308919167804 30032023"
        # They sit in the description x-zone but are purely numeric.
        # Rule: if ALL non-skip tokens in the desc+instr zone are digits
        #       AND match the pattern <9+ digits> <8 digits>, extract ref
        #       and skip the row from description.
        # ----------------------------------------------------------------
        zone_tokens = [
            w['text'] for w in row_words
            if _DESC_X_MIN <= w['x0'] < _INSTR_X_MAX
            and w['text'] not in _SKIP_WORDS
        ]
        if zone_tokens:
            zone_str = " ".join(zone_tokens)
            m = _REF_DATE_LINE_RE.match(zone_str)
            if m:
                # This is a pure ref+date continuation — extract ref, skip desc
                if instrument is None:
                    instrument = m.group(1)
                continue  # skip entire row for description

        # Normal row processing
        for w in row_words:
            x    = w['x0']
            text = w['text']

            if text in _SKIP_WORDS or _DASHES_RE.match(text):
                continue

            # Date column
            if x < _DATE_X_MAX and _DATE_RE.match(text):
                continue

            # Instrument column — short instrument numbers (100001 etc.)
            if _INSTR_X_MIN <= x < _INSTR_X_MAX:
                if re.match(r'^\d{5,}$', text) or re.match(r'^[A-Z0-9]{5,}$', text, re.I):
                    instrument = text
                continue

            # Debit column
            if _DR_X_MIN <= x < _DR_X_MAX and _AMOUNT_RE.match(text):
                debit = _clean_amount(text)
                continue

            # Credit column
            if _CR_X_MIN <= x < _CR_X_MAX and _AMOUNT_RE.match(text):
                credit = _clean_amount(text)
                continue

            # Balance column
            if x >= _BAL_X_MIN and _AMOUNT_RE.match(text):
                balance = _clean_balance(text)
                continue

            # Description column — all real text (alpha or mixed)
            if _DESC_X_MIN <= x < _DESC_X_MAX:
                desc_parts.append(text)

    # Deduplicate consecutive identical tokens
    deduped = []
    for p in desc_parts:
        if not deduped or deduped[-1] != p:
            deduped.append(p)

    description = re.sub(r"\s+", " ", " ".join(deduped)).strip() or None

    if balance is None:
        return None

    return {
        "date":        _reformat_date(date_str),
        "description": description,
        "ref_no":      instrument,
        "debit":       debit,
        "credit":      credit,
        "balance":     balance,
    }


# =============================================================================
# ACCOUNT INFO EXTRACTION
# =============================================================================

def extract_account_info(lines, pdf_path=None):
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"
    full_text = "\n".join(lines)

    # CBS account number (most reliable)
    m = _CBS_ACCT_RE.search(full_text)
    if m:
        info["account_number"] = m.group(1).strip()

    # "Account : CD/313   Name : ARROW ENGINEERING SERVICES" — same line
    m = _ACCT_RE.search(full_text)
    if m:
        if info["account_number"] is None:
            info["account_number"] = m.group(1).strip()
        info["account_holder"] = m.group(2).strip()
    else:
        m2 = _ACCT_NO_RE.search(full_text)
        if m2 and info["account_number"] is None:
            info["account_number"] = m2.group(1).strip()
        m3 = _NAME_RE.search(full_text)
        if m3:
            info["account_holder"] = m3.group(1).strip()

    # Branch — strip leading "20 - " or "20 – " prefix
    m = _BRANCH_RE.search(full_text)
    if m:
        raw = re.sub(r"^\d+\s*[-–]\s*", "", m.group(1).strip()).strip()
        info["branch"] = raw

    # Statement period
    m = _FROM_DATE_RE.search(full_text)
    if m:
        info["statement_period"]["from"] = _reformat_date(m.group(1))
    m = _TO_DATE_RE.search(full_text)
    if m:
        info["statement_period"]["to"] = _reformat_date(m.group(1))

    # IFSC
    m = _IFSC_RE.search(full_text)
    if m:
        info["ifsc"] = m.group(1).strip()
    else:
        m = _IFSC_ANY_RE.search(full_text)
        if m:
            info["ifsc"] = m.group(1).strip()

    # Opening / closing balance
    m = _OPEN_BAL_RE.search(full_text)
    if m:
        info["opening_balance"] = _clean_balance(m.group(1))
    m = _CLOSE_BAL_RE.search(full_text)
    if m:
        info["closing_balance"] = _clean_balance(m.group(1))

    return info


def extract_account_info_full(pdf_path, lines):
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

def extract_transactions(pdf_path):
    transactions = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            words = page.extract_words(
                keep_blank_chars=False, x_tolerance=3, y_tolerance=3
            )
            if not words:
                continue

            by_y = defaultdict(list)
            for w in words:
                by_y[round(w['top'])].append(w)

            table_top  = _find_table_top(by_y)
            footer_top = _find_footer_top(by_y)

            rows = defaultdict(list)
            for w in words:
                if table_top <= w['top'] < footer_top:
                    rows[round(w['top'] / 5) * 5].append(w)

            if not rows:
                continue

            # Find rows that start with a date in the date column
            date_rows = []
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
                prev_mid = (date_ys[i - 1] + date_y) // 2 if i > 0 else table_top

                # 80% toward next date — keeps multi-line continuation text
                # (e.g. "FINANCIAL SERVICES L / 0104SLNEF") inside its own band
                if i + 1 < len(date_ys):
                    next_mid = date_y + int(0.8 * (date_ys[i + 1] - date_y))
                else:
                    next_mid = footer_top

                band_words = []
                for y in sorted(rows.keys()):
                    if prev_mid < y <= next_mid:
                        band_words.extend(rows[y])

                txn = _build_txn(band_words, date_str)
                if txn:
                    transactions.append(txn)

    # Sort chronologically (stable — preserves intra-day PDF order)
    transactions.sort(key=_date_key)

    # Re-order within same-date groups using balance chain
    final = []
    for _, grp in groupby(transactions, key=lambda t: t["date"]):
        final.extend(_order_same_date_group(list(grp)))
    transactions = final

    # Assign ascending row_id
    for i, txn in enumerate(transactions, 1):
        txn["row_id"] = i

    return transactions