import sqlite3
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
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
            started_at TEXT NOT NULL,
            finished_at TEXT,
            total_cards INTEGER DEFAULT 0,
            charged INTEGER DEFAULT 0,
            live INTEGER DEFAULT 0,
            dead INTEGER DEFAULT 0,
            ccn INTEGER DEFAULT 0,
            error INTEGER DEFAULT 0,
            total_charged_amount REAL DEFAULT 0.0,
            time_taken REAL DEFAULT 0.0,
            gateway TEXT DEFAULT 'all',
            parallel INTEGER DEFAULT 1,
            amount REAL DEFAULT 1.0,
            currency TEXT DEFAULT 'USD',
            status TEXT DEFAULT 'running'
        );

        CREATE TABLE IF NOT EXISTS check_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            card_number TEXT NOT NULL,
            full_card TEXT NOT NULL,
            exp_month TEXT,
            exp_year TEXT,
            cvv TEXT,
            card_type TEXT,
            card_brand TEXT,
            bin_country TEXT,
            bin_bank TEXT,
            bin_network TEXT,
            best_gateway TEXT,
            best_status TEXT,
            charged_count INTEGER DEFAULT 0,
            live_count INTEGER DEFAULT 0,
            amount REAL DEFAULT 0.0,
            stripe_status TEXT,
            razorpay_status TEXT,
            adyen_status TEXT,
            paypal_status TEXT,
            shopify_status TEXT,
            gateway_results TEXT,
            errors TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES check_sessions(id)
        );

        CREATE TABLE IF NOT EXISTS proxy_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proxy TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            last_used TEXT,
            fail_count INTEGER DEFAULT 0,
            success_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_results_session ON check_results(session_id);
        CREATE INDEX IF NOT EXISTS idx_results_status ON check_results(best_status);
        CREATE INDEX IF NOT EXISTS idx_results_card ON check_results(card_number);
        CREATE INDEX IF NOT EXISTS idx_sessions_date ON check_sessions(started_at);
    """)
    conn.commit()


def create_session(gateway: str = "all", parallel: bool = True, amount: float = 1.0, currency: str = "USD") -> int:
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO check_sessions (started_at, gateway, parallel, amount, currency, status)
           VALUES (?, ?, ?, ?, ?, 'running')""",
        (datetime.now().isoformat(), gateway, 1 if parallel else 0, amount, currency)
    )
    conn.commit()
    return cursor.lastrowid


def finish_session(session_id: int, stats: Dict[str, Any], time_taken: float = 0.0):
    conn = get_connection()
    conn.execute(
        """UPDATE check_sessions SET
           finished_at=?, total_cards=?, charged=?, live=?, dead=?, ccn=?, error=?,
           total_charged_amount=?, time_taken=?, status='completed'
           WHERE id=?""",
        (
            datetime.now().isoformat(),
            stats.get("total", 0),
            stats.get("charged", 0),
            stats.get("live", 0),
            stats.get("dead", 0),
            stats.get("ccn", 0),
            stats.get("error", 0),
            stats.get("total_charged_amount", 0.0),
            time_taken,
            session_id,
        ),
    )
    conn.commit()


def save_result(session_id: int, result: Dict[str, Any]):
    conn = get_connection()
    gw_results = result.get("results", {})
    errors = result.get("errors", [])

    conn.execute(
        """INSERT INTO check_results
           (session_id, card_number, full_card, exp_month, exp_year, cvv, card_type, card_brand,
            bin_country, bin_bank, bin_network, best_gateway, best_status, charged_count, live_count,
            amount, stripe_status, razorpay_status, adyen_status, paypal_status, shopify_status,
            gateway_results, errors, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            result.get("card_number", ""),
            result.get("full_card", ""),
            result.get("exp_month", ""),
            result.get("exp_year", ""),
            result.get("cvv", ""),
            result.get("card_type", ""),
            result.get("card_brand", ""),
            result.get("bin_info", {}).get("country", ""),
            result.get("bin_info", {}).get("bank", ""),
            result.get("bin_info", {}).get("network", ""),
            result.get("best_gateway", ""),
            result.get("best_status", ""),
            result.get("charged_count", 0),
            result.get("live_count", 0),
            result.get("amount", 0.0),
            gw_results.get("stripe", {}).get("status", ""),
            gw_results.get("razorpay", {}).get("status", ""),
            gw_results.get("adyen", {}).get("status", ""),
            gw_results.get("paypal", {}).get("status", ""),
            gw_results.get("shopify", {}).get("status", ""),
            json.dumps(gw_results),
            json.dumps(errors),
            datetime.now().isoformat(),
        ),
    )
    conn.commit()


def get_sessions(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM check_sessions ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    return [dict(r) for r in rows]


def get_session(session_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM check_sessions WHERE id=?", (session_id,)).fetchone()
    return dict(row) if row else None


def get_session_results(session_id: int) -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM check_results WHERE session_id=? ORDER BY id", (session_id,)
    ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        if d.get("gateway_results"):
            try:
                d["gateway_results"] = json.loads(d["gateway_results"])
            except:
                d["gateway_results"] = {}
        if d.get("errors"):
            try:
                d["errors"] = json.loads(d["errors"])
            except:
                d["errors"] = []
        results.append(d)
    return results


def delete_session(session_id: int):
    conn = get_connection()
    conn.execute("DELETE FROM check_results WHERE session_id=?", (session_id,))
    conn.execute("DELETE FROM check_sessions WHERE id=?", (session_id,))
    conn.commit()


def get_stats() -> Dict[str, Any]:
    conn = get_connection()
    total_sessions = conn.execute("SELECT COUNT(*) FROM check_sessions").fetchone()[0]
    total_cards = conn.execute("SELECT COALESCE(SUM(total_cards), 0) FROM check_sessions").fetchone()[0]
    total_charged = conn.execute("SELECT COALESCE(SUM(charged), 0) FROM check_sessions").fetchone()[0]
    total_live = conn.execute("SELECT COALESCE(SUM(live), 0) FROM check_sessions").fetchone()[0]
    total_dead = conn.execute("SELECT COALESCE(SUM(dead), 0) FROM check_sessions").fetchone()[0]
    total_amount = conn.execute("SELECT COALESCE(SUM(total_charged_amount), 0) FROM check_sessions").fetchone()[0]

    recent = conn.execute(
        "SELECT started_at, charged, live, dead, ccn, total_cards, gateway FROM check_sessions ORDER BY id DESC LIMIT 10"
    ).fetchall()

    top_gateways = conn.execute(
        "SELECT best_gateway, COUNT(*) as cnt FROM check_results WHERE best_status='charged' GROUP BY best_gateway ORDER BY cnt DESC LIMIT 5"
    ).fetchall()

    return {
        "total_sessions": total_sessions,
        "total_cards_checked": total_cards,
        "total_charged": total_charged,
        "total_live": total_live,
        "total_dead": total_dead,
        "total_charged_amount": total_amount,
        "recent_sessions": [dict(r) for r in recent],
        "top_gateways": [dict(r) for r in top_gateways],
    }


def add_proxy(proxy: str):
    conn = get_connection()
    conn.execute(
        "INSERT INTO proxy_list (proxy, created_at) VALUES (?, ?)",
        (proxy, datetime.now().isoformat()),
    )
    conn.commit()


def get_proxies(status: str = "active") -> List[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT proxy FROM proxy_list WHERE status=? ORDER BY success_count DESC", (status,)
    ).fetchall()
    return [r["proxy"] for r in rows]


def update_proxy_stats(proxy: str, success: bool):
    conn = get_connection()
    if success:
        conn.execute(
            "UPDATE proxy_list SET success_count=success_count+1, last_used=? WHERE proxy=?",
            (datetime.now().isoformat(), proxy),
        )
    else:
        conn.execute(
            "UPDATE proxy_list SET fail_count=fail_count+1 WHERE proxy=?", (proxy,)
        )
    conn.commit()


def remove_proxy(proxy: str):
    conn = get_connection()
    conn.execute("DELETE FROM proxy_list WHERE proxy=?", (proxy,))
    conn.commit()
