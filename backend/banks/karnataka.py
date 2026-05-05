import re
import pdfplumber
from collections import defaultdict
from datetime import datetime

from .base import default_account_info

BANK_KEY          = "karnataka"
BANK_DISPLAY_NAME = "Karnataka Bank"

# =============================================================================
# KARNATAKA BANK — TWO PDF FORMATS
# =============================================================================
#
# FORMAT 1 (f1) — text-based, older layout:
#   Lines: DD-MM-YYYY  <description>  <amounts>
#
# FORMAT 2 (f2) — modern layout (General Details header):
#   Table: Date | Description | Cheque No | Debit | Credit | Balance (INR)
#   Date:  DD/MM/YYYY  OR  DD/MM/YY   ← both supported
#   Balance: NEGATIVE for overdraft e.g. -12,19,18,092.98
#
# BUGS FIXED IN THIS VERSION:
#
#  FIX 1 (_extract_f2_words — CRASH on page 2+):
#    table_start_y was left as None when no header row found on a continuation
#    page. The subsequent "if y <= table_start_y" comparison raised TypeError.
#    Fix: reset table_start_y = 0 when reusing col_bounds from a previous page.
#
#  FIX 2 (_extract_f2_words — amounts with leading/trailing spaces):
#    get_col() can return " 1,28,013.98" with a leading space.
#    _AMOUNT_CELL_RE.match() failed on un-stripped text.
#    Fix: strip() before _AMOUNT_CELL_RE.match().
#
#  FIX 3 (extract_account_info — branch continuation missing):
#    After setting info["branch"] = "MANGALORE", the next line "DONGERKERY"
#    was never appended because "if info['branch'] is None" was False.
#    Fix: track prev_branch flag independently of info["branch"].
#
#  FIX 4 (_F2_DATE_PAT — 2-digit year):
#    Statement 1 uses DD/MM/YY dates (31/10/23). Pattern was \d{4} only.
#    Fix: changed to \d{2,4}.  (already present in this version)
#
#  FIX 5 (extract_account_info — full account holder name):
#    "Name:" field is truncated in two-column layout. Nickname field on the
#    same line as Number has the full untruncated name.
#    Fix: prefer _F2_NICKNAME_PAT.  (already present in this version)
# =============================================================================

# ---------------------------------
# SHARED PATTERNS
# ---------------------------------
_AMOUNT_PAT      = re.compile(r"-?[\d,]+\.\d{2}")
_OPENING_BAL_PAT = re.compile(r"opening\s+balance\s+([\d,]+\.\d{2})", re.I)
_IFSC_PAT        = re.compile(r"ifsc\s*(?:code)?\s*[:\-]?\s*(KARB[A-Z0-9]{7})", re.I)
_AMOUNT_CELL_RE  = re.compile(r"^-?[\d,]+\.\d{2}$")
_F2_DATE_ONLY_RE = re.compile(r"^\d{2}/\d{2}/\d{2,4}$")   # FIX 4: \d{2,4}

_SKIP_PAT = re.compile(
    r"^(Account\s+Statement\s*$"
    r"|General\s+Details\s*$"
    r"|Balance\s+Details\s*$"
    r"|Page\s+\d+\s+of\s+\d+"
    r"|Statement\s+Generated\s+for\s+the\s+period"
    r"|Date\s+Description\s+Chq"
    r"|Date\s+Description\s+Cheque"
    r"|Transactions\s+List\s+-"
    r"|Withdrawal\s+Deposit\s+Balance"
    r"|Debit\s+Credit\s+Balance)",
    re.I,
)

_HEADER_CONT_PAT = re.compile(
    r"^(Nickname\s*:|Status\s*:|Category\s*:|Open\s+Date\s*:|Drawing\s+Power\s*:"
    r"|Sanction\s+Limit\s*:|Debit\s+Accrued|Credit\s+Accrued|Primary\s+Account"
    r"|Date\s+From|Date\s+To|Transactions\s+for|Last\s+N|Amount\s+From|Amount\s+Type)",
    re.I,
)

# ---------------------------------
# FORMAT 1 PATTERNS
# ---------------------------------
_F1_PERIOD_PAT = re.compile(
    r"period\s*[:\-]?\s*(\d{2}-[A-Za-z]{3}-\d{4})\s*[-–to]+\s*(\d{2}-[A-Za-z]{3}-\d{4})",
    re.I,
)
_F1_ACCT_PAT   = re.compile(r"a/?c\s*number\s*[:\-]?\s*(\d{10,20})", re.I)
_F1_NAME_PAT   = re.compile(r"^name\s+([A-Z].{3,60})$", re.I)
_F1_BRANCH_PAT = re.compile(r"branch\s*name\s*[:\-]?\s*(.+)", re.I)
_F1_MICR_PAT   = re.compile(r"micr\s*[:\-]?\s*(\d{9})", re.I)
_F1_DATE_PAT   = re.compile(r"^(\d{2}-\d{2}-\d{4})\s+(.*)")
_F1_AMOUNTS_ONLY = re.compile(r"^[\d,]+\.\d{2}(\s+[\d,]+\.\d{2})*$")

# ---------------------------------
# FORMAT 2 PATTERNS
# ---------------------------------
_F2_ACCT_PAT     = re.compile(r"(?:^|\b)number\s*:\s*(\d{10,20})", re.I)
# FIX 5: Nickname has the FULL untruncated account holder name
_F2_NICKNAME_PAT = re.compile(r"Nickname\s*:\s*(.+)", re.I)
# FIX: lookahead prevents capturing right-column text in two-column layout
_F2_TYPE_PAT     = re.compile(r"^type\s*:\s*(.+?)(?=\s+Category\s*:|$)", re.I)
_F2_BRANCH_PAT   = re.compile(r"^branch\s*:\s*(.+?)(?=\s+Drawing\s+Power\s*:|$)", re.I)
_F2_CURRENCY_PAT = re.compile(r"^currency\s*:\s*([A-Z]{3})", re.I)
_F2_PERIOD_FROM  = re.compile(r"date\s+from\s*\(?dd/mm/yyyy\)?\s*:\s*(\d{2}/\d{2}/\d{2,4})", re.I)
_F2_PERIOD_TO    = re.compile(r"date\s+to\s*\(?dd/mm/yyyy\)?\s*:\s*(\d{2}/\d{2}/\d{2,4})", re.I)
_F2_DATE_PAT     = re.compile(r"^(\d{2}/\d{2}/\d{2,4})\s+(.*)")   # FIX 4
_F2_AMOUNTS_ONLY = re.compile(r"^-?[\d,]+\.\d{2}(\s+-?[\d,]+\.\d{2})*$")

_TYPE_MAP = {
    "SB": "Savings Account", "CA": "Current Account",
    "CURRENT": "Current Account", "SAVINGS": "Savings Account",
    "OVERDRAFT": "Overdraft", "OD": "Overdraft", "CC": "Cash Credit",
}

_ROLE_KEYWORDS = {
    "date":    ["date"],
    "desc":    ["description", "particulars", "narration", "detail"],
    "cheque":  ["cheque", "chq", "ref"],
    "debit":   ["debit", "withdrawal"],
    "credit":  ["credit", "deposit"],
    "balance": ["balance"],
}

_TABLE_HEADER_RE = re.compile(
    r"transactions\s+list|date\s+description|date\s+desc",
    re.I,
)

# ---------------------------------
# HELPERS
# ---------------------------------
def _parse_amount(s: str) -> float | None:
    if not s:
        return None
    s = str(s).replace(",", "").strip()
    if not s or s in ("-", "NIL", "-NIL-"):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _fmt_date_dmy_dash(s: str) -> str:
    s = s.strip()
    for fmt in ["%d-%m-%Y", "%d-%b-%Y"]:
        try:
            return datetime.strptime(s, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    return s


def _fmt_date_dmy_slash(s: str) -> str:
    s = s.strip()
    for fmt in ["%d/%m/%Y", "%d/%m/%y"]:
        try:
            return datetime.strptime(s, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    return s


def _is_date_f2(s: str) -> bool:
    return bool(_F2_DATE_ONLY_RE.match(s.strip()))


def _is_skip(line: str) -> bool:
    return bool(_SKIP_PAT.match(line.strip()))


def _sort_key(txn: dict):
    try:
        return datetime.strptime(txn["date"], "%d-%m-%Y")
    except (ValueError, TypeError, KeyError):
        return datetime.max


def _detect_format(lines: list[str]) -> str:
    header = "\n".join(lines[:40]).lower()
    if any(x in header for x in [
        "general details", "transactions list -", "date from(dd/mm/yyyy)",
        "date from(dd/mm", "overdraft general", "drawing power",
        "sanction limit", "open date", "ca-money",
    ]):
        return "f2"
    if any(x in header for x in [
        "statement generated for the period", "a/c number", "upi id", "joint holder",
    ]):
        return "f1"
    for line in lines[:100]:
        s = line.strip()
        if re.match(r"^\d{2}/\d{2}/\d{2,4}\s+", s):   # FIX 4
            return "f2"
        if re.match(r"^\d{2}-\d{2}-\d{4}\s+", s):
            return "f1"
    return "f1"


def _identify_role(word_text: str) -> str | None:
    t = word_text.lower().strip()
    for role, keywords in _ROLE_KEYWORDS.items():
        if any(kw in t for kw in keywords):
            return role
    return None


def _build_col_bounds(role_x: dict, page_width: float) -> dict:
    if not role_x:
        return {}
    sorted_roles = sorted(role_x.items(), key=lambda r: r[1])
    bounds = {}
    for i, (role, x_start) in enumerate(sorted_roles):
        x_end = sorted_roles[i + 1][1] if i + 1 < len(sorted_roles) else page_width
        bounds[role] = (x_start, x_end)
    return bounds


def _words_in_col(words: list[dict], x_min: float, x_max: float) -> str:
    tokens = [w["text"] for w in sorted(words, key=lambda w: w["x0"])
              if x_min <= w["x0"] < x_max]
    return " ".join(tokens).strip()


# =============================================================================
# ACCOUNT INFO EXTRACTION
# =============================================================================
def extract_account_info(lines: list[str], pdf_path: str = None) -> dict:
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    info["currency"]  = "INR"

    full_text = "\n".join(lines)
    fmt = _detect_format(lines)

    m = _IFSC_PAT.search(full_text)
    if m:
        info["ifsc"] = m.group(1).upper()

    m = _F1_MICR_PAT.search(full_text)
    if m:
        info["micr"] = m.group(1)

    if fmt == "f1":
        m = _F1_ACCT_PAT.search(full_text)
        if m:
            info["account_number"] = m.group(1).strip()
        m = _F1_PERIOD_PAT.search(full_text)
        if m:
            info["statement_period"]["from"] = _fmt_date_dmy_dash(m.group(1))
            info["statement_period"]["to"]   = _fmt_date_dmy_dash(m.group(2))
        for line in lines[:40]:
            s = line.strip()
            if info["account_holder"] is None:
                m2 = _F1_NAME_PAT.match(s)
                if m2:
                    info["account_holder"] = m2.group(1).strip()
            if info["branch"] is None:
                m2 = _F1_BRANCH_PAT.match(s)
                if m2:
                    info["branch"] = m2.group(1).strip()

    else:  # fmt == "f2"
        m = _F2_ACCT_PAT.search(full_text)
        if m:
            info["account_number"] = m.group(1).strip()

        # FIX 5: Nickname field has the full untruncated name on one line
        m = _F2_NICKNAME_PAT.search(full_text)
        if m:
            info["account_holder"] = m.group(1).strip()

        m = _F2_PERIOD_FROM.search(full_text)
        if m:
            info["statement_period"]["from"] = _fmt_date_dmy_slash(m.group(1))
        m = _F2_PERIOD_TO.search(full_text)
        if m:
            info["statement_period"]["to"] = _fmt_date_dmy_slash(m.group(1))

        # FIX 3: Track prev_branch independently so continuation line is appended
        prev_branch = False
        for line in lines[:60]:
            s = line.strip()
            if not s:
                prev_branch = False
                continue

            if info["acc_type"] is None:
                m2 = _F2_TYPE_PAT.match(s)
                if m2:
                    raw = m2.group(1).strip().upper()
                    info["acc_type"] = _TYPE_MAP.get(raw, m2.group(1).strip())
                    prev_branch = False
                    continue

            if info["branch"] is None or prev_branch:
                m2 = _F2_BRANCH_PAT.match(s)
                if m2:
                    info["branch"] = m2.group(1).strip().rstrip("-").strip()
                    prev_branch = True
                    continue
                # FIX 3: append continuation line (e.g. "DONGERKERY")
                elif prev_branch and not re.match(
                    r"^(Type|Currency|Name|Status|Date|Nickname|Number|"
                    r"Drawing|Sanction|Debit|Credit|Primary|Balance)\s*[:\d]",
                    s, re.I
                ) and not re.match(r"^-NIL-$|^INR\s", s, re.I) and not _is_skip(s):
                    info["branch"] = (info["branch"] + " " + s).strip()
                    prev_branch = False
                    continue
                else:
                    prev_branch = False

            if info["currency"] == "INR":
                m2 = _F2_CURRENCY_PAT.match(s)
                if m2:
                    info["currency"] = m2.group(1).strip()

    return info


def extract_account_info_full(pdf_path: str, lines: list[str]) -> dict:
    return extract_account_info(lines, pdf_path=pdf_path)


# =============================================================================
# TRANSACTION EXTRACTION
# =============================================================================
def extract_transactions(pdf_path: str) -> list[dict]:
    with pdfplumber.open(pdf_path) as pdf:
        all_lines = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                all_lines.extend(text.split("\n"))

    fmt = _detect_format(all_lines)
    if fmt == "f1":
        txns = _extract_f1(all_lines)
    else:
        txns = _extract_f2_words(pdf_path)

    for i, txn in enumerate(txns, 1):
        txn["row_id"] = i
    return txns


# =============================================================================
# FORMAT 1 PARSER
# =============================================================================
def _assign_amounts_f1(amounts, last_balance):
    debit = credit = balance = None
    if not amounts:
        return debit, credit, balance
    balance = _parse_amount(amounts[-1])
    if len(amounts) >= 2:
        txn_amt = _parse_amount(amounts[-2])
        if txn_amt is not None and last_balance is not None and balance is not None:
            delta = round(balance - last_balance, 2)
            if delta > 0:
                credit = txn_amt
            elif delta < 0:
                debit = txn_amt
    return debit, credit, balance


def _extract_f1(all_lines: list[str]) -> list[dict]:
    transactions = []
    current      = None
    last_balance = None

    for raw in all_lines:
        line = raw.strip()
        if not line or _is_skip(line):
            continue
        m = _OPENING_BAL_PAT.search(line)
        if m:
            last_balance = _parse_amount(m.group(1))
            continue
        if _F1_AMOUNTS_ONLY.match(line):
            if current is not None and current["balance"] is None:
                amounts = _AMOUNT_PAT.findall(line)
                d, c, b = _assign_amounts_f1(amounts, last_balance)
                current["debit"]   = d
                current["credit"]  = c
                current["balance"] = b
                last_balance = b
            continue
        m = _F1_DATE_PAT.match(line)
        if m:
            if current is not None:
                transactions.append(current)
            date_str  = _fmt_date_dmy_dash(m.group(1))
            remainder = m.group(2).strip()
            amounts   = _AMOUNT_PAT.findall(remainder)
            if amounts:
                d, c, b = _assign_amounts_f1(amounts, last_balance)
                last_balance = b
            else:
                d = c = b = None
            desc_clean = re.sub(r"\s{2,}", " ", _AMOUNT_PAT.sub("", remainder)).strip()
            ref_no = None
            ref_m  = re.search(r"\s+(\d{5,10})\s*$", desc_clean)
            if ref_m:
                ref_no     = ref_m.group(1)
                desc_clean = desc_clean[:ref_m.start()].strip()
            current = {
                "date": date_str, "description": desc_clean,
                "ref_no": ref_no, "debit": d, "credit": c, "balance": b,
            }
        else:
            if current is not None and not _is_skip(line):
                current["description"] = (current["description"] + " " + line).strip()

    if current is not None:
        transactions.append(current)
    transactions.sort(key=_sort_key)
    return transactions


# =============================================================================
# FORMAT 2 — WORD-LEVEL EXTRACTION WITH AUTO-CALIBRATED COLUMN BOUNDARIES
# =============================================================================
def _extract_f2_words(pdf_path: str) -> list[dict]:
    """
    Word-level column-aware extractor for Karnataka Bank F2 format.

    FIXES APPLIED:
      FIX 1: table_start_y reset to 0 (not None) when reusing col_bounds from
             a previous page, preventing TypeError on "if y <= table_start_y".
      FIX 2: strip() before _AMOUNT_CELL_RE.match() to handle leading/trailing
             spaces in cell text returned by get_col().
    """
    transactions = []
    current      = None
    # These persist across pages so continuation pages work
    col_bounds_persistent   = None
    table_start_y_persistent = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_width = page.width

            words = page.extract_words(
                keep_blank_chars=False,
                x_tolerance=3,
                y_tolerance=3,
            )
            if not words:
                continue

            # ---- Group words into 5px y-bands ----
            by_y = defaultdict(list)
            for w in words:
                by_y[round(w["top"] / 5) * 5].append(w)
            sorted_ys = sorted(by_y.keys())

            # ---- Find table header row on this page ----
            col_bounds    = None
            table_start_y = None

            for y in sorted_ys:
                row_words = sorted(by_y[y], key=lambda w: w["x0"])
                row_text  = " ".join(w["text"] for w in row_words)

                if _TABLE_HEADER_RE.search(row_text):
                    continue  # "Transactions List -" label — skip, next row is actual header

                role_x = {}
                for w in row_words:
                    role = _identify_role(w["text"])
                    if role and role not in role_x:
                        role_x[role] = w["x0"]

                if "date" in role_x and "balance" in role_x and len(role_x) >= 3:
                    col_bounds    = _build_col_bounds(role_x, page_width)
                    table_start_y = y
                    # Update persistent state
                    col_bounds_persistent    = col_bounds
                    table_start_y_persistent = y
                    break

            # FIX 1: If no header found on this page, reuse previous page's col_bounds
            # and set table_start_y = 0 so ALL rows are scanned (no skipping).
            if col_bounds is None:
                if col_bounds_persistent is None:
                    continue  # No table seen yet on any page — skip page
                col_bounds    = col_bounds_persistent
                table_start_y = 0   # FIX 1: was None → caused TypeError

            # ---- Helper: extract text for a column role ----
            def get_col(row_words, role):
                if role not in col_bounds:
                    return ""
                x_min, x_max = col_bounds[role]
                return _words_in_col(row_words, x_min, x_max)

            # ---- Walk data rows ----
            for y in sorted_ys:
                if y <= table_start_y:
                    continue

                row_words = sorted(by_y[y], key=lambda w: w["x0"])
                if not row_words:
                    continue

                row_text = " ".join(w["text"] for w in row_words).strip()
                if not row_text or _is_skip(row_text):
                    continue

                # Detect and re-calibrate on repeated column header rows
                role_check = {}
                for w in row_words:
                    r = _identify_role(w["text"])
                    if r:
                        role_check[r] = True
                if "date" in role_check and "balance" in role_check and len(role_check) >= 3:
                    role_x = {}
                    for w in row_words:
                        role = _identify_role(w["text"])
                        if role and role not in role_x:
                            role_x[role] = w["x0"]
                    if len(role_x) >= 3:
                        col_bounds    = _build_col_bounds(role_x, page_width)
                        table_start_y = y
                        col_bounds_persistent    = col_bounds
                        table_start_y_persistent = y
                    continue

                date_text    = get_col(row_words, "date").strip()
                desc_text    = get_col(row_words, "desc").strip()
                cheque_text  = get_col(row_words, "cheque").strip()
                debit_text   = get_col(row_words, "debit").strip()
                credit_text  = get_col(row_words, "credit").strip()
                balance_text = get_col(row_words, "balance").strip()

                # FIX 2: strip before matching amount pattern
                def parse_cell(text):
                    t = text.strip()
                    return _parse_amount(t) if _AMOUNT_CELL_RE.match(t) else None

                # ---- New transaction row ----
                if _is_date_f2(date_text):
                    if current is not None:
                        transactions.append(current)

                    ref_no = cheque_text if (cheque_text and re.match(r"^\d+$", cheque_text)) else None
                    desc   = re.sub(r"\s+", " ", desc_text).strip()

                    current = {
                        "date":        _fmt_date_dmy_slash(date_text),
                        "description": desc,
                        "ref_no":      ref_no,
                        "debit":       parse_cell(debit_text),
                        "credit":      parse_cell(credit_text),
                        "balance":     parse_cell(balance_text),
                    }

                # ---- Continuation row ----
                elif current is not None:
                    extra_parts = []
                    if desc_text:
                        extra_parts.append(desc_text)
                    if cheque_text and not re.match(r"^\d+$", cheque_text):
                        extra_parts.append(cheque_text)
                    extra = " ".join(extra_parts).strip()
                    if extra and not _is_skip(extra):
                        current["description"] = re.sub(
                            r"\s+", " ",
                            current["description"] + " " + extra
                        ).strip()
                    # Fill missing amounts from continuation row
                    if current["balance"] is None:
                        v = parse_cell(balance_text)
                        if v is not None:
                            current["balance"] = v
                    if current["debit"] is None:
                        v = parse_cell(debit_text)
                        if v is not None:
                            current["debit"] = v
                    if current["credit"] is None:
                        v = parse_cell(credit_text)
                        if v is not None:
                            current["credit"] = v

    if current is not None:
        transactions.append(current)

    transactions.sort(key=_sort_key)
    return transactions