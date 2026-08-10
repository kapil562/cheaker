import json
from typing import Dict, Any
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

_network_data: Dict[str, Any] = {}
_bank_data: Dict[str, Any] = {}


def _load_data():
    global _network_data, _bank_data
    if _network_data:
        return
    try:
        with open(DATA_DIR / "bins.json", "r", encoding="utf-8") as f:
            all_data = json.load(f)
        for key, val in all_data.items():
            if "-" in key and "network" in val:
                parts = key.split("-")
                _network_data[(int(parts[0]), int(parts[1]))] = val
            elif "-" in key and "country" in val:
                parts = key.split("-")
                _bank_data[(int(parts[0]), int(parts[1]))] = val
    except Exception:
        pass


def _get_first_6(card_number: str) -> int:
    clean = card_number.replace(" ", "").replace("-", "")
    return int(clean[:6]) if len(clean) >= 6 else 0


def _get_first_1(card_number: str) -> int:
    clean = card_number.replace(" ", "").replace("-", "")
    return int(clean[:1]) if clean else 0


def detect_card_network(card_number: str) -> str:
    clean = card_number.replace(" ", "").replace("-", "")
    first6 = _get_first_6(card_number)
    first1 = _get_first_1(card_number)

    if first1 == 4:
        return "Visa"
    if first1 == 5 or (first6 and 2221 <= first6 <= 2720):
        return "Mastercard"
    if first1 == 3 and len(clean) >= 2 and int(clean[1]) in (4, 7):
        return "American Express"
    if clean.startswith("6011") or clean.startswith("65") or (len(clean) >= 3 and 644 <= int(clean[:3]) <= 649):
        return "Discover"
    if clean.startswith("35"):
        return "JCB"
    if clean.startswith("62"):
        return "UnionPay"
    if (len(clean) >= 3 and 300 <= int(clean[:3]) <= 305) or clean.startswith("36") or clean.startswith("38"):
        return "Diners Club"
    if clean.startswith("5018") or clean.startswith("5020") or clean.startswith("5038") or clean.startswith("6759") or clean.startswith("676"):
        return "Maestro"
    return "Unknown"


def _find_bank(first6: int) -> Dict[str, Any]:
    for (start, end), info in _bank_data.items():
        if start <= first6 <= end:
            return info
    return {}


def lookup_bin(card_number: str) -> Dict[str, Any]:
    _load_data()
    clean = card_number.replace(" ", "").replace("-", "")
    first6 = _get_first_6(card_number)
    first1 = _get_first_1(card_number)
    network = detect_card_network(card_number)

    result = {
        "card_number": card_number,
        "first_6": str(first6),
        "network": network,
        "country": "Unknown",
        "country_code": "XX",
        "currency": "USD",
        "bank": "Unknown",
        "card_type": "Credit/Debit",
        "brand": network,
        "issuer": "Unknown",
        "is_test": False,
        "risk_level": "low",
        "flags": [],
        "cvv_length": 3,
        "prepaid": False,
    }

    is_test = clean.startswith("4111") or clean.startswith("5555") or clean.startswith("3782") or clean.startswith("601111") or clean.startswith("3530")
    if is_test:
        result["is_test"] = True
        result["flags"].append("TEST_CARD")
        result["risk_level"] = "high"

    cvv_map = {
        "Visa": 3, "Mastercard": 3, "American Express": 4,
        "Discover": 3, "JCB": 3, "Diners Club": 3, "UnionPay": 3, "Maestro": 3
    }
    result["cvv_length"] = cvv_map.get(network, 3)

    issuer_map = {
        "Visa": "Visa International", "Mastercard": "Mastercard Worldwide",
        "American Express": "American Express", "Discover": "Discover Financial Services",
        "JCB": "JCB International", "Diners Club": "Diners Club International",
        "UnionPay": "China UnionPay", "Maestro": "Mastercard Worldwide"
    }
    result["issuer"] = issuer_map.get(network, "Unknown")

    if first6:
        bank_info = _find_bank(first6)
        if bank_info:
            result["country"] = bank_info.get("country", "United States")
            result["country_code"] = bank_info.get("country_code", "US")
            result["currency"] = bank_info.get("currency", "USD")
            result["bank"] = bank_info.get("bank", "Unknown")

    if first1 in (3, 4, 5, 6):
        result["card_type"] = "Credit"
    else:
        result["card_type"] = "Debit"

    return result


def get_country_info(country_code: str) -> Dict[str, Any]:
    return {"country": "Unknown", "flag": country_code, "currency": "USD"}


def get_network_info(network: str) -> Dict[str, Any]:
    info_map = {
        "Visa": {"name": "Visa", "color": "#1A1F71", "logo": "visa", "min_length": 13, "max_length": 19},
        "Mastercard": {"name": "Mastercard", "color": "#EB001B", "logo": "mastercard", "min_length": 16, "max_length": 16},
        "American Express": {"name": "American Express", "color": "#006FCF", "logo": "amex", "min_length": 15, "max_length": 15},
        "Discover": {"name": "Discover", "color": "#FF6000", "logo": "discover", "min_length": 16, "max_length": 16},
        "JCB": {"name": "JCB", "color": "#0B4EA2", "logo": "jcb", "min_length": 15, "max_length": 16},
        "Diners Club": {"name": "Diners Club", "color": "#004080", "logo": "diners", "min_length": 14, "max_length": 14},
        "UnionPay": {"name": "UnionPay", "color": "#D22028", "logo": "unionpay", "min_length": 16, "max_length": 19},
        "Maestro": {"name": "Maestro", "color": "#EB001B", "logo": "maestro", "min_length": 12, "max_length": 19},
    }
    return info_map.get(network, {"name": "Unknown", "color": "#999", "logo": "unknown", "min_length": 13, "max_length": 19})


def batch_lookup(cards: list) -> list:
    results = []
    for card in cards:
        parts = card.strip().split("|")
        if parts:
            results.append(lookup_bin(parts[0]))
    return results
