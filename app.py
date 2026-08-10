from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio
import json
import time
import logging
from pathlib import Path
from io import BytesIO

from checker import CreditCardChecker
from bin_lookup import lookup_bin, detect_card_network
from database import (
    init_db, create_session, finish_session, save_result,
    get_sessions, get_session, get_session_results, delete_session, get_stats,
    add_proxy, get_proxies, remove_proxy
)
from proxy_manager import proxy_rotator
from card_generator import generate_full_card, generate_batch, NETWORKS
from gateways.stripe import StripeGateway, STRIPE_VERSIONS
from gateways.razorpay import RazorpayGateway
from gateways.adyen import AdyenGateway
from gateways.paypal import PayPalGateway
from gateways.shopify import ShopifyGateway

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import os
IS_SERVERLESS = os.environ.get("VERCEL", "") != ""

if not IS_SERVERLESS:
    for d in ["static/css", "static/js", "templates", "data"]:
        Path(d).mkdir(parents=True, exist_ok=True)

init_db()

if not IS_SERVERLESS:
    try:
        saved_proxies = get_proxies()
        if saved_proxies:
            proxy_rotator.load_proxies(saved_proxies)
    except Exception:
        pass


class MultiGatewayRequest(BaseModel):
    cards: List[str]
    gateway: str = "all"
    amount: float = 1.0
    currency: str = "USD"
    stripe_version: int = 1
    auto_retry: bool = True
    parallel: bool = True
    max_workers: int = 5
    proxy: Optional[str] = None
    shopify_site: Optional[str] = None
    api_key: Optional[str] = None


class ProxyRequest(BaseModel):
    proxies: List[str]


class GenerateRequest(BaseModel):
    count: int = 10
    network: str = "visa"


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

API_KEYS = {
    "admin": {"name": "Admin", "rate_limit": None},
    "user1": {"name": "User 1", "rate_limit": 5},
    "free": {"name": "Free", "rate_limit": 10},
}
_rate_limit_store: Dict[str, list] = {}


def check_rate_limit(api_key: str) -> bool:
    config = API_KEYS.get(api_key)
    if not config:
        return False
    if config["rate_limit"] is None:
        return True
    now = time.time()
    if api_key not in _rate_limit_store:
        _rate_limit_store[api_key] = []
    _rate_limit_store[api_key] = [t for t in _rate_limit_store[api_key] if now - t < 60]
    if len(_rate_limit_store[api_key]) >= config["rate_limit"]:
        return False
    _rate_limit_store[api_key].append(now)
    return True


GATEWAY_TIMEOUT = 20

async def _with_timeout(coro, timeout=GATEWAY_TIMEOUT):
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        return {"status": "error", "success": False, "message": f"Timeout ({timeout}s)", "gateway": "timeout"}
    except Exception as e:
        return {"status": "error", "success": False, "message": str(e), "gateway": "error"}


async def auto_retry_stripe(card_number, exp_month, exp_year, cvv, amount, currency, proxy=None, max_version=10):
    last_result = {"status": "error", "success": False, "message": "All versions failed", "gateway": "stripe"}
    for v in range(1, max_version + 1):
        result = await _with_timeout(
            StripeGateway.process(card_number, exp_month, exp_year, cvv, amount=amount, currency=currency, stripe_version=v, proxy=proxy),
            timeout=GATEWAY_TIMEOUT
        )
        last_result = result
        if result.get("status") not in ("error",):
            result["stripe_version"] = v
            return result
    last_result["stripe_version"] = max_version
    return last_result


class GatewayManager:
    def __init__(self):
        self.gateways = {
            "stripe": {"class": StripeGateway, "name": "Stripe", "display_name": "Stripe", "working": True,
                       "supported_cards": ["visa", "mastercard", "amex", "discover", "jcb"]},
            "razorpay": {"class": RazorpayGateway, "name": "Razorpay", "display_name": "Razorpay", "working": True,
                         "supported_cards": ["visa", "mastercard", "amex", "jcb"]},
            "adyen": {"class": AdyenGateway, "name": "Adyen", "display_name": "Adyen (Picsart)", "working": True,
                      "supported_cards": ["visa", "mastercard"]},
            "paypal": {"class": PayPalGateway, "name": "PayPal", "display_name": "PayPal Commerce", "working": True,
                       "supported_cards": ["visa", "mastercard", "amex", "discover"]},
            "shopify": {"class": ShopifyGateway, "name": "Shopify", "display_name": "Shopify", "working": True,
                        "supported_cards": ["visa", "mastercard", "amex", "discover"]},
        }

    def get_working_gateways(self) -> List[str]:
        return [name for name, info in self.gateways.items() if info.get("working", False)]

    def get_gateway(self, name: str):
        info = self.gateways.get(name.lower())
        if info and info.get("working", False):
            return info["class"]
        return None

    def get_gateway_info(self, name: str):
        return self.gateways.get(name.lower())


gateway_manager = GatewayManager()

app = FastAPI(title="Advanced CC Checker", version="7.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if not IS_SERVERLESS:
    app.mount("/static", StaticFiles(directory="static"), name="static")


BASE_DIR = Path(__file__).parent


@app.get("/", response_class=HTMLResponse)
async def home():
    try:
        with open(BASE_DIR / "templates" / "index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>CC Checker</h1>")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    try:
        await manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)
    except Exception:
        pass


@app.post("/api/check")
async def check_cards(request: MultiGatewayRequest, http_request: Request):
    start_time = time.time()
    checker = CreditCardChecker()
    total_cards = len(request.cards)

    session_id = create_session(
        gateway=request.gateway, parallel=request.parallel,
        amount=request.amount, currency=request.currency
    )

    async def event_stream():
        stats = {"charged": 0, "live": 0, "dead": 0, "ccn": 0, "error": 0}
        total_charged_amount = 0.0
        all_results = []

        async def check_one(idx, card_data):
            try:
                parts = card_data.strip().split("|")
                if len(parts) != 4:
                    return None
                card_number, mm, yy, cvv = [p.strip() for p in parts]
                try:
                    exp_month = int(mm)
                    exp_year = int(yy)
                    if exp_year < 100:
                        exp_year += 2000
                except ValueError:
                    return None

                validation = checker.validate_card(card_number, exp_month, exp_year, cvv)
                bin_info = lookup_bin(card_number)

                if not validation["valid"]:
                    return {
                        "card_number": card_number[:6] + "..." + card_number[-4:],
                        "full_card": card_number, "exp_month": mm, "exp_year": yy, "cvv": cvv,
                        "card_type": validation["card_type"], "card_brand": validation["brand"],
                        "bin_info": bin_info,
                        "results": {}, "best_gateway": "N/A", "best_status": "dead",
                        "charged_count": 0, "live_count": 0, "amount": 0, "errors": validation["errors"]
                    }

                proxy = request.proxy
                if proxy_rotator.has_proxies and not proxy:
                    proxy = proxy_rotator.get_next()

                if request.gateway == "all":
                    gateway_results = {}
                    tasks_list = []
                    for gw_name in gateway_manager.get_working_gateways():
                        gw_class = gateway_manager.get_gateway(gw_name)
                        if not gw_class:
                            continue
                        if gw_name == "shopify" and not request.shopify_site:
                            continue
                        if gw_name == "stripe":
                            task = _with_timeout(gw_class.process(card_number, exp_month, exp_year, cvv, amount=request.amount, currency=request.currency, stripe_version=request.stripe_version, proxy=proxy), timeout=GATEWAY_TIMEOUT)
                        elif gw_name == "razorpay":
                            task = _with_timeout(gw_class.process(card_number, exp_month, exp_year, cvv, amount=request.amount, currency="INR", proxy=proxy), timeout=GATEWAY_TIMEOUT)
                        elif gw_name == "shopify":
                            task = _with_timeout(gw_class.process(card_number, exp_month, exp_year, cvv, amount=request.amount, shopify_site=request.shopify_site, proxy=proxy), timeout=GATEWAY_TIMEOUT)
                        else:
                            task = _with_timeout(gw_class.process(card_number, exp_month, exp_year, cvv, amount=request.amount, proxy=proxy), timeout=GATEWAY_TIMEOUT)
                        tasks_list.append((gw_name, task))

                    if request.parallel and len(tasks_list) > 1:
                        done = await asyncio.gather(*[t for _, t in tasks_list], return_exceptions=True)
                        for i, (gw_name, _) in enumerate(tasks_list):
                            r = done[i] if not isinstance(done[i], Exception) else {"status": "error", "message": str(done[i])}
                            r["gateway"] = gw_name
                            gateway_results[gw_name] = r
                    else:
                        for gw_name, task in tasks_list:
                            try:
                                r = await task
                                r["gateway"] = gw_name
                                gateway_results[gw_name] = r
                            except Exception as e:
                                gateway_results[gw_name] = {"status": "error", "message": str(e), "gateway": gw_name}

                    best_gateway = None
                    best_score = -1
                    status_scores = {"charged": 100, "live": 80, "ccn": 50, "dead": 20, "error": 0}
                    for name, result in gateway_results.items():
                        score = status_scores.get(result.get("status", "error"), 0)
                        if score > best_score:
                            best_score = score
                            best_gateway = name

                    charged_count = sum(1 for r in gateway_results.values() if r.get("status") == "charged")
                    live_count = sum(1 for r in gateway_results.values() if r.get("status") == "live")
                    amount_charged = sum(float(r.get("amount", 0)) for r in gateway_results.values() if r.get("status") == "charged")

                    return {
                        "card_number": card_number[:6] + "..." + card_number[-4:],
                        "full_card": card_number, "exp_month": mm, "exp_year": yy, "cvv": cvv,
                        "card_type": validation["card_type"], "card_brand": validation["brand"],
                        "bin_info": bin_info,
                        "results": gateway_results, "best_gateway": best_gateway,
                        "best_status": gateway_results.get(best_gateway, {}).get("status", "unknown"),
                        "charged_count": charged_count, "live_count": live_count,
                        "amount": amount_charged, "errors": validation["errors"]
                    }
                else:
                    gw_class = gateway_manager.get_gateway(request.gateway)
                    if not gw_class:
                        return {
                            "card_number": card_number[:6] + "..." + card_number[-4:],
                            "full_card": card_number, "exp_month": mm, "exp_year": yy, "cvv": cvv,
                            "card_type": validation["card_type"], "card_brand": validation["brand"],
                            "bin_info": bin_info,
                            "results": {}, "best_gateway": "N/A", "best_status": "error",
                            "charged_count": 0, "live_count": 0, "amount": 0, "errors": ["Gateway not available"]
                        }

                    if request.gateway == "stripe":
                        if request.auto_retry:
                            result = await _with_timeout(auto_retry_stripe(card_number, exp_month, exp_year, cvv, request.amount, request.currency, proxy=proxy), timeout=45)
                        else:
                            result = await _with_timeout(gw_class.process(card_number, exp_month, exp_year, cvv, amount=request.amount, currency=request.currency, stripe_version=request.stripe_version, proxy=proxy), timeout=GATEWAY_TIMEOUT)
                    elif request.gateway == "razorpay":
                        result = await _with_timeout(gw_class.process(card_number, exp_month, exp_year, cvv, amount=request.amount, currency="INR", proxy=proxy), timeout=GATEWAY_TIMEOUT)
                    elif request.gateway == "shopify":
                        result = await _with_timeout(gw_class.process(card_number, exp_month, exp_year, cvv, amount=request.amount, shopify_site=request.shopify_site, proxy=proxy), timeout=GATEWAY_TIMEOUT)
                    else:
                        result = await _with_timeout(gw_class.process(card_number, exp_month, exp_year, cvv, amount=request.amount, proxy=proxy), timeout=GATEWAY_TIMEOUT)

                    gateway_results = {request.gateway: result}
                    amount_charged = float(result.get("amount", 0)) if result.get("status") == "charged" else 0

                    return {
                        "card_number": card_number[:6] + "..." + card_number[-4:],
                        "full_card": card_number, "exp_month": mm, "exp_year": yy, "cvv": cvv,
                        "card_type": validation["card_type"], "card_brand": validation["brand"],
                        "bin_info": bin_info,
                        "results": gateway_results, "best_gateway": request.gateway,
                        "best_status": result.get("status", "unknown"),
                        "charged_count": 1 if result.get("status") == "charged" else 0,
                        "live_count": 1 if result.get("status") == "live" else 0,
                        "amount": amount_charged, "errors": validation["errors"]
                    }
            except Exception as e:
                return {
                    "card_number": "ERROR", "full_card": card_data[:10] if len(card_data) > 10 else card_data,
                    "exp_month": "", "exp_year": "", "cvv": "",
                    "card_type": "unknown", "card_brand": "Unknown",
                    "bin_info": {},
                    "results": {}, "best_gateway": "ERROR", "best_status": "error",
                    "charged_count": 0, "live_count": 0, "amount": 0, "errors": [str(e)]
                }

        if request.parallel and total_cards > 1:
            CARD_TIMEOUT = 45
            MAX_CONCURRENT = min(total_cards, 30) if total_cards > 50 else min(total_cards, 15)
            sem = asyncio.Semaphore(MAX_CONCURRENT)

            async def limited_check(idx, card):
                async with sem:
                    return await _with_timeout(check_one(idx, card), timeout=CARD_TIMEOUT)

            pending = []
            for idx, card in enumerate(request.cards):
                pending.append(asyncio.ensure_future(limited_check(idx, card)))

            done_set = set()
            while len(done_set) < len(pending):
                newly_done = []
                for i, task in enumerate(pending):
                    if i not in done_set and task.done():
                        newly_done.append(i)
                        done_set.add(i)
                        try:
                            r = task.result()
                        except Exception as e:
                            r = {"status": "error", "message": str(e)}
                        if r and isinstance(r, dict):
                            all_results.append(r)
                            save_result(session_id, r)
                            st = r.get("best_status", "error")
                            if st in stats:
                                stats[st] += 1
                            if r.get("charged_count", 0) > 0:
                                total_charged_amount += r.get("amount", 0)
                            yield f"data: {json.dumps(r)}\n\n"
                if not newly_done:
                    await asyncio.sleep(0.05)
        else:
            for idx, card_data in enumerate(request.cards):
                r = await check_one(idx, card_data)
                if r:
                    all_results.append(r)
                    save_result(session_id, r)
                    st = r.get("best_status", "error")
                    if st in stats:
                        stats[st] += 1
                    if r.get("charged_count", 0) > 0:
                        total_charged_amount += r.get("amount", 0)
                    yield f"data: {json.dumps(r)}\n\n"

        app.state.last_results = all_results

        time_taken = round(time.time() - start_time, 2)
        summary = {
            "type": "done",
            "total": len(all_results), "charged": stats["charged"], "live": stats["live"],
            "dead": stats["dead"], "ccn": stats["ccn"], "error": stats["error"],
            "total_charged_amount": round(total_charged_amount, 2),
            "time_taken": time_taken,
            "timestamp": datetime.now().isoformat()
        }

        finish_session(session_id, summary, time_taken)

        yield f"data: {json.dumps(summary)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive"
    })


@app.get("/api/gateways")
async def get_gateways():
    working = gateway_manager.get_working_gateways()
    gateways_info = {}
    for name in working:
        info = gateway_manager.get_gateway_info(name)
        if info:
            gateways_info[name] = {"name": info.get("display_name", name), "supported_cards": info.get("supported_cards", [])}
    return {"gateways": working, "count": len(working), "details": gateways_info}


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "version": "7.0.0", "timestamp": datetime.now().isoformat()}


@app.post("/api/generate")
async def generate_cards_api(req: GenerateRequest):
    count = min(req.count, 500)
    network = req.network if req.network in NETWORKS else "visa"
    cards = []
    for _ in range(count):
        card = generate_full_card(network)
        cards.append(card)
    return {"cards": cards, "count": len(cards), "network": network}


@app.get("/api/history")
async def get_history():
    sessions = get_sessions(limit=50)
    return {"sessions": sessions, "count": len(sessions)}


@app.get("/api/history/{session_id}")
async def get_history_detail(session_id: int):
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    results = get_session_results(session_id)
    return {"session": session, "results": results}


@app.delete("/api/history/{session_id}")
async def delete_history(session_id: int):
    delete_session(session_id)
    return {"status": "deleted"}


@app.get("/api/stats")
async def get_stats_api():
    return get_stats()


@app.get("/api/proxies")
async def get_proxies_api():
    proxies = get_proxies()
    return {"proxies": proxies, "count": len(proxies)}


@app.post("/api/proxies")
async def add_proxies_api(req: ProxyRequest):
    added = 0
    for p in req.proxies:
        p = p.strip()
        if p:
            add_proxy(p)
            added += 1
    return {"added": added}


@app.delete("/api/proxies/{proxy:path}")
async def remove_proxy_api(proxy: str):
    remove_proxy(proxy)
    return {"status": "deleted"}


@app.get("/api/export/csv")
async def export_csv():
    results = getattr(app.state, 'last_results', [])
    if not results:
        raise HTTPException(status_code=400, detail="No results to export")

    rows = []
    for r in results:
        bi = r.get("bin_info", {})
        gw = r.get("results", {})
        rows.append({
            "Card Number": r.get("full_card", ""),
            "Expiry": r.get("exp_month", "") + "/" + r.get("exp_year", ""),
            "CVV": r.get("cvv", ""),
            "Card Type": r.get("card_type", ""),
            "Card Brand": r.get("card_brand", ""),
            "Country": bi.get("country", ""),
            "Bank": bi.get("bank", ""),
            "Network": bi.get("network", ""),
            "Stripe": gw.get("stripe", {}).get("status", ""),
            "Razorpay": gw.get("razorpay", {}).get("status", ""),
            "Adyen": gw.get("adyen", {}).get("status", ""),
            "PayPal": gw.get("paypal", {}).get("status", ""),
            "Shopify": gw.get("shopify", {}).get("status", ""),
            "Best Gateway": r.get("best_gateway", ""),
            "Best Status": r.get("best_status", ""),
            "Amount": r.get("amount", 0),
            "Errors": ", ".join(r.get("errors", [])),
        })

    try:
        import pandas as pd
        df = pd.DataFrame(rows)
    except ImportError:
        output = BytesIO()
        import csv as csv_mod
        writer = csv_mod.DictWriter(output, fieldnames=rows[0].keys() if rows else [])
        writer.writeheader()
        writer.writerows(rows)
        output.seek(0)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return FileResponse(output, media_type="text/csv", filename=f"cc_results_{timestamp}.csv")

    output = BytesIO()
    df.to_csv(output, index=False, encoding='utf-8-sig')
    output.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return FileResponse(output, media_type="text/csv", filename=f"cc_results_{timestamp}.csv")


if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("  ADVANCED CC CHECKER v7.0")
    print("=" * 60)
    print("  Gateways: Stripe (10v), Razorpay, Adyen, PayPal, Shopify")
    print("  Features: BIN Lookup, Dark Mode, History, Charts, Card Gen")
    print("  Export: CSV, JSON, TXT")
    print("=" * 60)
    print("  Open: http://localhost:8000")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000)
