"""Đo CVD thật × đường giá × nến → data/results.json.

Lợi suất luôn là VƯỢT TRỘI so với trung bình rổ cùng thời điểm (cùng ngày + cùng mốc 15'), để 7 phiên chung một
nhịp thị trường không làm giả kết quả. Mọi phép đo có hướng định sẵn (want = +1 kỳ vọng tăng, −1 kỳ vọng giảm).

Cổng (giống order-flow-lab): đúng chiều + vượt mức giả (500 lần thay mã ngẫu nhiên cùng ngày/mốc, ngưỡng 97,5 %)
+ > 1 bước giá + ≥ 70 % ngày cùng dấu + hai nửa mã (chẵn/lẻ theo thứ tự chữ cái) cùng dấu.

Chạy: ../order-flow-live/venv/Scripts/python measure.py
"""
from __future__ import annotations

import argparse
import json
import random
import statistics as st
from pathlib import Path

HERE = Path(__file__).resolve().parent
BARS, OUT = HERE / "data" / "bars.json", HERE / "data" / "results.json"
MIN_VAL = 5.0          # tỷ/phiên, trung vị
LOOK = 8               # số nến 15' nhìn lại để xác định đáy/đỉnh (2 giờ)
N_FAKE = 500
SLOTS = [m for m in range(9 * 60 + 15, 11 * 60 + 30, 15)] + [m for m in range(13 * 60, 14 * 60 + 30, 15)]
RNG = random.Random(20261008)


def tick_size(p: float, ex: str) -> float:
    if ex != "HOSE":
        return 0.1
    return 0.01 if p < 10 else 0.05 if p < 50 else 0.1


def load(uni_mode: str = "liquid"):
    """uni_mode: "liquid" = mã ≥ 5 tỷ/phiên (mặc định), "kingstock" = 39 mã danh mục (không lọc thanh khoản)."""
    raw = json.loads(BARS.read_text(encoding="utf-8"))
    days = sorted({d for v in raw.values() for d in v["days"]})
    ok = lambda v: len(v["days"]) >= 6 and not any(x["no_side"] for x in v["days"].values())
    if uni_mode == "kingstock":
        import hidden
        uni = sorted(s for s in hidden.watchlist() if s in raw and ok(raw[s]))
    else:
        uni = sorted(s for s, v in raw.items() if ok(v) and st.median(x["val"] for x in v["days"].values()) >= MIN_VAL)
    return raw, days, uni


def add_hidden(raw, days, uni):
    """Cộng cá mập ẩn (hidden.py) vào bb/bs của nến 5' và của ngày → CVD cá mập = cá mập tổng hợp của app.
    Trả {(mã, ngày): giá trị ròng chuỗi thuật toán (tỷ)} cho phép đo D."""
    import hidden
    h = hidden.load(days)
    chain = {}
    for (s, d), r in h.items():
        rec = raw.get(s, {}).get("days", {}).get(d)
        if s not in uni or not rec:
            continue
        chain[(s, d)] = r["chain_val"]
        b5 = rec["b5"]
        mins = [b[0] for b in b5]
        for minute, sh in r["adj"]:
            k = minute // 5 * 5
            i = max(0, max((j for j, m in enumerate(mins) if m <= k), default=0))
            col = 7 if sh > 0 else 8
            b5[i][col] += abs(sh)
            rec["bb" if sh > 0 else "bs"] += abs(sh)
    return chain


def bars15(rec: dict) -> dict[int, dict]:
    """Nến 5' → nến 15' theo mốc SLOTS; nến trống (không khớp) không có mặt."""
    out: dict[int, dict] = {}
    for m, o, h, l, c, buy, sell, bb, bs, x in rec["b5"]:
        k = m // 15 * 15
        if k < SLOTS[0]:
            k = SLOTS[0]          # 09:00–09:14 khớp liên tục hiếm, gộp vào nến đầu
        b = out.get(k)
        if b is None:
            out[k] = {"o": o, "h": h, "l": l, "c": c, "buy": buy, "sell": sell, "bb": bb, "bs": bs}
        else:
            b["h"], b["l"], b["c"] = max(b["h"], h), min(b["l"], l), c
            for key, v in (("buy", buy), ("sell", sell), ("bb", bb), ("bs", bs)):
                b[key] += v
    return out


class Market:
    """Giá theo (mã, ngày, mốc) với mốc = phút của nến 15' hoặc 'C' (đóng cửa ngày, có ATC)."""

    def __init__(self, raw, days, uni):
        self.days, self.uni, self.raw = days, uni, raw
        self.px: dict[tuple, float] = {}
        self.b15: dict[tuple, dict] = {}
        for s in uni:
            for d, rec in raw[s]["days"].items():
                b = bars15(rec)
                self.b15[(s, d)] = b
                last = None
                for m in SLOTS:       # giá đóng tại mốc, kéo theo giá gần nhất nếu nến trống
                    if m in b:
                        last = b[m]["c"]
                    if last is not None:
                        self.px[(s, d, m)] = last
                self.px[(s, d, "C")] = rec["c"]
        self.bad = self._bad_days()
        self._base: dict[tuple, float] = {}

    def _bad_days(self) -> set:
        """Ngày có bước nhảy vượt biên độ (chia cổ tức/thưởng) → bỏ mã-ngày đó và ngày trước."""
        bad = set()
        for s in self.uni:
            ex = self.raw[s]["ex"]
            lim = {"HOSE": 0.075, "HNX": 0.105}.get(ex, 0.155)
            for i in range(1, len(self.days)):
                a, b = self.px.get((s, self.days[i - 1], "C")), self.px.get((s, self.days[i], "C"))
                if a and b and abs(b / a - 1) > lim:
                    bad.add((s, self.days[i])); bad.add((s, self.days[i - 1]))
        return bad

    def ret(self, s, d, m, k):
        """Lợi suất từ giá (d, m) tới đóng cửa ngày d+k (k=0: hết phiên)."""
        i = self.days.index(d)
        if i + k >= len(self.days):
            return None
        d2 = self.days[i + k]
        if (s, d) in self.bad or (s, d2) in self.bad:
            return None
        a, b = self.px.get((s, d, m)), self.px.get((s, d2, "C"))
        return None if not a or not b else b / a - 1

    def base(self, d, m, k):
        key = (d, m, k)
        if key not in self._base:
            rs = [r for s in self.uni if (r := self.ret(s, d, m, k)) is not None]
            self._base[key] = st.mean(rs) if rs else None
        return self._base[key]

    def excess(self, s, d, m, k):
        r, b = self.ret(s, d, m, k), self.base(d, m, k)
        return None if r is None or b is None else r - b


# ------------------------------------------------------------------ tín hiệu
def intraday_events(mk: Market):
    """Quét nến 15' từng mã-ngày → {tên: [(mã, ngày, mốc)]}; mỗi loại chỉ lấy LẦN ĐẦU mỗi mã-ngày (chống đếm trùng)."""
    ev: dict[str, list] = {k: [] for k in (
        "A1", "A2", "A3", "A4", "B1", "B2", "B3", "B4")}
    for s in mk.uni:
        for d in mk.days:
            b = mk.b15.get((s, d))
            if not b:
                continue
            seen = set()
            ks = [m for m in SLOTS if m in b]
            cvd = cvw = 0
            hist = []          # (l, h, cvd, cvw, vol) của các nến trước
            for m in ks:
                x = b[m]
                vol = x["buy"] + x["sell"]
                cvd += x["buy"] - x["sell"]
                cvw += x["bb"] - x["bs"]
                if len(hist) >= LOOK and vol > 0 and m < SLOTS[-1]:
                    prev = hist[-LOOK:]
                    lo, hi = min(p[0] for p in prev), max(p[1] for p in prev)
                    vavg = st.mean(p[4] for p in prev) or 1
                    rng = x["h"] - x["l"]
                    clv = (x["c"] - x["l"]) / rng if rng > 0 else 0.5
                    dr = (x["buy"] - x["sell"]) / vol
                    at_low, at_high = x["l"] <= lo, x["h"] >= hi
                    heavy = vol >= 1.5 * vavg
                    cand = {
                        # A: nến × delta tại đáy/đỉnh 2 giờ, KL ≥ 1,5× TB 8 nến
                        "A1": at_low and heavy and x["c"] > x["o"] and dr >= 0.2,          # cầu xác nhận → tăng
                        "A2": at_low and heavy and dr <= -0.3 and clv >= 0.5,              # hấp thụ bán → tăng
                        "A3": at_high and heavy and dr >= 0.3 and clv <= 0.5,              # hấp thụ mua → giảm
                        "A4": at_high and heavy and x["c"] < x["o"] and dr <= -0.2,        # cung xác nhận → giảm
                        # B: phân kỳ giá–CVD (tổng / cá mập)
                        "B1": at_low and cvd > min(p[2] for p in prev),                    # đáy giá mới, CVD không → tăng
                        "B2": at_high and cvd < max(p[2] for p in prev),                   # đỉnh giá mới, CVD không → giảm
                        "B3": at_low and cvw > min(p[3] for p in prev) and cvw > 0,        # cá mập gom khi giá thủng đáy
                        "B4": at_high and cvw < max(p[3] for p in prev) and cvw < 0,       # cá mập xả khi giá vượt đỉnh
                    }
                    for k, ok in cand.items():
                        if ok and k not in seen:
                            seen.add(k)
                            ev[k].append((s, d, m))
                hist.append((x["l"], x["h"], cvd, cvw, vol))
    return ev


def daily_events(mk: Market, chain=None):
    """Tín hiệu cuối phiên (mốc 'C'); chống đếm trùng: mỗi mã cách nhau ≥ 3 phiên."""
    ev: dict[str, list] = {k: [] for k in ("C1", "C2", "C3", "C4", "C5", "C6", "D1", "D2")}
    last: dict[tuple, int] = {}
    for s in mk.uni:
        recs = mk.raw[s]["days"]
        for i, d in enumerate(mk.days):
            r = recs.get(d)
            if not r or (s, d) in mk.bad:
                continue
            vol = r["buy"] + r["sell"]
            if vol <= 0:
                continue
            dr = (r["buy"] - r["sell"]) / vol
            body, rng = abs(r["c"] - r["o"]), r["h"] - r["l"]
            lower = min(r["o"], r["c"]) - r["l"]
            prev = [recs.get(x) for x in mk.days[max(0, i - 3):i]]
            prev = [p for p in prev if p]
            cand = {
                "C1": r["c"] < r["o"] and dr >= 0.15,                                     # nến đỏ mà mua ròng → tăng
                "C2": r["c"] > r["o"] and dr <= -0.15,                                    # nến xanh mà bán ròng → giảm
                "C3": rng > 0 and lower >= 2 * max(body, 1e-9) and (r["c"] - r["l"]) / rng >= 0.6
                      and r["bb"] > r["bs"],                                              # rút chân + cá mập mua → tăng
            }
            if len(prev) == 3:
                win = prev + [r]
                v3 = sum(p["buy"] + p["sell"] for p in win[1:]) or 1
                w3 = sum(p["bb"] - p["bs"] for p in win[1:]) / v3       # CVD cá mập 3 phiên % KL CĐ
                c3 = sum(p["buy"] - p["sell"] for p in win[1:]) / v3
                p3 = r["c"] / prev[0]["c"] - 1                          # % giá 3 phiên
                cand["C4"] = r["c"] < min(p["l"] for p in prev) and c3 > 0                # phá đáy 3 phiên, CVD 3p dương → tăng
                cand["C5"] = w3 >= 0.10 and p3 < 0                                        # cá mập gom, giá giảm → tăng
                cand["C6"] = w3 <= -0.10 and p3 > 0                                       # cá mập xả, giá tăng → giảm
            if chain is not None:
                cv_ = chain.get((s, d), 0.0)
                cand["D1"] = cv_ >= 1.0                                                   # chuỗi thuật toán mua ròng ≥ 1 tỷ → tăng
                cand["D2"] = cv_ <= -1.0                                                  # bán ròng ≥ 1 tỷ → giảm
            for k, ok in cand.items():
                if ok and i - last.get((s, k), -99) >= 3:
                    last[(s, k)] = i
                    ev[k].append((s, d, "C"))
    return ev


# ------------------------------------------------------------------ đo & cổng
def evaluate(mk: Market, name: str, events: list, want: int, k: int, tick_bps: float) -> dict:
    rows = [(s, d, m, e) for s, d, m in events if (e := mk.excess(s, d, m, k)) is not None]
    res = {"name": name, "k": k, "want": want, "n": len(rows)}
    if len(rows) < 20:
        res.update(pass_=False, note="ít mẫu (< 20)")
        return res
    mean = st.mean(r[3] for r in rows) * 1e4
    hit = sum(1 for r in rows if r[3] * want > 0) / len(rows)
    # mức giả: thay mã bằng mã ngẫu nhiên có giá cùng ngày/mốc
    pool: dict[tuple, list] = {}
    fakes = []
    for _ in range(N_FAKE):
        acc = []
        for s, d, m, _e in rows:
            key = (d, m)
            if key not in pool:
                pool[key] = [x for u in mk.uni if (x := mk.excess(u, d, m, k)) is not None]
            acc.append(RNG.choice(pool[key]))
        fakes.append(st.mean(acc) * 1e4 * want)
    fakes.sort()
    fake975 = fakes[int(0.975 * N_FAKE)]
    by_day: dict[str, list] = {}
    for s, d, m, e in rows:
        by_day.setdefault(d, []).append(e)
    day_means = {d: st.mean(v) * 1e4 for d, v in by_day.items()}
    same = sum(1 for v in day_means.values() if v * want > 0)
    idx = {s: i for i, s in enumerate(mk.uni)}
    halves = [st.mean([r[3] for r in rows if idx[r[0]] % 2 == h] or [0]) * 1e4 for h in (0, 1)]
    checks = {
        "đúng chiều": mean * want > 0,
        "vượt mức giả": mean * want > fake975,
        "> 1 bước giá": mean * want > tick_bps,
        "≥ 70 % ngày cùng dấu": same >= 0.7 * len(day_means),
        "hai nửa cùng dấu": all(h * want > 0 for h in halves),
    }
    res.update(mean_bps=round(mean, 1), hit=round(hit, 3), fake975=round(fake975, 1),
               days_same=f"{same}/{len(day_means)}", day_means={d: round(v, 1) for d, v in day_means.items()},
               halves=[round(h, 1) for h in halves], checks=checks, pass_=all(checks.values()))
    return res


def rank_ic(mk: Market, k: int) -> dict:
    """IC hạng theo ngày: delta/KL cả phiên → lợi suất vượt trội tới đóng cửa d+k."""
    ics = {}
    for d in mk.days:
        xs = []
        for s in mk.uni:
            r = mk.raw[s]["days"].get(d)
            e = mk.excess(s, d, "C", k)
            if r and e is not None and (r["buy"] + r["sell"]) > 0:
                xs.append(((r["buy"] - r["sell"]) / (r["buy"] + r["sell"]), e))
        if len(xs) >= 30:
            ics[d] = round(spearman([a for a, _ in xs], [b for _, b in xs]), 3)
    return {"name": f"IC delta/KL ngày → T+{k}", "k": k, "by_day": ics,
            "mean": round(st.mean(ics.values()), 3) if ics else None,
            "pos": sum(1 for v in ics.values() if v > 0), "n_days": len(ics)}


def spearman(a, b):
    def rk(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        for pos, i in enumerate(order):
            r[i] = pos
        return r
    ra, rb = rk(a), rk(b)
    return st.correlation(ra, rb)


TESTS = {
    "A1": ("Đáy 2 giờ · nến xanh KL lớn · delta ≥ +20 % (cầu xác nhận)", +1),
    "A2": ("Đáy 2 giờ · KL lớn · delta ≤ −30 % mà đóng nửa trên (hấp thụ bán)", +1),
    "A3": ("Đỉnh 2 giờ · KL lớn · delta ≥ +30 % mà đóng nửa dưới (hấp thụ mua)", -1),
    "A4": ("Đỉnh 2 giờ · nến đỏ KL lớn · delta ≤ −20 % (cung xác nhận)", -1),
    "B1": ("Phân kỳ đáy: giá thủng đáy 2 giờ, CVD không thủng", +1),
    "B2": ("Phân kỳ đỉnh: giá vượt đỉnh 2 giờ, CVD không vượt", -1),
    "B3": ("Giá thủng đáy 2 giờ, CVD cá mập dương và không thủng", +1),
    "B4": ("Giá vượt đỉnh 2 giờ, CVD cá mập âm và không vượt", -1),
    "C1": ("Nến ngày đỏ nhưng delta ≥ +15 % KL", +1),
    "C2": ("Nến ngày xanh nhưng delta ≤ −15 % KL", -1),
    "C3": ("Nến rút chân + cá mập mua ròng", +1),
    "C4": ("Đóng dưới đáy 3 phiên, CVD 3 phiên dương", +1),
    "C5": ("CVD cá mập 3 phiên ≥ +10 % KL, giá 3 phiên giảm", +1),
    "C6": ("CVD cá mập 3 phiên ≤ −10 % KL, giá 3 phiên tăng", -1),
    "D1": ("Chuỗi thuật toán (cá mập ẩn) mua ròng ≥ 1 tỷ trong phiên", +1),
    "D2": ("Chuỗi thuật toán (cá mập ẩn) bán ròng ≥ 1 tỷ trong phiên", -1),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uni", choices=("liquid", "kingstock"), default="liquid")
    ap.add_argument("--whale", choices=("big", "comb"), default="big",
                    help="big = lệnh ≥ 500 tr; comb = + cá mập ẩn (chỉ có cho 39 mã KingStock)")
    a = ap.parse_args()
    raw, days, uni = load(a.uni)
    chain = add_hidden(raw, days, uni) if a.whale == "comb" else None
    out = OUT if (a.uni, a.whale) == ("liquid", "big") else OUT.with_name(f"results-{a.uni}-{a.whale}.json")
    mk = Market(raw, days, uni)
    tb = st.median(tick_size(raw[s]["days"][days[-1]]["c"], raw[s]["ex"]) / raw[s]["days"][days[-1]]["c"] * 1e4
                   for s in uni if days[-1] in raw[s]["days"])
    print(f"{len(uni)} mã, {len(days)} phiên, bước giá trung vị {tb:.1f} bps, bỏ {len(mk.bad)} mã-ngày nhảy giá")
    ev = {**intraday_events(mk), **daily_events(mk, chain)}
    # giả dược: sự kiện ngẫu nhiên cùng số lượng → kỳ vọng KHÔNG qua cổng
    plc = [(RNG.choice(uni), RNG.choice(days), RNG.choice(SLOTS)) for _ in range(400)]
    results = []
    for key, (name, want) in TESTS.items():
        if key[0] == "D" and chain is None:
            continue
        horizons = (0, 1, 2) if key[0] in "AB" else (1, 2)
        for k in horizons:
            r = evaluate(mk, name, ev[key], want, k, tb)
            r["id"] = key
            results.append(r)
            print(f"{key} T+{k} n={r['n']:4d} mean={r.get('mean_bps', '-'):>7} fake={r.get('fake975', '-'):>6} "
                  f"hit={r.get('hit', '-')} ngày={r.get('days_same', '-')} {'QUA' if r['pass_'] else 'trượt'}")
    placebo = [evaluate(mk, "Giả dược: mã/ngày/mốc ngẫu nhiên", plc, w, k, tb) for w in (1, -1) for k in (0, 1)]
    for p in placebo:
        print("giả dược", p["want"], "T+", p["k"], p.get("mean_bps"), "QUA" if p["pass_"] else "trượt")
    ics = [rank_ic(mk, k) for k in (1, 2)]
    for i in ics:
        print(i["name"], i["mean"], f"{i['pos']}/{i['n_days']} ngày dương")
    out.write_text(json.dumps({"uni": a.uni, "whale": a.whale, "n_sym": len(uni), "days": days, "tick_bps": round(tb, 1), "results": results,
                               "placebo": placebo, "ic": ics, "events": {k: v for k, v in ev.items()}},
                              ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
