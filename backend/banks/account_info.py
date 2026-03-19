"""
Shared account info extraction. Used by each bank module's extract_account_info.
"""
import re
from .base import default_account_info, DATE_PATTERN

BANK_PATTERNS = {
    r"indusind\s*bank": "IndusInd Bank",
    r"axis\s*bank": "Axis Bank",
    r"icici\s*bank": "ICICI Bank",
    r"hdfc\s*bank": "HDFC Bank",
    r"state\s*bank\s*of\s*india|sbi\b": "State Bank of India",
    r"kotak\s*mahindra\s*bank": "Kotak Mahindra Bank",
}

ACCOUNT_PATTERNS = [
    r"a\/c\s*no\.?\s*[:\-]?\s*(\d{9,18})",
    r"account\s*no\.?\s*[:\-]?\s*(\d{9,18})",
    r"account\s*number\s*[:\-]?\s*(\d{9,18})",
]

NAME_PATTERNS = [
    r"name\s*[:\-]\s*([A-Za-z0-9\s\.&]+)",
    r"customer\s*name.*[:\-]?\s*([A-Za-z0-9\s\.&]+)",
]

BRANCH_PATTERNS = [
    r"a\/c\s*branch\s*[:\-]\s*([A-Za-z\s,]+)",
    r"branch\s*[:\-]\s*([A-Za-z\s,]+)",
]

ACCOUNT_TYPE_PATTERNS = [
    r"a\/c\s*type\s*[:\-]?\s*([A-Za-z]+)",
    r"scheme\s*[:\-]?\s*([A-Za-z0-9\s\-]+)",
]

JOINT_HOLDER_PATTERN = r"(jt\.?\s*holder|joint\s*holder)\s*:\s*(.*)"
MICR_PATTERN = r"micr\s*(code|no)?\s*[:\-]?\s*(\d{9})"
CUSTOMER_ID_PATTERNS = [
    r"cust\s*id\s*[:\-]?\s*(\d+)",
    r"customer\s*no\s*[:\-]?\s*(\d+)",
]
STATEMENT_REQ_PATTERN = r"statement\s*request.*date\s*[:\-]?\s*(" + DATE_PATTERN + ")"
IFSC_PATTERN = r"[A-Z]{4}0[A-Z0-9]{6}"


def extract_account_info_impl(lines, force_bank_name=None):
    """
    Extract account metadata from text lines.
    If force_bank_name is set, use it when bank is not detected from content.
    """
    info = default_account_info()

    for line in lines:
        lower = (line or "").lower().strip()

        if info["bank_name"] is None:
            for pattern, name in BANK_PATTERNS.items():
                if re.search(pattern, line or "", re.I):
                    info["bank_name"] = name
                    break

        if info["account_holder"] is None:
            for pattern in NAME_PATTERNS:
                m = re.search(pattern, line or "", re.I)
                if m:
                    holder = m.group(1)
                    holder = re.split(r"a\/c\s*branch|branch\s*address", holder, flags=re.I)[0]
                    info["account_holder"] = holder.strip()

        if info["micr"] is None:
            m = re.search(MICR_PATTERN, line or "", re.I)
            if m:
                info["micr"] = m.group(2)

        if info["account_number"] is None:
            for pattern in ACCOUNT_PATTERNS:
                m = re.search(pattern, line or "", re.I)
                if m:
                    info["account_number"] = m.group(1)
                    break

        if info["branch"] is None:
            for pattern in BRANCH_PATTERNS:
                m = re.search(pattern, line or "", re.I)
                if m:
                    branch = m.group(1)
                    branch = re.split(r"branch\s*address|address", branch, flags=re.I)[0]
                    info["branch"] = branch.strip()

        if info["ifsc"] is None:
            m = re.search(IFSC_PATTERN, line or "")
            if m:
                info["ifsc"] = m.group()

        if "currency" in lower and "inr" in lower:
            info["currency"] = "INR"

        if info["acc_type"] is None:
            for pattern in ACCOUNT_TYPE_PATTERNS:
                m = re.search(pattern, line or "", re.I)
                if m:
                    info["acc_type"] = m.group(1).strip()
                    break

        if info["joint_holder"] is None:
            m = re.search(JOINT_HOLDER_PATTERN, line or "", re.I)
            if m:
                value = re.split(
                    r"cust\s*id|scheme|branch\s*code|ifsc|a\/c\s*type",
                    m.group(2).strip(),
                    flags=re.I,
                )[0].strip()
                info["joint_holder"] = value or None

        if info["customer_id"] is None:
            for pattern in CUSTOMER_ID_PATTERNS:
                m = re.search(pattern, line or "", re.I)
                if m:
                    info["customer_id"] = m.group(1)
                    break

        if info["statement_request_date"] is None:
            m = re.search(STATEMENT_REQ_PATTERN, line or "", re.I)
            if m:
                info["statement_request_date"] = m.group(1)

        if "transaction period" in lower or ("from" in lower and "to" in lower):
            dates = re.findall(DATE_PATTERN, line or "")
            if len(dates) >= 2:
                info["statement_period"]["from"] = dates[0]
                info["statement_period"]["to"] = dates[1]

    if force_bank_name and info["bank_name"] is None:
        info["bank_name"] = force_bank_name
    return info
