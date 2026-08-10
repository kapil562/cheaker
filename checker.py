import re
import random
from datetime import datetime
from typing import Dict, Optional, Tuple

class CreditCardChecker:
    """Advanced credit card validation"""
    
    @staticmethod
    def luhn_check(card_number: str) -> bool:
        """Validate using Luhn algorithm"""
        card_number = re.sub(r'[\s-]', '', card_number)
        if not card_number.isdigit():
            return False
        
        digits = [int(d) for d in card_number]
        digits.reverse()
        
        total = 0
        for i, d in enumerate(digits):
            if i % 2 == 1:
                d *= 2
                if d > 9:
                    d -= 9
            total += d
        
        return total % 10 == 0

    @staticmethod
    def detect_card_type(card_number: str) -> str:
        """Detect card type"""
        card_number = re.sub(r'[\s-]', '', card_number)
        
        patterns = {
            "visa": r"^4[0-9]{12}(?:[0-9]{3})?$",
            "mastercard": r"^(5[1-5][0-9]{14}|2(2[2-9]|[3-6][0-9])[0-9]{12})$",
            "amex": r"^3[47][0-9]{13}$",
            "discover": r"^6(?:011|5[0-9]{2})[0-9]{12}$",
            "diners": r"^3(?:0[0-5]|[68][0-9])[0-9]{11}$",
            "jcb": r"^(?:2131|1800|35\d{3})\d{11}$",
            "unionpay": r"^62[0-9]{14,17}$",
            "maestro": r"^(5[06789]|6)[0-9]{11,18}$"
        }
        
        for card_type, pattern in patterns.items():
            if re.match(pattern, card_number):
                return card_type
        
        return "unknown"

    @staticmethod
    def get_card_brand(card_number: str) -> str:
        """Get display brand name"""
        card_type = CreditCardChecker.detect_card_type(card_number)
        brand_map = {
            "visa": "Visa",
            "mastercard": "Mastercard",
            "amex": "American Express",
            "discover": "Discover",
            "diners": "Diners Club",
            "jcb": "JCB",
            "unionpay": "UnionPay",
            "maestro": "Maestro"
        }
        return brand_map.get(card_type, "Unknown")

    @staticmethod
    def validate_card(card_number: str, exp_month: int, exp_year: int, cvv) -> Dict:
        """Complete card validation"""
        card_number = re.sub(r'[\s-]', '', str(card_number))
        cvv = str(cvv)
        
        results = {
            "valid": False,
            "card_type": "unknown",
            "brand": "Unknown",
            "luhn_valid": False,
            "expiry_valid": False,
            "cvv_valid": False,
            "errors": []
        }
        
        # Check Luhn
        if CreditCardChecker.luhn_check(card_number):
            results["luhn_valid"] = True
        else:
            results["errors"].append("Invalid card number")
        
        # Check expiry
        if exp_year < 100:
            exp_year += 2000
        
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        if not (1 <= exp_month <= 12):
            results["errors"].append("Invalid expiry month")
        elif exp_year > current_year or (exp_year == current_year and exp_month >= current_month):
            results["expiry_valid"] = True
        else:
            results["errors"].append("Card expired")
        
        # Check CVV
        if len(cvv) in [3, 4] and cvv.isdigit():
            results["cvv_valid"] = True
        else:
            results["errors"].append("Invalid CVV format")
        
        # Get card type
        results["card_type"] = CreditCardChecker.detect_card_type(card_number)
        results["brand"] = CreditCardChecker.get_card_brand(card_number)
        
        results["valid"] = all([
            results["luhn_valid"],
            results["expiry_valid"],
            results["cvv_valid"]
        ])
        
        return results