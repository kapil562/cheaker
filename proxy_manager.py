import random
import asyncio
from typing import List, Optional, Dict, Any
from collections import defaultdict
import time


class ProxyRotator:
    def __init__(self):
        self.proxies: List[str] = []
        self.current_index = 0
        self.stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"success": 0, "fail": 0, "last_used": 0})
        self._lock = asyncio.Lock()

    def load_proxies(self, proxy_list: List[str]):
        self.proxies = [p.strip() for p in proxy_list if p.strip()]
        self.current_index = 0

    def load_from_string(self, proxy_string: str):
        if not proxy_string:
            return
        lines = [l.strip() for l in proxy_string.replace("\r", "\n").split("\n") if l.strip()]
        self.proxies = lines
        self.current_index = 0

    def get_next(self) -> Optional[str]:
        if not self.proxies:
            return None
        proxy = self.proxies[self.current_index % len(self.proxies)]
        self.current_index += 1
        self.stats[proxy]["last_used"] = time.time()
        return proxy

    def get_random(self) -> Optional[str]:
        if not self.proxies:
            return None
        proxy = random.choice(self.proxies)
        self.stats[proxy]["last_used"] = time.time()
        return proxy

    def get_best(self) -> Optional[str]:
        if not self.proxies:
            return None
        scored = []
        for p in self.proxies:
            s = self.stats[p]
            total = s["success"] + s["fail"]
            if total == 0:
                scored.append((p, 1.0))
            else:
                score = s["success"] / total
                scored.append((p, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]

    def report_success(self, proxy: str):
        self.stats[proxy]["success"] += 1

    def report_fail(self, proxy: str):
        self.stats[proxy]["fail"] += 1

    def remove_bad_proxies(self, threshold: float = 0.3, min_requests: int = 5):
        to_remove = []
        for p in self.proxies:
            s = self.stats[p]
            total = s["success"] + s["fail"]
            if total >= min_requests:
                rate = s["success"] / total
                if rate < threshold:
                    to_remove.append(p)
        for p in to_remove:
            self.proxies.remove(p)
            del self.stats[p]
        return to_remove

    def get_stats(self) -> Dict[str, Any]:
        result = {}
        for p in self.proxies:
            s = self.stats[p]
            total = s["success"] + s["fail"]
            result[p] = {
                "success": s["success"],
                "fail": s["fail"],
                "total": total,
                "rate": round(s["success"] / total * 100, 1) if total > 0 else 0,
                "last_used": s["last_used"],
            }
        return result

    @property
    def count(self) -> int:
        return len(self.proxies)

    @property
    def has_proxies(self) -> bool:
        return len(self.proxies) > 0


proxy_rotator = ProxyRotator()
