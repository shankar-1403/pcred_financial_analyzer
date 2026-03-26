from ocr_engine import extract_text_from_pdf

from .bank_detector import detect_bank

# Map bank_key -> module with extract_account_info(lines) and extract_transactions(pdf_path)
_BANK_MODULES = {}


def _get_bank_module(bank_key: str):
    if not _BANK_MODULES:
        from . import icici, sbi, axis_neo, axis, hdfc, kotak, indusind, au, boi, bob, csb, kokan, canara, federal, indian, saraswat, standard_chartered, cosmos, bom, bandhan, yes_bank, union_bank, cbi, generic
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
        _BANK_MODULES["csb"] = csb
        _BANK_MODULES["kokan"] = kokan
        _BANK_MODULES["canara"] = canara
        _BANK_MODULES["federal"] = federal
        _BANK_MODULES["indian"] = indian
        _BANK_MODULES["saraswat"] = saraswat
        _BANK_MODULES["standard_chartered"] = standard_chartered
        _BANK_MODULES["cosmos"] = cosmos
        _BANK_MODULES["bom"] = bom
        _BANK_MODULES["bandhan"] = bandhan
        _BANK_MODULES["yes_bank"] = yes_bank
        _BANK_MODULES["union_bank"] = union_bank
        _BANK_MODULES["cbi"] = cbi
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
