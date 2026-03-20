from ocr_engine import extract_text_from_pdf

from .bank_detector import detect_bank

# Map bank_key -> module with extract_account_info(lines) and extract_transactions(pdf_path)
_BANK_MODULES = {}


def _get_bank_module(bank_key: str):
    if not _BANK_MODULES:
        from . import icici, sbi, axis_neo, axis, hdfc, kotak, indusind, au, boi, bob, generic
        _BANK_MODULES["axis neo"] = axis_neo
        _BANK_MODULES["axis"] = axis
        _BANK_MODULES["icici"] = icici
        _BANK_MODULES["sbi"] = sbi
        _BANK_MODULES["hdfc"] = hdfc
        _BANK_MODULES["kotak"] = kotak
        _BANK_MODULES["indusind"] = indusind
        _BANK_MODULES["au bank"] = au
        _BANK_MODULES["boi"] = boi
        _BANK_MODULES["bob"] = bob
        _BANK_MODULES["generic"] = generic
    return _BANK_MODULES.get(bank_key) or _BANK_MODULES["generic"]


def parse_bank_statement(pdf_path: str):
    lines = extract_text_from_pdf(pdf_path)
    bank_key = detect_bank(pdf_path, lines)
    bank_module = _get_bank_module(bank_key)
    account_info = bank_module.extract_account_info(lines)
    transactions = bank_module.extract_transactions(pdf_path)
    return {
        "account": account_info,
        "transactions": transactions,
    }
