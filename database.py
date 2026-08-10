import json
from datetime import datetime
from typing import List, Dict, Any, Optional
import os

IS_SERVERLESS = os.environ.get("VERCEL", "") != ""

_sessions: Dict[int, Dict] = {}
_results: Dict[int, List[Dict]] = []
_session_counter = 0


if not IS_SERVERLESS:
    import sqlite3
    from pathlib import Path
    import threading

    DB_PATH = Path(__file__).parent / "data" / "checker.db"
    _local = threading.local()

    def get_connection() -> sqlite3.Connection:
        if not hasattr(_local, "conn") or _local.conn is None:
            _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
            _local.conn.row_factory = sqlite3.Row
            _local.conn.execute("PRAGMA journal_mode=WAL")
            _local.conn.execute("PRAGMA synchronous=NORMAL")
        return _local.conn

    def init_db():
        conn = get_connection()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS check_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL, finished_at TEXT,
                total_cards INTEGER DEFAULT 0, charged INTEGER DEFAULT 0,
                live INTEGER DEFAULT 0, dead INTEGER DEFAULT 0,
                ccn INTEGER DEFAULT 0, error INTEGER DEFAULT 0,
                total_charged_amount REAL DEFAULT 0.0, time_taken REAL DEFAULT 0.0,
                gateway TEXT DEFAULT 'all', parallel INTEGER DEFAULT 1,
                amount REAL DEFAULT 1.0, currency TEXT DEFAULT 'USD',
                status TEXT DEFAULT 'running'
            );
            CREATE TABLE IF NOT EXISTS check_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL, card_number TEXT NOT NULL,
                full_card TEXT NOT NULL, exp_month TEXT, exp_year TEXT,
                cvv TEXT, card_type TEXT, card_brand TEXT,
                bin_country TEXT, bin_bank TEXT, bin_network TEXT,
                best_gateway TEXT, best_status TEXT,
                charged_count INTEGER DEFAULT 0, live_count INTEGER DEFAULT 0,
                amount REAL DEFAULT 0.0,
                gateway_results TEXT, errors TEXT, created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES check_sessions(id)
            );
            CREATE TABLE IF NOT EXISTS proxy_list (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proxy TEXT NOT NULL, status TEXT DEFAULT 'active',
                last_used TEXT, fail_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0, created_at TEXT NOT NULL
            );
        """)
        conn.commit()

    def create_session(gateway="all", parallel=True, amount=1.0, currency="USD"):
        conn = get_connection()
        cursor = conn.execute(
            "INSERT INTO check_sessions (started_at, gateway, parallel, amount, currency, status) VALUES (?, ?, ?, ?, ?, 'running')",
            (datetime.now().isoformat(), gateway, 1 if parallel else 0, amount, currency)
        )
        conn.commit()
        return cursor.lastrowid

    def finish_session(session_id, stats, time_taken=0.0):
        conn = get_connection()
        conn.execute(
            "UPDATE check_sessions SET finished_at=?, total_cards=?, charged=?, live=?, dead=?, ccn=?, error=?, total_charged_amount=?, time_taken=?, status='completed' WHERE id=?",
            (datetime.now().isoformat(), stats.get("total", 0), stats.get("charged", 0),
             stats.get("live", 0), stats.get("dead", 0), stats.get("ccn", 0),
             stats.get("error", 0), stats.get("total_charged_amount", 0.0), time_taken, session_id)
        )
        conn.commit()

    def save_result(session_id, result):
        conn = get_connection()
        gw = result.get("results", {})
        errs = result.get("errors", [])
        conn.execute(
            "INSERT INTO check_results (session_id, card_number, full_card, exp_month, exp_year, cvv, card_type, card_brand, bin_country, bin_bank, bin_network, best_gateway, best_status, charged_count, live_count, amount, gateway_results, errors, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, result.get("card_number", ""), result.get("full_card", ""),
             result.get("exp_month", ""), result.get("exp_year", ""), result.get("cvv", ""),
             result.get("card_type", ""), result.get("card_brand", ""),
             result.get("bin_info", {}).get("country", ""),
             result.get("bin_info", {}).get("bank", ""),
             result.get("bin_info", {}).get("network", ""),
             result.get("best_gateway", ""), result.get("best_status", ""),
             result.get("charged_count", 0), result.get("live_count", 0),
             result.get("amount", 0.0), json.dumps(gw), json.dumps(errs),
             datetime.now().isoformat())
        )
        conn.commit()

    def get_sessions(limit=50, offset=0):
        conn = get_connection()
        rows = conn.execute("SELECT * FROM check_sessions ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        return [dict(r) for r in rows]

    def get_session(session_id):
        conn = get_connection()
        row = conn.execute("SELECT * FROM check_sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row) if row else None

    def get_session_results(session_id):
        conn = get_connection()
        rows = conn.execute("SELECT * FROM check_results WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            if d.get("gateway_results"):
                try: d["gateway_results"] = json.loads(d["gateway_results"])
                except: d["gateway_results"] = {}
            if d.get("errors"):
                try: d["errors"] = json.loads(d["errors"])
                except: d["errors"] = []
            results.append(d)
        return results

    def delete_session(session_id):
        conn = get_connection()
        conn.execute("DELETE FROM check_results WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM check_sessions WHERE id=?", (session_id,))
        conn.commit()

    def get_stats():
        conn = get_connection()
        ts = conn.execute("SELECT COUNT(*) FROM check_sessions").fetchone()[0]
        tc = conn.execute("SELECT COALESCE(SUM(total_cards), 0) FROM check_sessions").fetchone()[0]
        tch = conn.execute("SELECT COALESCE(SUM(charged), 0) FROM check_sessions").fetchone()[0]
        tl = conn.execute("SELECT COALESCE(SUM(live), 0) FROM check_sessions").fetchone()[0]
        td = conn.execute("SELECT COALESCE(SUM(dead), 0) FROM check_sessions").fetchone()[0]
        ta = conn.execute("SELECT COALESCE(SUM(total_charged_amount), 0) FROM check_sessions").fetchone()[0]
        recent = conn.execute("SELECT started_at, charged, live, dead, ccn, total_cards, gateway FROM check_sessions ORDER BY id DESC LIMIT 10").fetchall()
        return {
            "total_sessions": ts, "total_cards_checked": tc,
            "total_charged": tch, "total_live": tl, "total_dead": td,
            "total_charged_amount": ta,
            "recent_sessions": [dict(r) for r in recent], "top_gateways": [],
        }

    def add_proxy(proxy):
        conn = get_connection()
        conn.execute("INSERT INTO proxy_list (proxy, created_at) VALUES (?, ?)", (proxy, datetime.now().isoformat()))
        conn.commit()

    def get_proxies(status="active"):
        conn = get_connection()
        rows = conn.execute("SELECT proxy FROM proxy_list WHERE status=? ORDER BY success_count DESC", (status,)).fetchall()
        return [r["proxy"] for r in rows]

    def remove_proxy(proxy):
        conn = get_connection()
        conn.execute("DELETE FROM proxy_list WHERE proxy=?", (proxy,))
        conn.commit()

else:
    def init_db():
        pass

    def create_session(gateway="all", parallel=True, amount=1.0, currency="USD"):
        global _session_counter
        _session_counter += 1
        sid = _session_counter
        _sessions[sid] = {
            "id": sid, "started_at": datetime.now().isoformat(), "finished_at": None,
            "total_cards": 0, "charged": 0, "live": 0, "dead": 0, "ccn": 0, "error": 0,
            "total_charged_amount": 0.0, "time_taken": 0.0,
            "gateway": gateway, "parallel": 1 if parallel else 0,
            "amount": amount, "currency": currency, "status": "running"
        }
        _results[sid] = []
        return sid

    def finish_session(session_id, stats, time_taken=0.0):
        if session_id in _sessions:
            s = _sessions[session_id]
            s["finished_at"] = datetime.now().isoformat()
            s["total_cards"] = stats.get("total", 0)
            s["charged"] = stats.get("charged", 0)
            s["live"] = stats.get("live", 0)
            s["dead"] = stats.get("dead", 0)
            s["ccn"] = stats.get("ccn", 0)
            s["error"] = stats.get("error", 0)
            s["total_charged_amount"] = stats.get("total_charged_amount", 0.0)
            s["time_taken"] = time_taken
            s["status"] = "completed"

    def save_result(session_id, result):
        if session_id in _results:
            _results[session_id].append(result)

    def get_sessions(limit=50, offset=0):
        items = sorted(_sessions.values(), key=lambda x: x["id"], reverse=True)
        return items[offset:offset+limit]

    def get_session(session_id):
        return _sessions.get(session_id)

    def get_session_results(session_id):
        return _results.get(session_id, [])

    def delete_session(session_id):
        _sessions.pop(session_id, None)
        _results.pop(session_id, None)

    def get_stats():
        items = list(_sessions.values())
        return {
            "total_sessions": len(items),
            "total_cards_checked": sum(s.get("total_cards", 0) for s in items),
            "total_charged": sum(s.get("charged", 0) for s in items),
            "total_live": sum(s.get("live", 0) for s in items),
            "total_dead": sum(s.get("dead", 0) for s in items),
            "total_charged_amount": sum(s.get("total_charged_amount", 0) for s in items),
            "recent_sessions": sorted(items, key=lambda x: x["id"], reverse=True)[:10],
            "top_gateways": [],
        }

    def add_proxy(proxy):
        _proxies.append({"proxy": proxy, "created_at": datetime.now().isoformat()})

    def get_proxies(status="active"):
        return [p["proxy"] for p in _proxies]

    def remove_proxy(proxy):
        global _proxies
        _proxies = [p for p in _proxies if p["proxy"] != proxy]

    _proxies = []
