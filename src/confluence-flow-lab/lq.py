"""Nhãn "LQ" trên nến ngày — chép đúng luật của c:\\Claude code\\sweep-lab (sweep.py + b4.py, 19/10/2026), không import lab đó.

LQ MUA (xanh)
  L1  sau giảm (C[t−1] ≤ 0,95 × đỉnh đóng cửa 20 phiên trước), L[t] thủng một đáy swing còn sống (fractal 2 nến, ≤ 120 phiên),
      C[t] ≥ mức thấp nhất bị thủng, O[t] ≤ mức + 0,25 ATR, nến xanh đóng ở ≥ 70 % biên độ, KL ≥ 1 × TB20.
  L2  L1 + mức là đáy 60 phiên (± 0,3 ATR) hoặc có ≥ 2 đáy bằng nhau.
  L3  L1 + phiên t+1 KL < TB20 và đóng cửa ≥ L[t] + 2/3 × (H[t] − L[t]).
LQ BÁN (đỏ)
  B1  sau tăng (C[t−1] ≥ 1,10 × đáy đóng cửa 20 phiên trước), H[t] vượt đỉnh swing còn sống hoặc đỉnh phiên trước, với ít nhất
      một mức bị vượt O[t] ≥ mức − 0,25 ATR, đóng ở ≤ 40 % biên độ, nến đỏ hoặc râu trên ≥ 50 % biên độ, KL ≥ 1 × TB20.
  B2  B1 + mức cao nhất bị vượt là đỉnh 60 phiên hoặc có ≥ 2 đỉnh bằng nhau.
  B3  B1 + phiên t+1 đóng cửa ≤ L[t] + 1/3 × (H[t] − L[t]).
  B4  (Δ) B1 + bán chủ động ≥ 1,5 × mua trong phiên + CVD trong phiên đạt đỉnh trong ± 6 nến 5' quanh nến giá cao nhất
      và CVD cuối phiên thấp hơn đỉnh đó (nến tick của cvd-candle-lab; thiếu dữ liệu → không có Δ).
Cùng mã, cùng luật cách nhau < 5 phiên chỉ giữ lần đầu. Chưa qua cổng thống kê của Sweep Lab (L3 tốt nhất +1,38 %/10p).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LEVEL_LIFE = 120
EXT_WIN = 60
EQ_TOL = 0.3
DEDUP = 5
B4_WIN = 6


def swings(h: np.ndarray, l: np.ndarray, low: bool) -> list[int]:
    out = []
    for i in range(2, len(l) - 2):
        if low:
            if l[i] < min(l[i - 1], l[i - 2]) and l[i] <= min(l[i + 1], l[i + 2]):
                out.append(i)
        elif h[i] > max(h[i - 1], h[i - 2]) and h[i] >= max(h[i + 1], h[i + 2]):
            out.append(i)
    return out


def low_sweeps(h, l, c, a) -> list[dict]:
    """Phiên thủng đáy swing còn sống và đóng cửa ≥ mức thấp nhất bị thủng."""
    n = len(c)
    known: dict[int, list[int]] = {}
    for i in swings(h, l, True):
        known.setdefault(i + 2, []).append(i)
    alive, hist, out = [], [], []
    for t in range(n):
        alive = [(i, p) for i, p in alive if t - i <= LEVEL_LIFE]
        if t >= 1 and a[t] > 1e-9:
            swept = [(i, p) for i, p in alive if l[t] < p]
            if swept:
                lev = min(p for _, p in swept)
                if c[t] >= lev:
                    tol = EQ_TOL * a[t]
                    lo60 = l[max(0, t - EXT_WIN):t].min()
                    eq = sum(1 for j, p in hist if t - j <= LEVEL_LIFE and abs(p - lev) <= tol)
                    out.append({"t": t, "lev": float(lev), "ext": bool(lev <= lo60 + tol or eq >= 2)})
                alive = [(i, p) for i, p in alive if l[t] >= p]
        for i in known.get(t, []):
            alive.append((i, l[i]))
            hist.append((i, l[i]))
    return out


def high_sweeps(h, l, a) -> list[dict]:
    """Phiên vượt đỉnh swing còn sống hoặc đỉnh phiên trước."""
    n = len(h)
    known: dict[int, list[int]] = {}
    for i in swings(h, l, False):
        known.setdefault(i + 2, []).append(i)
    alive, hist, out = [], [], []
    for t in range(n):
        alive = [(i, p) for i, p in alive if t - i <= LEVEL_LIFE]
        if t >= 1 and a[t] > 1e-9:
            levs = [p for _, p in alive if h[t] > p] + ([h[t - 1]] if h[t] > h[t - 1] else [])
            if levs:
                top = max(levs)
                tol = EQ_TOL * a[t]
                hi60 = h[max(0, t - EXT_WIN):t].max()
                eq = sum(1 for j, p in hist if t - j <= LEVEL_LIFE and abs(p - top) <= tol)
                out.append({"t": t, "levs": levs, "lev": float(top), "ext": bool(top >= hi60 - tol or eq >= 2)})
            alive = [(i, p) for i, p in alive if h[t] <= p]
        for i in known.get(t, []):
            alive.append((i, h[i]))
            hist.append((i, h[i]))
    return out


def b4_ok(day: dict | None) -> dict | None:
    """Δ: bán ≥ 1,5 × mua + CVD đỉnh quanh nến giá cao nhất rồi giảm. day = bars.json[mã]["days"][ngày]."""
    if not day or day.get("no_side") or not day.get("b5"):
        return None
    b5 = day["b5"]                         # [phút, o, h, l, c, mua, bán, bb, bs, x]
    buy, sell = sum(b[5] for b in b5), sum(b[6] for b in b5)
    cvd, run = [], 0
    for b in b5:
        run += b[5] - b[6]
        cvd.append(run)
    pk = max(range(len(cvd)), key=lambda i: cvd[i])
    hi = max(range(len(b5)), key=lambda i: b5[i][2])
    ok = sell >= 1.5 * max(buy, 1) and abs(pk - hi) <= B4_WIN and cvd[-1] < cvd[pk]
    return {"ok": bool(ok), "sx": round(sell / max(buy, 1), 2)}


def lq_marks(df: pd.DataFrame, b5_days: dict) -> list[dict]:
    """df = M.base_frame (o, h, l, c, v, atr, vr, d). b5_days = {ngày: bars.json day}. Trả mọi nhãn (đã chống đếm trùng)."""
    o, h, l, c, a, vr = (df[k].to_numpy(float) for k in ("o", "h", "l", "c", "atr", "vr"))
    n = len(c)
    dates = [str(x.date()) for x in df["d"]]
    cs = pd.Series(c).shift(1)
    cmax20, cmin20 = cs.rolling(20).max().to_numpy(), cs.rolling(20).min().to_numpy()
    out: dict[str, list[dict]] = {k: [] for k in ("L1", "L2", "L3", "B1", "B2", "B3")}

    def pos(t):
        rg = h[t] - l[t]
        return (c[t] - l[t]) / rg if rg > 0 else None

    for e in low_sweeps(h, l, c, a):
        t = e["t"]
        p = pos(t)
        if (t >= 21 and c[t - 1] <= 0.95 * cmax20[t] and c[t] > o[t] and p is not None and p >= 0.7 and vr[t] >= 1.0
                and o[t] <= e["lev"] + 0.25 * a[t]):
            base = {"t": t, "lev": round(e["lev"], 2), "pos": round(p, 2), "vr": round(float(vr[t]), 2)}
            out["L1"].append({**base, "s": t})
            if e["ext"]:
                out["L2"].append({**base, "s": t})
            if t + 1 < n and vr[t + 1] < 1.0 and c[t + 1] >= l[t] + 2 / 3 * (h[t] - l[t]):
                out["L3"].append({**base, "s": t + 1, "lvl": round(l[t] + 2 / 3 * (h[t] - l[t]), 2)})
    for e in high_sweeps(h, l, a):
        t = e["t"]
        p = pos(t)
        rg = h[t] - l[t]
        if (t >= 21 and c[t - 1] >= 1.10 * cmin20[t] and p is not None and p <= 0.4 and vr[t] >= 1.0
                and (c[t] < o[t] or (h[t] - max(o[t], c[t])) / rg >= 0.5)
                and any(o[t] >= q - 0.25 * a[t] for q in e["levs"])):
            base = {"t": t, "lev": round(e["lev"], 2), "pos": round(p, 2), "vr": round(float(vr[t]), 2)}
            d4 = b4_ok(b5_days.get(dates[t]))
            out["B1"].append({**base, "s": t, "b4": bool(d4 and d4["ok"]), "sx": d4 and d4["sx"]})
            if e["ext"]:
                out["B2"].append({**base, "s": t})
            if t + 1 < n and c[t + 1] <= l[t] + (h[t] - l[t]) / 3:
                out["B3"].append({**base, "s": t + 1, "lvl": round(l[t] + (h[t] - l[t]) / 3, 2)})
    marks = []
    for k, lst in out.items():
        last = -10 ** 9
        for x in sorted(lst, key=lambda x: x["s"]):
            if x["s"] - last >= DEDUP:
                marks.append({"k": k, **x})
                last = x["s"]
    return marks
