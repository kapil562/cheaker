import random
import hashlib
from typing import List, Dict, Any


CARD_PREFIXES = {
    "visa": {
        "prefixes": ["4"],
        "lengths": [16],
        "cvv_length": 3,
        "brand": "Visa",
    },
    "mastercard": {
        "prefixes": ["51", "52", "53", "54", "55", "2221", "2222", "2223", "2224", "2225", "2226", "2227", "2228", "2229", "223", "224", "225", "226", "227", "228", "229", "23", "24", "25", "26", "27"],
        "lengths": [16],
        "cvv_length": 3,
        "brand": "Mastercard",
    },
    "amex": {
        "prefixes": ["34", "37"],
        "lengths": [15],
        "cvv_length": 4,
        "brand": "American Express",
    },
    "discover": {
        "prefixes": ["6011", "644", "645", "646", "647", "648", "649", "65"],
        "lengths": [16],
        "cvv_length": 3,
        "brand": "Discover",
    },
    "jcb": {
        "prefixes": ["3528", "3529", "353", "354", "355", "356", "357", "358"],
        "lengths": [16],
        "cvv_length": 3,
        "brand": "JCB",
    },
    "diners": {
        "prefixes": ["300", "301", "302", "303", "304", "305", "36", "38"],
        "lengths": [14],
        "cvv_length": 3,
        "brand": "Diners Club",
    },
    "unionpay": {
        "prefixes": ["62"],
        "lengths": [16],
        "cvv_length": 3,
        "brand": "UnionPay",
    },
    "maestro": {
        "prefixes": ["5018", "5020", "5038", "5612", "5893", "6304", "6759", "6761", "6762", "6763"],
        "lengths": [16],
        "cvv_length": 3,
        "brand": "Maestro",
    },
}


def _luhn_checksum(card_number: str) -> int:
    digits = [int(d) for d in card_number]
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    total = sum(odd_digits)
    for d in even_digits:
        total += sum(divmod(d * 2, 10))
    return (10 - (total % 10)) % 10


def generate_card_number(network: str = "visa") -> str:
    config = CARD_PREFIXES.get(network.lower())
    if not config:
        config = CARD_PREFIXES["visa"]

    prefix = random.choice(config["prefixes"])
    length = random.choice(config["lengths"])

    remaining = length - len(prefix) - 1
    body = "".join([str(random.randint(0, 9)) for _ in range(remaining)])
    partial = prefix + body
    check_digit = _luhn_checksum(partial + "0")
    return partial + str(check_digit)


def generate_expiry() -> Dict[str, str]:
    month = random.randint(1, 12)
    year = random.randint(25, 30)
    return {"month": str(month).zfill(2), "year": str(year)}


def generate_cvv(network: str = "visa") -> str:
    config = CARD_PREFIXES.get(network.lower())
    if not config:
        config = CARD_PREFIXES["visa"]
    length = config["cvv_length"]
    return "".join([str(random.randint(0, 9)) for _ in range(length)])


def generate_full_card(network: str = "visa") -> Dict[str, str]:
    card_number = generate_card_number(network)
    expiry = generate_expiry()
    cvv = generate_cvv(network)
    return {
        "card": f"{card_number}|{expiry['month']}|{expiry['year']}|{cvv}",
        "card_number": card_number,
        "exp_month": expiry["month"],
        "exp_year": expiry["year"],
        "cvv": cvv,
        "network": network,
        "brand": CARD_PREFIXES.get(network.lower(), CARD_PREFIXES["visa"])["brand"],
    }


def generate_batch(count: int, network: str = "visa", unique: bool = True) -> List[str]:
    cards = set() if unique else []
    max_attempts = count * 3
    attempts = 0
    while len(cards) < count and attempts < max_attempts:
        card = generate_full_card(network)
        if unique:
            if card["card"] not in cards:
                cards.add(card["card"])
        else:
            cards.append(card["card"])
        attempts += 1
    return list(cards) if unique else cards


def validate_luhn(card_number: str) -> bool:
    clean = card_number.replace(" ", "").replace("-", "")
    if not clean.isdigit():
        return False
    if len(clean) < 13 or len(clean) > 19:
        return False
    return _luhn_checksum(clean[:-1]) == int(clean[-1])


def detect_network_from_prefix(card_number: str) -> str:
    clean = card_number.replace(" ", "").replace("-", "")
    for network, config in CARD_PREFIXES.items():
        for prefix in config["prefixes"]:
            if clean.startswith(prefix):
                return network
    return "unknown"


NETWORKS = list(CARD_PREFIXES.keys())
