"""Cá mập ẩn (tab Cá mập ẩn của price-path) → phần cộng thêm vào CVD cá mập, theo cổ phiếu có dấu.

Định nghĩa đúng `price-path/zone/algo.py` day_view: comb = lệnh ≥ 500 tr + lệnh con chuỗi thuật toán (< 500 tr,
phần ≥ 500 tr đã nằm trong lệnh lớn) − chân rổ ≥ 500 tr (rổ là giao dịch chỉ số, không riêng mã).
"""
from __future__ import annotations

import bisect
import json
from pathlib import Path

ALGO = Path(__file__).resolve().parent / "data" / "algo"
WHALE_VND = 500_000_000
SG = {"B": 1, "S": -1}


def watchlist() -> list[str]:
    w = json.loads((ALGO / "watchlist.json").read_text(encoding="utf-8"))
    return sorted({(it.get("symbol") or it.get("code") or it.get("sym")).upper() for it in w["items"]})


def load(days: list[str]) -> dict[tuple[str, str], dict]:
    """{(mã, ngày): {"adj": [(phút, cp có dấu)], "val": tỷ có dấu, "algo_val": tỷ chuỗi, "app": số app}}."""
    out = {}
    for d in days:
        p = ALGO / f"{d}.json"
        if not p.exists():
            continue
        for s in json.loads(p.read_text(encoding="utf-8"))["stocks"]:
            c5 = s.get("c5") or []
            secs = [c[0] for c in c5]

            def price_at(t):
                i = max(0, bisect.bisect_right(secs, t) - 1)
                return c5[i][4] if c5 else s["close"]

            # chân rổ (giây, phía); lệnh con chuỗi trùng chân rổ là robot chạy rổ chỉ số → app trừ (w = 1)
            bk = {(t, side) for t, side, _ in s.get("bkt", [])}
            adj, val, algo_val, chain_val = [], 0.0, 0.0, 0.0
            for ch in s["chains"]:
                for t, px in zip(ch["t"], ch["p"]):
                    v = ch["size"] * px * 1000
                    algo_val += SG[ch["side"]] * v
                    if (t, ch["side"]) not in bk:
                        chain_val += SG[ch["side"]] * v
                    if v < WHALE_VND and (t, ch["side"]) not in bk:
                        adj.append((t // 60, SG[ch["side"]] * ch["size"]))
                        val += SG[ch["side"]] * v
            for t, side, tr in s.get("bkt", []):
                if tr * 1e6 >= WHALE_VND:   # chân rổ là lệnh lớn → bỏ khỏi cá mập lộ diện
                    px = price_at(t)
                    adj.append((t // 60, -SG[side] * round(tr * 1e6 / (px * 1000))))
                    val -= SG[side] * tr * 1e6
            out[(s["sym"], d)] = {"adj": adj, "val": val / 1e9, "algo_val": algo_val / 1e9, "chain_val": chain_val / 1e9,
                                  "app": {k: s[k] for k in ("whale", "algo", "bk", "comb")}}
    return out


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    days = sorted(p.stem[len("ticks-"):] for p in (ALGO.parent / "raw").glob("ticks-*.tar"))
    h = load(days)
    print(len(watchlist()), "mã;", len(h), "mã-phiên")
    worst = 0
    for (s, d), r in sorted(h.items()):
        a = r["app"]
        want = a["comb"] - a["whale"]
        diff = abs(r["val"] - want)
        worst = max(worst, diff)
        if s in ("SSI", "TCB", "GMD", "VPB") or diff > 0.05:
            print(s, d, "lab ẩn", round(r["val"], 2), "app comb−whale", round(want, 2),
                  "| chuỗi", round(r["algo_val"], 2), "app", a["algo"])
    print("lệch lớn nhất (tỷ):", round(worst, 3))
