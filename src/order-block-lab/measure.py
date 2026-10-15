"""Order Block Lab — Order Block (SMC/ICT) có giá trị trên cổ phiếu VN không? KHÔNG đụng app nào.

    "c:\\Claude code\\price-path\\venv\\Scripts\\python" measure.py          # 39 mã → results.json
    "c:\\Claude code\\price-path\\venv\\Scripts\\python" measure.py --quick  # 6 mã

Chỉ ĐỌC price-path/data/history.json (nến ngày điều chỉnh 39 mã, 10/2015→). Khung đo y hệt volume-profile-lab.

ĐỊNH NGHĨA — cố định TRƯỚC khi chạy, không chỉnh theo kết quả.
  Swing high/low: fractal 2 nến mỗi bên, chỉ biết sau 2 phiên. "Đỉnh cấu trúc" = swing high gần nhất chưa bị đóng
  cửa vượt qua (biết tại phiên k). Đáy cấu trúc đối xứng.
  OB tăng tại nến k: k ĐỎ (C<O), k+1 XANH (→ k là nến đỏ cuối), trong k+1..k+3 có phiên m đầu tiên mà
    - displacement: đóng cửa ≥ C[k] + 1,5 ATR14[k], và
    - BOS: đã có một phiên trong k+1..m đóng cửa trên đỉnh cấu trúc tại k.
  Vùng OB = [L[k], H[k]], MT = giữa vùng. OB được biết tại m (chỉ dùng dữ liệu ≤ m).
  FVG: có i trong k..m−2 với L[i+2] > H[i].  KL: max KL/TB20 trong k+1..m ≥ 1,5.
  Chạm: sau m, chờ một phiên nằm HẲN trên vùng (L > đỉnh vùng) rồi phiên đầu tiên L ≤ đỉnh vùng = chạm lần đầu;
  OB sống 60 phiên tính từ m. Cùng luật cho vùng giả.

GIẢ THUYẾT
  H1 MUA  OB tăng chạm lần đầu, đóng cửa ≥ đáy vùng.
  H2 MUA  H1 + nhịp tăng có FVG.
  H3 MUA  H1 + nhịp tăng có KL ≥ 1,5× TB20.
  H4 MUA  H1 + chạm tới MT mà đóng cửa ≥ MT.
  H5 MUA  Chạm lần đầu nhưng đóng cửa THỦNG đáy vùng (đối chứng chiều ngược).
  H6 BÁN  OB giảm (đối xứng) chạm lần đầu từ dưới, đóng cửa < đỉnh vùng.
  H7 BÁN  Breaker: OB tăng bị đóng cửa thủng đáy, giá rời hẳn xuống dưới (H < đáy vùng), rồi phiên đầu tiên H ≥ đáy vùng.
  Đối chứng: G± = H1 với vùng dịch ±2 ATR14[k];  C1 = như H1 nhưng KHÔNG có BOS;  C2 = nến đỏ bất kỳ (không
  displacement, không BOS), cùng luật chạm.

Lệnh: tín hiệu đóng cửa t → mua mở cửa t+1 → bán đóng cửa t+H (H=5/10/20); phí 0,15 %/chiều + thuế 0,1 %.
Mốc mua-đại = mọi phiên-mã cùng năm. BÁN "đúng" khi lãi sau đó THẤP hơn mua-đại (VN không bán khống → tín hiệu thoát).
Chống đếm trùng: cùng mã cùng tín hiệu cách nhau < 5 phiên chỉ tính lần đầu.
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
HERE = Path(__file__).resolve().parent
INDEX = "VNINDEX"
FEE, TAX = 0.0015, 0.001
HS = (5, 10, 20)
FROM_YEAR = 2016
EXCL = 2022
DEDUP = 5
GATE_N, GATE_YEARS, GATE_EDGE = 150, 7, 0.01
DISP = 1.5           # displacement tính bằng ATR
DISP_WIN = 3         # số phiên tối đa cho nhịp
LIFE = 60            # OB sống bao nhiêu phiên
VOL_X = 1.5
FAKE = 2.0           # vùng giả dịch ± bao nhiêu ATR
ILLUS = ("FPT", "HPG", "VPB")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


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
    return df


def structure(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Đỉnh/đáy cấu trúc chưa bị phá, biết tại phiên t (fractal 2 nến, xác nhận ở i+2)."""
    n = len(h)
    sh = np.full(n, np.nan)
    sl = np.full(n, np.nan)
    hi = lo = np.nan
    for t in range(n):
        i = t - 2
        if i >= 2:
            if h[i] > max(h[i - 1], h[i - 2]) and h[i] >= max(h[i + 1], h[i + 2]):
                hi = h[i]
            if l[i] < min(l[i - 1], l[i - 2]) and l[i] <= min(l[i + 1], l[i + 2]):
                lo = l[i]
        if not np.isnan(hi) and c[t] > hi:
            hi = np.nan
        if not np.isnan(lo) and c[t] < lo:
            lo = np.nan
        sh[t], sl[t] = hi, lo
    return sh, sl


def structure_events(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> tuple[list, list]:
    """Chỉ để vẽ: swing (HH/LH/HL/LL) và lần phá cấu trúc (BOS cùng chiều lần phá trước, CHoCH đổi chiều).
    Cùng luật fractal 2 nến và cùng thứ tự cập nhật như structure()."""
    n = len(h)
    swings, breaks = [], []
    hi = lo = None                    # (chỉ số, giá) của đỉnh/đáy cấu trúc chưa bị phá
    last_hi = last_lo = None
    trend = 0
    for t in range(n):
        i = t - 2
        if i >= 2:
            if h[i] > max(h[i - 1], h[i - 2]) and h[i] >= max(h[i + 1], h[i + 2]):
                swings.append({"i": i, "p": h[i], "lab": "HH" if last_hi is None or h[i] > last_hi else "LH", "up": True})
                last_hi = h[i]
                hi = (i, h[i])
            if l[i] < min(l[i - 1], l[i - 2]) and l[i] <= min(l[i + 1], l[i + 2]):
                swings.append({"i": i, "p": l[i], "lab": "LL" if last_lo is None or l[i] < last_lo else "HL", "up": False})
                last_lo = l[i]
                lo = (i, l[i])
        if hi is not None and c[t] > hi[1]:
            breaks.append({"s": hi[0], "t": t, "p": hi[1], "up": True, "lab": "CHoCH" if trend == -1 else "BOS"})
            trend, hi = 1, None
        if lo is not None and c[t] < lo[1]:
            breaks.append({"s": lo[0], "t": t, "p": lo[1], "up": False, "lab": "CHoCH" if trend == 1 else "BOS"})
            trend, lo = -1, None
    return swings, breaks


FVG_MIN, FVG_LIFE = 0.5, 20


def fvg_events(h: np.ndarray, l: np.ndarray, a: np.ndarray) -> list:
    """Chỉ để vẽ: FVG ≥ 0,5 ATR, kéo tới khi giá lấp kín hoặc hết 20 phiên."""
    n = len(h)
    out = []
    for i in range(n - 2):
        if l[i + 2] - h[i] >= FVG_MIN * a[i]:
            bot, top, up = h[i], l[i + 2], True
        elif l[i] - h[i + 2] >= FVG_MIN * a[i]:
            bot, top, up = h[i + 2], l[i], False
        else:
            continue
        end = min(i + 2 + FVG_LIFE, n - 1)
        for t in range(i + 3, end + 1):
            if (up and l[t] <= bot) or (not up and h[t] >= top):
                end = t
                break
        out.append({"i": i + 1, "end": end, "lo": bot, "hi": top, "up": up})
    return out


# ============================================================================== dò OB
def find_obs(df: pd.DataFrame, bull: bool, need_bos: bool | None, disp: float = DISP) -> list[dict]:
    """need_bos: True = phải có BOS, False = phải KHÔNG có BOS (C1), None = nến ngược màu bất kỳ (C2)."""
    o, h, l, c, a, vr = (df[k].to_numpy(float) for k in ("o", "h", "l", "c", "atr", "vr"))
    sh, sl = structure(h, l, c)
    n = len(df)
    out = []
    s = 1 if bull else -1
    for k in range(20, n - 1):
        if not (s * (c[k] - o[k]) < 0 and s * (c[k + 1] - o[k + 1]) > 0):
            continue
        if need_bos is None:
            out.append({"k": k, "m": k, "lo": l[k], "hi": h[k], "atr": a[k], "fvg": False, "vol": False})
            continue
        lvl = sh[k] if bull else sl[k]
        bos = False
        m = None
        for j in range(k + 1, min(k + DISP_WIN, n - 1) + 1):
            if not np.isnan(lvl) and s * (c[j] - lvl) > 0:
                bos = True
            if s * (c[j] - c[k]) >= disp * a[k]:
                if need_bos and not bos:
                    continue
                m = j
                break
        if m is None or (need_bos is False and bos):
            continue
        if bull:
            fvg = any(l[i + 2] > h[i] for i in range(k, m - 1))
        else:
            fvg = any(h[i + 2] < l[i] for i in range(k, m - 1))
        vol = bool(np.nanmax(vr[k + 1:m + 1]) >= VOL_X)
        out.append({"k": k, "m": m, "lo": l[k], "hi": h[k], "atr": a[k], "fvg": fvg, "vol": vol})
    return out


def first_touch(h, l, ob: dict, bull: bool, shift: float = 0.0) -> int | None:
    """Phiên chạm lần đầu sau khi giá rời hẳn vùng (về phía nhịp)."""
    lo, hi = ob["lo"] + shift * ob["atr"], ob["hi"] + shift * ob["atr"]
    armed = False
    n = len(h)
    for t in range(ob["m"] + 1, min(ob["m"] + LIFE, n - 1) + 1):
        if bull:
            if armed and l[t] <= hi:
                return t
            if l[t] > hi:
                armed = True
        else:
            if armed and h[t] >= lo:
                return t
            if h[t] < lo:
                armed = True
    return None


def breaker(h, l, c, ob: dict) -> int | None:
    """OB tăng bị đóng cửa thủng, giá rời hẳn xuống dưới, rồi hồi lên chạm lại đáy vùng."""
    n = len(h)
    lo = ob["lo"]
    t = ob["m"] + 1
    end = min(ob["m"] + LIFE, n - 1)
    while t <= end and c[t] >= lo:
        t += 1
    if t > end:
        return None
    b = t
    away = False
    for t in range(b + 1, min(b + LIFE, n - 1) + 1):
        if away and h[t] >= lo:
            return t
        if h[t] < lo:
            away = True
    return None


# ============================================================================== tín hiệu mỗi mã
SIDE = {"H1": "MUA", "H2": "MUA", "H3": "MUA", "H4": "MUA", "H5": "MUA", "H6": "BÁN", "H7": "BÁN",
        "G+": "MUA", "G-": "MUA", "C1": "MUA", "C2": "MUA", "D10": "MUA", "D20": "MUA"}
DESC = {
    "H1": "OB tăng, chạm lần đầu, đóng cửa giữ trên đáy vùng",
    "H2": "H1 + nhịp tăng để lại FVG (bản ICT chuẩn)",
    "H3": "H1 + nhịp tăng có KL ≥ 1,5× TB20",
    "H4": "H1 + chạm tới Mean Threshold (50 %) mà đóng cửa giữ trên MT",
    "H5": "Chạm OB tăng nhưng đóng cửa THỦNG đáy vùng",
    "H6": "OB giảm, chạm lần đầu từ dưới, bị đẩy lùi",
    "H7": "Breaker: OB tăng đã thủng, giá hồi lên chạm lại",
    "G+": "Vùng giả: OB tăng dịch LÊN 2 ATR",
    "G-": "Vùng giả: OB tăng dịch XUỐNG 2 ATR",
    "C1": "Nến đỏ trước nhịp tăng 1,5 ATR nhưng KHÔNG phá cấu trúc",
    "C2": "Nến đỏ bất kỳ (nến sau xanh), cùng luật chạm",
    "D10": "H1 với nhịp 1,0 ATR (độ nhạy)",
    "D20": "H1 với nhịp 2,0 ATR (độ nhạy)",
}
HYP = ("H1", "H2", "H3", "H4", "H5", "H6", "H7")
CTRL = ("G+", "G-", "C1", "C2", "D10", "D20")


def symbol_signals(df: pd.DataFrame) -> tuple[dict, list, list]:
    h, l, c = (df[k].to_numpy(float) for k in ("h", "l", "c"))
    n = len(df)
    sig = {k: np.zeros(n, bool) for k in SIDE}
    age = np.full(n, np.nan)                  # tuổi OB (phiên từ m tới chạm) cho H1
    events = []

    bulls = find_obs(df, True, True)
    for ob in bulls:
        ev = {"k": ob["k"], "m": ob["m"], "lo": ob["lo"], "hi": ob["hi"], "bull": True, "fvg": ob["fvg"],
              "vol": ob["vol"], "w_atr": (ob["hi"] - ob["lo"]) / ob["atr"], "t": None, "res": None, "brk": None}
        t = first_touch(h, l, ob, True)
        if t is not None:
            ev["t"] = t
            mt = 0.5 * (ob["lo"] + ob["hi"])
            if c[t] >= ob["lo"]:
                sig["H1"][t] = True
                age[t] = t - ob["m"] if np.isnan(age[t]) else min(age[t], t - ob["m"])
                sig["H2"][t] |= ob["fvg"]
                sig["H3"][t] |= ob["vol"]
                if l[t] <= mt and c[t] >= mt:
                    sig["H4"][t] = True
                ev["res"] = "giữ"
            else:
                sig["H5"][t] = True
                ev["res"] = "thủng"
        b = breaker(h, l, c, ob)
        if b is not None:
            sig["H7"][b] = True
            ev["brk"] = b
        ev["brk_close"] = next((t for t in range(ob["m"] + 1, min(ob["m"] + LIFE, n - 1) + 1) if c[t] < ob["lo"]), None)
        for sh_, key in ((FAKE, "G+"), (-FAKE, "G-")):
            tf = first_touch(h, l, ob, True, sh_)
            if tf is not None and c[tf] >= ob["lo"] + sh_ * ob["atr"]:
                sig[key][tf] = True
        events.append(ev)

    for ob in find_obs(df, False, True):
        ev = {"k": ob["k"], "m": ob["m"], "lo": ob["lo"], "hi": ob["hi"], "bull": False, "fvg": ob["fvg"],
              "vol": ob["vol"], "w_atr": (ob["hi"] - ob["lo"]) / ob["atr"], "t": None, "res": None, "brk": None}
        t = first_touch(h, l, ob, False)
        if t is not None:
            ev["t"] = t
            if c[t] < ob["hi"]:
                sig["H6"][t] = True
                ev["res"] = "giữ"
            else:
                ev["res"] = "thủng"
        events.append(ev)

    for key, need, disp in (("C1", False, DISP), ("C2", None, DISP), ("D10", True, 1.0), ("D20", True, 2.0)):
        for ob in find_obs(df, True, need, disp):
            t = first_touch(h, l, ob, True)
            if t is not None and c[t] >= ob["lo"]:
                sig[key][t] = True
    return sig, age, events


def dedup(m: np.ndarray) -> np.ndarray:
    m = m.copy()
    last = -10**9
    for i in np.flatnonzero(m):
        if i - last < DEDUP:
            m[i] = False
        else:
            last = i
    return m


# ============================================================================== thống kê (y hệt volume-profile-lab)
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


# ============================================================================== minh hoạ
def illustrate(df: pd.DataFrame, events: list, sym: str, span: int = 160) -> dict:
    n = len(df)
    s0 = n - span
    rows = df.iloc[s0:]
    h, l, c, a = (df[k].to_numpy(float) for k in ("h", "l", "c", "atr"))
    rel = lambda i: None if i is None else i - s0
    obs = []
    for ev in events:
        if ev["m"] < s0 or ev["k"] < s0:
            continue
        end = ev["t"] if ev["t"] is not None else min(ev["m"] + LIFE, n - 1)
        obs.append({"k": ev["k"] - s0, "m": ev["m"] - s0, "end": end - s0, "lo": ev["lo"], "hi": ev["hi"],
                    "bull": ev["bull"], "t": rel(ev["t"]), "res": ev["res"], "fvg": ev["fvg"],
                    "brk": rel(ev["brk"]), "brk_close": rel(ev.get("brk_close"))})
    swings, breaks = structure_events(h, l, c)
    swings = [dict(s, i=s["i"] - s0) for s in swings if s["i"] >= s0]
    breaks = [dict(b, s=max(b["s"], s0) - s0, t=b["t"] - s0) for b in breaks if b["s"] >= s0]
    fvgs = [dict(f, i=f["i"] - s0, end=f["end"] - s0) for f in fvg_events(h, l, a) if f["i"] >= s0]
    return {"symbol": sym, "dates": rows["d"].dt.strftime("%Y-%m-%d").tolist(),
            "ohlc": rows[["o", "h", "l", "c"]].round(3).to_numpy().tolist(), "obs": obs,
            "swings": swings, "breaks": breaks, "fvgs": fvgs}


# ============================================================================== main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--show", default="", help="in vài OB của một mã để soát bằng mắt")
    a = ap.parse_args()
    hist = json.loads(HIST.read_text(encoding="utf-8"))["bars"]
    syms = sorted(s for s in hist if s != INDEX)
    if a.quick:
        syms = syms[:6]
    log(f"{len(syms)} mã")

    frames, evrows, illus = [], [], []
    for sym in syms:
        df = base_frame(hist[sym])
        sig, age, events = symbol_signals(df)
        x = df[["d", "touch"] + [f"net{H}" for H in HS]].copy()
        x["symbol"] = sym
        for k, m in sig.items():
            x[k] = dedup(m)
        x["age"] = age
        frames.append(x)
        for ev in events:
            evrows.append({"symbol": sym, "year": int(df["d"].iloc[ev["k"]].year), "bull": ev["bull"],
                           "touched": ev["t"] is not None, "wait": None if ev["t"] is None else ev["t"] - ev["m"],
                           "res": ev["res"], "fvg": ev["fvg"], "vol": ev["vol"], "w_atr": ev["w_atr"]})
        if sym == a.show:
            for ev in events[-8:]:
                f = lambda i: None if i is None else str(df["d"].iloc[i].date())
                print(f"{'TĂNG' if ev['bull'] else 'GIẢM'} nến {f(ev['k'])} biết {f(ev['m'])} vùng "
                      f"[{ev['lo']:.2f}, {ev['hi']:.2f}] FVG={ev['fvg']} KL={ev['vol']} chạm {f(ev['t'])} "
                      f"→ {ev['res']} breaker {f(ev['brk'])}")
        if sym in ILLUS:
            illus.append(illustrate(df, events, sym))
        log(f"  {sym}: {sum(e['bull'] for e in events)} OB tăng, {sum(not e['bull'] for e in events)} OB giảm")

    F = pd.concat(frames, ignore_index=True)
    F["year"] = F["d"].dt.year
    E = F[(F["year"] >= FROM_YEAR) & F["net20"].notna()].copy()
    bm = bench(E)
    tb = float(E["touch"].dropna().mean())
    res: dict = {"meta": {"symbols": syms, "last_day": max(r[-1][0] for r in hist.values()), "fee": FEE, "tax": TAX,
                          "disp": DISP, "disp_win": DISP_WIN, "life": LIFE, "fake": FAKE, "dedup": DEDUP,
                          "gate": [GATE_N, GATE_YEARS, GATE_EDGE], "from_year": FROM_YEAR},
                 "bench": {H: float(E[f"net{H}"].mean()) for H in HS}, "touch_base": tb,
                 "n_rows": int(len(E)), "years": [int(E["year"].min()), int(E["year"].max())],
                 "desc": DESC, "side": SIDE, "hyp": HYP, "ctrl": CTRL, "sig": {}}
    for k in SIDE:
        sel = E[E[k]]
        st = {H: stats(sel, bm, H, SIDE[k], tb) for H in HS}
        st["gate"] = gate(st[10], SIDE[k])
        res["sig"][k] = st
        log(f"{k:4s} n={st[10]['n']:5d} ex10={st[10].get('ex', 0):+.2%} năm {st[10].get('years_win', 0)}/"
            f"{st[10].get('years', 0)}{'  ✓ QUA CỔNG' if st['gate'] else ''}")

    # tuổi OB lúc chạm (H1)
    h1 = E[E["H1"] & E["net10"].notna()].copy()
    h1["ex"] = h1["net10"] - h1["year"].map(bm[10])
    res["age"] = []
    for lab, a_, b_ in (("1–10", 1, 10), ("11–30", 11, 30), ("31–60", 31, 60)):
        g = h1[(h1["age"] >= a_) & (h1["age"] <= b_)]
        res["age"].append({"label": lab, "n": int(len(g)), "ex": float(g["ex"].mean()) if len(g) else None,
                           "win": float((g["net10"] > 0).mean()) if len(g) else None})

    EV = pd.DataFrame(evrows)
    EV = EV[EV["year"] >= FROM_YEAR]
    d = {}
    for bull, key in ((True, "bull"), (False, "bear")):
        g = EV[EV["bull"] == bull]
        nyears = EV["year"].nunique()
        d[key] = {"n": int(len(g)), "per_sym_year": float(len(g) / len(syms) / max(nyears, 1)),
                  "touched": float(g["touched"].mean()), "wait_med": float(g["wait"].dropna().median()),
                  "hold": float((g["res"] == "giữ").sum() / max(g["touched"].sum(), 1)),
                  "fvg": float(g["fvg"].mean()), "vol": float(g["vol"].mean()), "w_atr_med": float(g["w_atr"].median())}
    res["events"] = d
    res["illus"] = illus
    (HERE / "results.json").write_text(json.dumps(res, ensure_ascii=False, default=float), encoding="utf-8")
    log(f"mua-đại +10p: {res['bench'][10]:+.2%}; chạm +1ATR trước: {tb:.1%}; ghi results.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
