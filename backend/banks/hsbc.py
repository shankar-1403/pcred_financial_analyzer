import re
import os
import sys
import subprocess
import tempfile
import glob
import inspect
from datetime import datetime
from PIL import Image
import pytesseract

from .base import default_account_info

BANK_KEY          = "hsbc"
BANK_DISPLAY_NAME = "HSBC Bank"

_OCR_CACHE: dict[str, list[str]] = {}


# =============================================================================
# OCR
# =============================================================================

def _ocr_pdf(pdf_path: str) -> list[str]:
    """Render each PDF page to image and OCR with Tesseract."""
    if pdf_path in _OCR_CACHE:
        return _OCR_CACHE[pdf_path]
    with tempfile.TemporaryDirectory() as tmpdir:
        prefix = os.path.join(tmpdir, "pg")
        subprocess.run(
            ["pdftoppm", "-r", "200", pdf_path, prefix],
            check=True, capture_output=True,
        )
        pages = sorted(glob.glob(f"{prefix}-*.ppm"))
        lines: list[str] = []
        for p in pages:
            img  = Image.open(p)
            text = pytesseract.image_to_string(img, config="--psm 6")
            lines.extend(text.split("\n"))
    _OCR_CACHE[pdf_path] = lines
    return lines


def _is_garbled(lines: list[str]) -> bool:
    """True if lines contain pdfplumber's obfuscated-font garbage bytes."""
    sample = [l for l in lines if l.strip()][:8]
    if not sample:
        return True
    total = sum(len(l) for l in sample)
    if total == 0:
        return True
    non_print = sum(
        1 for l in sample for c in l
        if ord(c) < 32 or (127 <= ord(c) <= 159)
    )
    return (non_print / total) > 0.05


def _get_pdf_path_from_stack() -> str | None:
    try:
        frame = inspect.currentframe()
        while frame is not None:
            local_vars = frame.f_locals
            # Look for a local named pdf_path that ends with .pdf
            for var_name in ("pdf_path", "path", "filepath", "file_path"):
                val = local_vars.get(var_name)
                if isinstance(val, str) and val.lower().endswith(".pdf") and os.path.exists(val):
                    return val
            frame = frame.f_back
    except Exception:
        pass
    return None


# =============================================================================
# REGEX PATTERNS
# =============================================================================

_DATE_ANCHOR  = re.compile(r'^([O0]?\d[A-Z]{3}\d{4}|\d{2}[A-Z]{3}\d{4})\s+(.+)$')
_CLOSE_DEBIT  = re.compile(r'^(\d{4}/\d{2}/\d{2})\s+\w+\s+([\d,]+\.\d{2})\s*[|\s]*\s*([\d, ]+\.\d{2})\s*$')
_CLOSE_CREDIT = re.compile(r'^(IMPS|NEFT|RTGS|UPI|ECS)[/\-](\S+)\s+([\d,]+\.\d{2})\s*[|\s]+\s*([\d, ]+\.\d{2})\s*$', re.IGNORECASE)
_CLOSE_UTR    = re.compile(r'^([A-Z0-9]{10,})\s+([\d,]+\.\d{2})\s*[|\s]+\s*([\d, ]+\.\d{2})\s*$', re.IGNORECASE)
_CLOSE_NUM    = re.compile(r'^(\d{7,})\s+([\d,]+\.\d{2})\s+([\d, ]+\.\d{2})\s*$')
_INWARD       = re.compile(r'\b(NEFT\s+FROM|IMPS\s+FROM|INWARD|CREDITED|CREDIT\s+BY|RECEIVED\s+FROM)\b', re.IGNORECASE)
_TABLE_ON     = re.compile(r'^\(DR=Debit\)$', re.IGNORECASE)
_TABLE_OFF    = re.compile(r'^Balance\s+Carried\s+Forward', re.IGNORECASE)
_BAL_FWD      = re.compile(r'^Balance\s+(Brought|Carried)\s+Forward', re.IGNORECASE)

_SKIP = re.compile(
    r'^(Page\s+\d+\s+of\s+\d+|HSBC\s+Account\s+Statement|The\s+Hongkong|52/60'
    r'|Website|Issued\s+by|Incorporated|Local\s+cheques|Please\s+note|HSN\s+\('
    r'|HSBC\s+State|Maharashtra|Delhi|Rajasthan|Kerala|Gujarat|West\s+Bengal'
    r'|Haryana|Tamil\s+Nadu|Chandigarh|Telangana|Karnataka|Uttar\s+Pradesh'
    r'|Date\s+Details|Statement\s+Details|Despatch\s+Code|\(DR=Debit\)'
    r'|discrepancies|will\s+be\s+deemed|in\s+address\s+should|debited.*cheques'
    r'|balance\s+available|pigase|Withdrawals\s+\d|Deposits\s+\d'
    r'|Invoice\s+No|Ce$|[-~>|<]{1,5}$)',
    re.IGNORECASE,
)

# FIX 1: re.MULTILINE — ^ must anchor to each line, not just string start
# FIX 2: \.?        — OCR adds trailing dot: "MICR CODE: 500039002."
_HOLDER_DATE = re.compile(
    r'^(.+?)\s+Statement\s+Date\s+(\d{2}[A-Z]{3}\d{4})',
    re.IGNORECASE | re.MULTILINE,
)
_ACCT_RE   = re.compile(r'Account\s+Number\s+([\d][\d\-]+)',   re.IGNORECASE)
_CUST_RE   = re.compile(r'Customer\s+Number\s+([\d\-]+)',       re.IGNORECASE)
_IFSC_RE   = re.compile(r'IFSC\s+CODE:\s*(HSBC[A-Z0-9]+)',     re.IGNORECASE)
_MICR_RE   = re.compile(r'MICR\s+CODE:\s*(\d{9})\.?',          re.IGNORECASE)
_BRANCH_RE = re.compile(r'Branch\s+Name:\s*=?\s*(.+)',          re.IGNORECASE)
_PROD_RE   = re.compile(r'Product\s+Type\s+(.+)',               re.IGNORECASE)
_CURR_RE   = re.compile(r'Currency\s+([A-Z]{3})',               re.IGNORECASE)


# =============================================================================
# HELPERS
# =============================================================================

def _clean_amount(s: str) -> float | None:
    if not s:
        return None
    try:
        v = float(s.replace(",", "").replace(" ", "").strip())
        return v if v else None
    except (ValueError, TypeError):
        return None


def _parse_date(s: str) -> str | None:
    s = s.replace("O", "0").replace("o", "0")
    try:
        return datetime.strptime(s, "%d%b%Y").strftime("%d-%m-%Y")
    except ValueError:
        return None


def _should_skip(line: str) -> bool:
    s = line.strip()
    if not s:              return True
    if _BAL_FWD.match(s): return True
    if _SKIP.match(s):     return True
    return False


def _finalise(txn: dict) -> dict:
    cont = txn.pop("_cont", [])
    full = ((txn.get("description") or "") + " " + " ".join(cont)).strip()
    txn["description"] = re.sub(r'\s+', ' ', full) or None
    return txn


def _sort_key(t: dict):
    try:
        return datetime.strptime(t["date"], "%d-%m-%Y")
    except (ValueError, TypeError, KeyError):
        return datetime.max


def _build_account_info(lines: list[str]) -> dict:
    """Build account info dict from clean OCR lines."""
    info = default_account_info()
    info["bank_name"] = BANK_DISPLAY_NAME
    full = "\n".join(lines)

    m = _HOLDER_DATE.search(full)
    if m:
        info["account_holder"]         = m.group(1).strip()
        info["statement_period"]["to"] = _parse_date(m.group(2))

    for pat, key in [
        (_ACCT_RE, "account_number"),
        (_CUST_RE, "customer_id"),
        (_IFSC_RE, "ifsc"),
        (_MICR_RE, "micr"),
    ]:
        m = pat.search(full)
        if m:
            info[key] = m.group(1).strip()

    if info.get("ifsc"):
        info["ifsc"] = info["ifsc"].upper()

    m = _BRANCH_RE.search(full)
    if m:
        info["branch"] = m.group(1).strip().split("MICR")[0].strip()

    m = _PROD_RE.search(full)
    if m:
        info["acc_type"] = m.group(1).strip()

    m = _CURR_RE.search(full)
    info["currency"] = m.group(1).upper() if m else "INR"

    return info


def extract_account_info(lines: list[str]) -> dict:
    if _is_garbled(lines):
        pdf_path = _get_pdf_path_from_stack()
        if pdf_path:
            lines = _ocr_pdf(pdf_path)   # cached — extract_transactions reuses this
        else:
            # Last resort: return minimal info with just bank name
            info = default_account_info()
            info["bank_name"] = BANK_DISPLAY_NAME
            info["currency"]  = "INR"
            return info

    return _build_account_info(lines)


def extract_transactions(pdf_path: str) -> list[dict]:
    """
    Called by __init__.py as: bank_module.extract_transactions(pdf_path)
    OCR result is cached so if extract_account_info already ran OCR it's free.
    """
    lines = _ocr_pdf(pdf_path)   # uses cache if already run
    return _extract_transactions_from_lines(lines)


def extract_account_info_full(pdf_path: str, lines: list[str]) -> dict:
    """Legacy entry point — always uses OCR."""
    return _build_account_info(_ocr_pdf(pdf_path))


# =============================================================================
# TRANSACTION PARSER (internal)
# =============================================================================

def _extract_transactions_from_lines(lines: list[str]) -> list[dict]:
    transactions: list[dict] = []
    current_txn:  dict | None = None
    current_date: str  | None = None
    pending_desc: list[str]   = []
    inside_table: bool        = False

    def flush() -> None:
        nonlocal current_txn
        if current_txn is not None:
            transactions.append(_finalise(current_txn))
            current_txn = None

    def emit(debit=None, credit=None, bal=None, desc="") -> None:
        nonlocal pending_desc
        flush()
        combined = (desc + " " + " ".join(pending_desc)).strip()
        t = {
            "date":        current_date,
            "description": re.sub(r'\s+', ' ', combined) or None,
            "_cont":       [],
            "debit":       debit,
            "credit":      credit,
            "balance":     bal,
        }
        transactions.append(_finalise(t))
        pending_desc = []

    def acc_desc() -> str:
        if current_txn:
            return ((current_txn.get("description") or "")
                    + " " + " ".join(current_txn.get("_cont", [])))
        return " ".join(pending_desc)

    def is_credit(extra: str = "") -> bool:
        return bool(_INWARD.search(acc_desc() + " " + extra))

    for raw in lines:
        line = raw.strip()

        if _TABLE_ON.match(line):
            inside_table = True
            continue

        if _TABLE_OFF.match(line):
            flush()
            inside_table = False
            pending_desc = []
            continue

        if _should_skip(line): continue
        if not inside_table:   continue

        # ── Close: YYYY/MM/DD seqno amt balance ───────────────────────────
        m = _CLOSE_DEBIT.match(line)
        if m:
            amt, bal, cr = _clean_amount(m.group(2)), _clean_amount(m.group(3)), is_credit()
            if current_txn is not None:
                current_txn["credit" if cr else "debit"] = amt
                current_txn["balance"] = bal
                flush(); pending_desc = []
            else:
                emit(credit=amt if cr else None, debit=None if cr else amt, bal=bal)
            continue

        # ── Close: IMPS/ref amt | balance ─────────────────────────────────
        m = _CLOSE_CREDIT.match(line)
        if m:
            amt, bal = _clean_amount(m.group(3)), _clean_amount(m.group(4))
            ref = f"{m.group(1).upper()}/{m.group(2)}"
            if current_txn is not None:
                current_txn["credit"]      = amt
                current_txn["balance"]     = bal
                current_txn["description"] = (ref + " " + (current_txn.get("description") or "")).strip()
                flush(); pending_desc = []
            else:
                emit(credit=amt, bal=bal, desc=ref)
            continue

        # ── Close: UTR amt | balance ───────────────────────────────────────
        m = _CLOSE_UTR.match(line)
        if m:
            amt, bal, cr = (_clean_amount(m.group(2)), _clean_amount(m.group(3)),
                            is_credit(m.group(1)))
            if current_txn is not None:
                current_txn["credit" if cr else "debit"] = amt
                current_txn["balance"] = bal
                flush(); pending_desc = []
            else:
                emit(credit=amt if cr else None, debit=None if cr else amt,
                     bal=bal, desc=m.group(1))
            continue

        # ── Close: numeric-ref amt balance ────────────────────────────────
        m = _CLOSE_NUM.match(line)
        if m:
            amt, bal, cr = _clean_amount(m.group(2)), _clean_amount(m.group(3)), is_credit()
            if current_txn is not None:
                current_txn["credit" if cr else "debit"] = amt
                current_txn["balance"] = bal
                flush(); pending_desc = []
            else:
                emit(credit=amt if cr else None, debit=None if cr else amt, bal=bal)
            continue

        # ── Date anchor: DDMMMYYYY description ────────────────────────────
        ma = _DATE_ANCHOR.match(line)
        if ma:
            parsed = _parse_date(ma.group(1))
            if parsed:
                flush(); pending_desc = []
                current_date = parsed
                current_txn  = {
                    "date": parsed, "description": ma.group(2).strip(),
                    "_cont": [], "debit": None, "credit": None, "balance": None,
                }
                continue

        # ── Continuation / pending description ────────────────────────────
        if current_txn is not None:
            current_txn["_cont"].append(line)
        else:
            pending_desc.append(line)

    flush()
    txns = [t for t in transactions
            if t.get("debit") is not None or t.get("credit") is not None]
    txns.sort(key=_sort_key)
    return txns