"""Volume Profile Lab — POC / Value Area / HVN-LVN có giá trị trên cổ phiếu VN không? KHÔNG đụng app nào.

    "c:\\Claude code\\price-path\\venv\\Scripts\\python" measure.py          # ~1–3 phút → results.json
    "c:\\Claude code\\price-path\\venv\\Scripts\\python" measure.py --quick  # 6 mã

Chỉ ĐỌC price-path/data/history.json (nến ngày điều chỉnh 39 mã, 10/2015→) và price-path/data/zone/*.json (50 phiên
KL theo mức giá: 4 phiên tick thật, 46 phiên ước lượng từ nến 1'). Không import code app.

Dựng profile từ nến ngày (tick chỉ có từ 18/09/2026): KL mỗi nến rải lên [Low, High] theo
  U — đều;   T — tam giác đỉnh ở giá điển hình (H+L+C)/3.
Nến H = L (trần/sàn cả phiên, mất thanh khoản) → toàn bộ KL vào đúng 1 mức giá.
Cửa sổ lăn W = 20/60/120 phiên, 40 ô đều nhau trên [min L, max H] của cửa sổ; POC = ô KL lớn nhất;
Value Area = mở rộng từ POC về phía ô kề lớn hơn tới ≥ 70 % (y hệt price-path/zone/profile.value_area);
VAL = mép dưới ô thấp nhất, VAH = mép trên ô cao nhất. Tín hiệu phiên t chỉ dùng profile của t−1 (đã biết trước).

GIẢ THUYẾT — ghi TRƯỚC khi chạy, không chỉnh ngưỡng theo kết quả. Mặc định W=60, profile T.
  H1a MUA  Chạm VAL từ trên: 5 phiên trước đóng cửa > VAL, hôm nay Low ≤ VAL + 0,25 ATR, đóng cửa ≥ VAL (giữ được).
  H1b MUA  Như H1a với POC.
  H1c MUA  Chạm VAL nhưng đóng cửa DƯỚI VAL (thủng) — đối chứng chiều ngược.
  H2  BÁN  Chạm VAH từ dưới: 5 phiên trước đóng < VAH, High ≥ VAH − 0,25 ATR, đóng < VAH (bị từ chối).
  H3a MUA  Quy tắc 80 %: ≥ 2 phiên đóng dưới VAL, hôm nay đóng trở lại ≥ VAL.
  H3b BÁN  Đối xứng: ≥ 2 phiên đóng trên VAH, hôm nay đóng trở lại < VAH.
  H4a MUA  Bứt VAH: hôm qua đóng ≤ VAH, hôm nay đóng > VAH, KL ≥ 1,5× TB20.
  H4b MUA  Bứt VAH không cần KL.
  H4c BÁN  Thủng VAL: hôm qua đóng ≥ VAL, hôm nay đóng < VAL, KL ≥ 1,5× TB20.
  Đối chứng "mức giả" cho H1a/H2: y hệt luật chạm nhưng mức = VAL (VAH) dịch ±2 ATR — nếu mức giả cho kết quả như
  mức thật thì VP không thêm gì ngoài "giá chạm một đường bất kỳ".
  Mô tả (không cổng): D1 vị trí (C−POC)/ATR chia 5 nhóm → lãi +10p; D2 mật độ KL ô chứa giá (HVN↔LVN) chia 5 nhóm
  → |biến động 5p|/ATR (LVN có "trơn" hơn không).

Lệnh: tín hiệu đóng cửa t → mua mở cửa t+1 → bán đóng cửa t+H (H=5/10/20); phí 0,15 %/chiều + thuế 0,1 %.
Mốc mua-đại = mọi phiên-mã cùng năm. Tín hiệu BÁN "đúng" khi lãi sau đó THẤP hơn mua-đại (VN không bán khống → là
tín hiệu thoát). Chống đếm trùng: cùng mã cùng tín hiệu cách nhau < 5 phiên chỉ tính lần đầu.
Thêm: tỷ lệ chạm +1 ATR trước −1 ATR trong 10 phiên (tính từ giá đóng cửa t) so với nền mọi ngày.
Cổng: n ≥ 150, ≥ 7 năm đúng dấu (năm có ≥ 5 lệnh), |vượt| ≥ 1 %, bỏ 2022 vẫn đúng dấu, 2016–20 và 2021–26 cùng dấu.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8", errors="replace")

PP = Path(__file__).resolve().parents[1] / "price-path"   # chỉ main() đo 10 năm dùng; repo confluence-flow không chạy
HIST = PP / "data" / "history.json"
ZONE = PP / "data" / "zone"
HERE = Path(__file__).resolve().parent
INDEX = "VNINDEX"
FEE, TAX = 0.0015, 0.001
HS = (5, 10, 20)
FROM_YEAR = 2016
EXCL = 2022
NBINS = 40
VA_PCT = 0.70
WINDOWS = (20, 60, 120)
MAIN_W = 60
DEDUP = 5
GATE_N, GATE_YEARS, GATE_EDGE = 150, 7, 0.01


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


# ============================================================================== dựng profile
def bar_cdf(edges: np.ndarray, lo: np.ndarray, hi: np.ndarray, tp: np.ndarray, kind: str) -> np.ndarray:
    """Tỷ lệ KL mỗi nến nằm dưới từng mép ô: ma trận (số nến × số mép)."""
    e = edges[None, :]
    L, H = lo[:, None], hi[:, None]
    span = H - L
    flat = span <= 1e-9
    with np.errstate(divide="ignore", invalid="ignore"):
        if kind == "U":
            f = np.clip((e - L) / span, 0, 1)
        else:                                      # tam giác (L, M, H)
            M = np.clip(tp[:, None], L, H)
            a = np.where(M - L > 1e-9, (e - L) ** 2 / (span * (M - L)), 0.0)
            b = np.where(H - M > 1e-9, 1 - (H - e) ** 2 / (span * (H - M)), 1.0)
            f = np.where(e <= L, 0.0, np.where(e >= H, 1.0, np.where(e <= M, a, b)))
    f = np.where(flat, (e >= L).astype(float), f)
    return np.nan_to_num(f)


def value_area(tot: np.ndarray, poc: int, pct: float = VA_PCT) -> tuple[int, int]:
    grand = tot.sum()
    lo = hi = poc
    acc = tot[poc]
    n = len(tot)
    while acc < grand * pct and (lo > 0 or hi < n - 1):
        below = tot[lo - 1] if lo > 0 else -1
        above = tot[hi + 1] if hi < n - 1 else -1
        if above > below:
            hi += 1
            acc += above
        else:
            lo -= 1
            acc += below
    return lo, hi


def profile(lo, hi, tp, v, kind="T", nbins=NBINS, edges=None):
    if edges is None:
        a, b = float(lo.min()), float(hi.max())
        if b - a < 1e-9:
            b = a + 1e-3
        edges = np.linspace(a, b + 1e-9, nbins + 1)
    cdf = bar_cdf(edges, lo, hi, tp, kind)
    tot = (np.diff(cdf, axis=1) * v[:, None]).sum(axis=0)
    return edges, tot


def levels(edges, tot):
    poc = int(np.argmax(tot))
    a, b = value_area(tot, poc)
    return 0.5 * (edges[poc] + edges[poc + 1]), edges[a], edges[b + 1]


def rolling_levels(df: pd.DataFrame, W: int, kind: str) -> pd.DataFrame:
    lo, hi, c, v = (df[k].to_numpy(float) for k in ("l", "h", "c", "v"))
    tp = (hi + lo + c) / 3
    n = len(df)
    poc = np.full(n, np.nan); val = np.full(n, np.nan); vah = np.full(n, np.nan); dens = np.full(n, np.nan)
    for t in range(W - 1, n):
        s = slice(t - W + 1, t + 1)
        if v[s].sum() <= 0:
            continue
        edges, tot = profile(lo[s], hi[s], tp[s], v[s], kind)
        poc[t], val[t], vah[t] = levels(edges, tot)
        i = min(NBINS - 1, max(0, int(np.searchsorted(edges, c[t]) - 1)))
        dens[t] = tot[i] / tot.mean()
    return pd.DataFrame({"poc": poc, "val": val, "vah": vah, "dens": dens}, index=df.index)


# ============================================================================== khung dữ liệu
def base_frame(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["d", "o", "h", "l", "c", "v"])
    df["d"] = pd.to_datetime(df["d"])
    o, h, l, c, v = df["o"], df["h"], df["l"], df["c"], df["v"].astype(float)
    c1 = c.shift(1)
    tr = pd.concat([h - l, (h - c1).abs(), (l - c1).abs()], axis=1).max(axis=1)
    df["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    df["vr"] = v / v.shift(1).rolling(20).mean()
    for H in HS:
        df[f"net{H}"] = c.shift(-H) * (1 - FEE - TAX) / (o.shift(-1) * (1 + FEE)) - 1
    # chạm +1 ATR trước −1 ATR trong 10 phiên, mốc = đóng cửa t (1 = lên trước, 0 = xuống trước/cùng phiên, nan = không chạm)
    hh, ll, cc, aa = h.to_numpy(), l.to_numpy(), c.to_numpy(), df["atr"].to_numpy()
    n = len(df)
    tch = np.full(n, np.nan)
    for t in range(n - 10):
        up, dn = cc[t] + aa[t], cc[t] - aa[t]
        for k in range(t + 1, t + 11):
            u, d = hh[k] >= up, ll[k] <= dn
            if u or d:
                tch[t] = 1.0 if (u and not d) else 0.0
                break
    df["touch"] = tch
    df["amove5"] = (c.shift(-5) - c).abs() / df["atr"]
    return df


def dedup(mask: pd.Series) -> pd.Series:
    m = mask.to_numpy(bool).copy()
    last = -10**9
    for i in np.flatnonzero(m):
        if i - last < DEDUP:
            m[i] = False
        else:
            last = i
    return pd.Series(m, index=mask.index)


def signals(df: pd.DataFrame, L: pd.DataFrame, fake_shift: float = 0.0) -> dict[str, pd.Series]:
    c, h, l, a, vr = df["c"], df["h"], df["l"], df["atr"], df["vr"]
    P = L.shift(1)                                   # profile đến hôm qua
    val = P["val"] + fake_shift * a
    vah = P["vah"] + fake_shift * a
    poc = P["poc"]
    above5 = pd.concat([(c.shift(k) > val) for k in range(1, 6)], axis=1).all(axis=1)
    below5 = pd.concat([(c.shift(k) < vah) for k in range(1, 6)], axis=1).all(axis=1)
    above5p = pd.concat([(c.shift(k) > poc) for k in range(1, 6)], axis=1).all(axis=1)
    touch_val = above5 & (l <= val + 0.25 * a)
    out = {
        "H1a": touch_val & (c >= val),
        "H1c": touch_val & (c < val),
        "H2": below5 & (h >= vah - 0.25 * a) & (c < vah),
    }
    if fake_shift:
        return out
    Pv, Ph = L["val"].shift(1), L["vah"].shift(1)
    out.update({
        "H1b": above5p & (l <= poc + 0.25 * a) & (c >= poc),
        "H3a": (c.shift(1) < Pv.shift(1)) & (c.shift(2) < Pv.shift(2)) & (c >= Pv),
        "H3b": (c.shift(1) > Ph.shift(1)) & (c.shift(2) > Ph.shift(2)) & (c < Ph),
        "H4a": (c.shift(1) <= Ph.shift(1)) & (c > Ph) & (vr >= 1.5),
        "H4b": (c.shift(1) <= Ph.shift(1)) & (c > Ph),
        "H4c": (c.shift(1) >= Pv.shift(1)) & (c < Pv) & (vr >= 1.5),
    })
    return out


SIDE = {"H1a": "MUA", "H1b": "MUA", "H1c": "MUA", "H2": "BÁN", "H3a": "MUA", "H3b": "BÁN",
        "H4a": "MUA", "H4b": "MUA", "H4c": "BÁN"}
DESC = {
    "H1a": "Chạm VAL từ trên, đóng cửa giữ trên VAL",
    "H1b": "Chạm POC từ trên, đóng cửa giữ trên POC",
    "H1c": "Chạm VAL, đóng cửa thủng dưới VAL",
    "H2": "Chạm VAH từ dưới, bị đẩy lùi (đóng dưới VAH)",
    "H3a": "Quy tắc 80 %: ≥2 phiên dưới VAL rồi đóng lại trong VA",
    "H3b": "Quy tắc 80 %: ≥2 phiên trên VAH rồi đóng lại trong VA",
    "H4a": "Bứt lên trên VAH + KL ≥ 1,5×",
    "H4b": "Bứt lên trên VAH (không cần KL)",
    "H4c": "Thủng VAL + KL ≥ 1,5×",
}


# ============================================================================== thống kê
def bench(E: pd.DataFrame) -> dict:
    return {H: E.groupby("year")[f"net{H}"].mean() for H in HS}


def stats(sel: pd.DataFrame, bm: dict, H: int, side: str, touch_base: float) -> dict:
    col = f"net{H}"
    g = sel[sel[col].notna()]
    if g.empty:
        return {"n": 0}
    ex = g[col] - g["year"].map(bm[H])
    sgn = 1 if side == "MUA" else -1
    by = ex.groupby(g["year"]).agg(["mean", "size"])
    by = by[by["size"] >= 5]
    no22 = ex[g["year"] != EXCL]
    h1 = ex[g["year"] <= 2020]
    h2 = ex[g["year"] >= 2021]
    tc = g["touch"].dropna()
    return {"n": int(len(g)), "ret": float(g[col].mean()), "ex": float(ex.mean()),
            "win": float((g[col] > 0).mean()), "years_win": int(((sgn * by["mean"]) > 0).sum()),
            "years": int(len(by)), "ex_no22": float(no22.mean()) if len(no22) else None,
            "ex_h1": float(h1.mean()) if len(h1) else None, "ex_h2": float(h2.mean()) if len(h2) else None,
            "n22": int((g["year"] == EXCL).sum()),
            "touch_up": float(tc.mean()) if len(tc) else None, "touch_base": touch_base,
            "by_year": {int(y): [round(float(r["mean"]), 5), int(r["size"])] for y, r in by.iterrows()}}


def gate(st: dict, side: str) -> bool:
    if st.get("n", 0) < GATE_N:
        return False
    s = 1 if side == "MUA" else -1
    ok_half = all(x is not None and s * x > 0 for x in (st["ex_h1"], st["ex_h2"]))
    return (st["years_win"] >= GATE_YEARS and s * st["ex"] >= GATE_EDGE
            and st["ex_no22"] is not None and s * st["ex_no22"] > 0 and ok_half)


def quint(E: pd.DataFrame, col: str, target: str) -> list:
    x = E[[col, target, "year"]].dropna()
    x = x[np.isfinite(x[col])]
    q = pd.qcut(x[col], 5, labels=False, duplicates="drop")
    rows = []
    for k in sorted(q.unique()):
        g = x[q == k]
        rows.append({"q": int(k) + 1, "lo": float(g[col].min()), "hi": float(g[col].max()),
                     "mean": float(g[target].mean()), "n": int(len(g))})
    return rows


# ============================================================================== Bước 0: đối chiếu với tick/1'
def validate(hist: dict, syms: list[str]) -> dict:
    out = {"per_symbol": [], "summary": {}}
    for sym in syms:
        p = ZONE / f"{sym}.json"
        if not p.exists():
            continue
        z = json.loads(p.read_text(encoding="utf-8"))["sessions"]
        days = sorted(z)
        rows = {r[0]: r for r in hist[sym]}
        days = [d for d in days if d in rows]
        if len(days) < 20:
            continue
        pts, vols = [], []
        for d in days:
            s = z[d]
            f = rows[d][4] / s["close"] if s.get("close") else 1.0
            f = 1.0 if abs(f - 1) < 0.005 else f
            for k, arr in s["levels"].items():
                pts.append(float(k) * f)
                vols.append(sum(arr[:3]))
        pts, vols = np.array(pts), np.array(vols, float)
        bars = np.array([rows[d][1:6] for d in days], float)
        lo, hi, c, v = bars[:, 2], bars[:, 1], bars[:, 3], bars[:, 4]
        a, b = min(pts.min(), lo.min()), max(pts.max(), hi.max())
        edges = np.linspace(a, b + 1e-9, NBINS + 1)
        ref = np.histogram(pts, bins=edges, weights=vols)[0]
        r_poc, r_val, r_vah = levels(edges, ref)
        rec = {"symbol": sym, "n": len(days), "real": sum(1 for d in days if not z[d].get("est")),
               "close": float(c[-1]), "ref": [r_poc, r_val, r_vah]}
        for kind in ("U", "T"):
            _, tot = profile(lo, hi, (hi + lo + c) / 3, v, kind, edges=edges)
            poc, val, vah = levels(edges, tot)
            inter = max(0.0, min(vah, r_vah) - max(val, r_val))
            union = max(vah, r_vah) - min(val, r_val)
            rec[kind] = {"poc_err": abs(poc - r_poc) / c[-1], "va_iou": inter / union if union > 0 else 0,
                         "corr": float(np.corrcoef(tot, ref)[0, 1])}
        # mức "ngây thơ": POC = trung bình giá đóng cửa có trọng số KL (VWAP) — profile có hơn không?
        vwap = float((c * v).sum() / v.sum())
        rec["vwap_err"] = abs(vwap - r_poc) / c[-1]
        rec["range_pct"] = (b - a) / c[-1]
        out["per_symbol"].append(rec)
    ps = out["per_symbol"]
    for kind in ("U", "T"):
        out["summary"][kind] = {
            "poc_err_med": float(np.median([r[kind]["poc_err"] for r in ps])),
            "poc_err_p80": float(np.percentile([r[kind]["poc_err"] for r in ps], 80)),
            "poc_within_2pct": float(np.mean([r[kind]["poc_err"] <= 0.02 for r in ps])),
            "va_iou_med": float(np.median([r[kind]["va_iou"] for r in ps])),
            "corr_med": float(np.median([r[kind]["corr"] for r in ps])),
        }
    out["summary"]["vwap_err_med"] = float(np.median([r["vwap_err"] for r in ps]))
    out["summary"]["range_med"] = float(np.median([r["range_pct"] for r in ps]))
    out["summary"]["n_symbols"] = len(ps)
    return out


def illustrate(hist: dict, sym: str) -> dict:
    """Profile 60 phiên gần nhất (nến ngày T) + profile tick/1' cùng lưới, kèm giá đóng cửa để vẽ."""
    rows = hist[sym][-MAIN_W:]
    bars = np.array([r[1:6] for r in rows], float)
    lo, hi, c, v = bars[:, 2], bars[:, 1], bars[:, 3], bars[:, 4]
    edges, tot = profile(lo, hi, (hi + lo + c) / 3, v, "T")
    poc, val, vah = levels(edges, tot)
    out = {"symbol": sym, "dates": [r[0] for r in rows], "close": c.tolist(), "high": hi.tolist(), "low": lo.tolist(),
           "edges": edges.round(3).tolist(), "vol": tot.round(0).tolist(), "poc": poc, "val": val, "vah": vah}
    p = ZONE / f"{sym}.json"
    if p.exists():
        z = json.loads(p.read_text(encoding="utf-8"))["sessions"]
        rmap = {r[0]: r for r in hist[sym]}
        pts, vols = [], []
        for d, s in z.items():
            if d not in rmap:
                continue
            f = rmap[d][4] / s["close"] if s.get("close") else 1.0
            f = 1.0 if abs(f - 1) < 0.005 else f
            for k, arr in s["levels"].items():
                pts.append(float(k) * f); vols.append(sum(arr[:3]))
        e2 = np.linspace(min(pts), max(pts) + 1e-9, NBINS + 1)
        ref = np.histogram(pts, bins=e2, weights=vols)[0].astype(float)
        out["tick"] = {"edges": e2.round(3).tolist(), "vol": ref.round(0).tolist(), "from": min(z), "to": max(z)}
        out["tick"]["poc"], out["tick"]["val"], out["tick"]["vah"] = levels(e2, ref)
    return out


# ============================================================================== main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    hist = json.loads(HIST.read_text(encoding="utf-8"))["bars"]
    syms = sorted(s for s in hist if s != INDEX)
    if a.quick:
        syms = syms[:6]
    log(f"{len(syms)} mã")

    res: dict = {"meta": {"symbols": syms, "last_day": max(r[-1][0] for r in hist.values()), "windows": WINDOWS,
                          "main_w": MAIN_W, "nbins": NBINS, "fee": FEE, "tax": TAX}}
    res["validate"] = validate(hist, syms)
    log(f"đối chiếu: {json.dumps(res['validate']['summary'], ensure_ascii=False)}")

    variants = [(MAIN_W, "T"), (MAIN_W, "U"), (20, "T"), (120, "T")]
    frames = {vk: [] for vk in variants}
    fake = []
    for sym in syms:
        df = base_frame(hist[sym])
        cache = {}
        for W, kind in variants:
            L = rolling_levels(df, W, kind)
            cache[(W, kind)] = L
            sg = signals(df, L)
            x = df[["d", "c", "atr", "vr", "touch", "amove5"] + [f"net{H}" for H in HS]].copy()
            x["symbol"] = sym
            for k, m in sg.items():
                x[k] = dedup(m.fillna(False))
            if (W, kind) == variants[0]:
                x["posatr"] = (df["c"] - L["poc"]) / df["atr"]
                x["dens"] = L["dens"]
            frames[(W, kind)].append(x)
        L = cache[variants[0]]
        for sh in (-2.0, 2.0):
            sg = signals(df, L, fake_shift=sh)
            x = df[["d", "touch"] + [f"net{H}" for H in HS]].copy()
            x["symbol"] = sym
            for k, m in sg.items():
                x[k] = dedup(m.fillna(False))
            fake.append(x)
        log(f"  {sym} xong")

    res["variants"] = {}
    for (W, kind), parts in frames.items():
        F = pd.concat(parts, ignore_index=True)
        F["year"] = F["d"].dt.year
        E = F[(F["year"] >= FROM_YEAR) & F["net20"].notna()].copy()
        bm = bench(E)
        tb = float(E["touch"].dropna().mean())
        key = f"W{W}{kind}"
        vr = {"bench": {H: float(E[f"net{H}"].mean()) for H in HS}, "touch_base": tb,
              "n_rows": int(len(E)), "years": [int(E["year"].min()), int(E["year"].max())], "sig": {}}
        for k in SIDE:
            sel = E[E[k]]
            st = {H: stats(sel, bm, H, SIDE[k], tb) for H in HS}
            st["gate"] = gate(st[10], SIDE[k])
            vr["sig"][k] = st
        if (W, kind) == variants[0]:
            vr["D1_pos"] = quint(E, "posatr", "net10")
            vr["D2_dens_move"] = quint(E, "dens", "amove5")
            vr["D2_dens_ret"] = quint(E, "dens", "net10")
            FK = pd.concat(fake, ignore_index=True)
            FK["year"] = FK["d"].dt.year
            FK = FK[(FK["year"] >= FROM_YEAR) & FK["net20"].notna()]
            vr["fake"] = {k: stats(FK[FK[k]], bm, 10, SIDE[k], tb) for k in ("H1a", "H1c", "H2")}
        res["variants"][key] = vr
        log(f"{key}: " + ", ".join(f"{k} n={v[10]['n']} ex={v[10].get('ex', 0):+.2%}{' ✓' if v['gate'] else ''}"
                                   for k, v in vr["sig"].items()))

    res["illus"] = [illustrate(hist, s) for s in ("FPT", "HPG", "VCB") if s in hist]
    (HERE / "results.json").write_text(json.dumps(res, ensure_ascii=False, default=float), encoding="utf-8")
    log("ghi results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
