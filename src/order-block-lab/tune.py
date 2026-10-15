"""Tinh chỉnh tiêu chí OB / FVG để tăng xác suất thắng — đo CÓ KỶ LUẬT, KHÔNG đụng app nào.

    "c:\\Claude code\\price-path\\venv\\Scripts\\python" tune.py          # 39 mã → tune.json
    "c:\\Claude code\\price-path\\venv\\Scripts\\python" tune.py --quick  # 6 mã, ít xáo

Dùng lại khung của measure.py (cùng dữ liệu, cùng hàm dò OB / chạm / thống kê / cổng).

ĐỊNH NGHĨA — khoá TRƯỚC khi chạy (10/10/2026), không chỉnh theo kết quả. Nền B0 = H1 của lab cũ (OB tăng chạm lần đầu,
đóng cửa ≥ đáy vùng). 12 biến thể (C = bối cảnh, Q = chất lượng vùng, T = cách chạm, F = FVG đứng riêng):
  C1 giá > MA50 và MA50 dốc lên (so 5 phiên trước)       Q1 tuổi OB lúc chạm 3–20 phiên
  C2 VNINDEX > MA50                                       Q2 bề rộng vùng ≤ 1,5 ATR
  C3 mã mạnh hơn VNINDEX trong 20 phiên                   Q4 nến k có bóng dưới ≥ 35 % biên độ
  T2 phiên chạm có KL < 0,8× TB20                         Q5 vùng nằm nửa dưới biên độ 60 phiên
  F1 mua khi giá hồi về FVG tăng còn mở (chạm mép trên, đóng cửa ≥ mép dưới, sau khi rời hẳn lên trên, ≤ 20 phiên)
  F2 F1 + trùng/sát một OB tăng còn hiệu lực (≤ 0,5 ATR)  F3 F1 + FVG ≥ 1 ATR
  F4 BÁN: FVG giảm chạm từ dưới và bị đẩy lùi (đối chứng chiều thoát)
Lệnh R: tín hiệu đóng cửa t → mua mở cửa t+1, dừng lỗ = đáy vùng − 0,25 ATR, chốt 2R, tối đa 20 phiên (dừng lỗ ưu tiên
nếu cùng ngày chạm cả hai); phí 0,15 %/chiều + thuế 0,1 %. So với lệnh NGẪU NHIÊN cùng mã, cùng năm, cùng khoảng dừng lỗ
(tính theo ATR, làm tròn 0,25).
Chia dữ liệu: chọn 2016–2021 (train), kiểm 2022–2026 (test, có gấu 2022).
Cổng A (cũ, giữ 10 phiên): n ≥ 150, ≥ 7 năm đúng dấu, |vượt| ≥ 1 %, bỏ 2022 còn đúng, 2016–20 & 2021–26 cùng dấu.
Cổng B (R, chỉ trên TEST): n ≥ 60, R TB > nền ngẫu nhiên, tỷ lệ thắng > nền, z vượt phân vị 95 của max-z 11 biến thể MUA
(xáo ngày vào lệnh trong cùng mã-năm 300 lần), vùng giả +2 ATR phải kém hơn, bỏ mã đóng góp nhiều nhất vẫn dương.
QUA = cả hai cổng.
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import numpy as np
import pandas as pd

import measure as M

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8", errors="replace")

OUT = M.HERE / "tune.json"
STOP_PAD = 0.25       # ATR dưới đáy vùng
RR = 2.0
MAX_BARS = 20
X_GRID = np.arange(0.5, 6.01, 0.25)
TRAIN_END = 2021
N_PERM = 300
SEED = 20261010
MIN_N_TEST = 60
rng = np.random.default_rng(SEED)

VARIANTS = {
    "B0": ("Nền: OB tăng chạm lần đầu, giữ trên đáy vùng (H1)", "MUA"),
    "C1": ("Giá > MA50 và MA50 dốc lên", "MUA"),
    "C2": ("VNINDEX > MA50", "MUA"),
    "C3": ("Mã mạnh hơn VNINDEX 20 phiên", "MUA"),
    "Q1": ("OB còn tươi: chạm sau 3–20 phiên", "MUA"),
    "Q2": ("Vùng hẹp ≤ 1,5 ATR", "MUA"),
    "Q4": ("Nến k có bóng dưới ≥ 35 %", "MUA"),
    "Q5": ("Vùng ở nửa dưới biên độ 60 phiên", "MUA"),
    "T2": ("Phiên chạm KL < 0,8× TB20", "MUA"),
    "F1": ("FVG tăng: hồi về mép trên, đóng cửa ≥ mép dưới", "MUA"),
    "F2": ("F1 + trùng/sát OB tăng còn hiệu lực", "MUA"),
    "F3": ("F1 + FVG ≥ 1 ATR", "MUA"),
    "F4": ("FVG giảm bị đẩy lùi (tín hiệu thoát)", "BÁN"),
}
OB_VARS = ("B0", "C1", "C2", "C3", "Q1", "Q2", "Q4", "Q5", "T2")
FVG_VARS = ("F1", "F2", "F3")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", file=sys.stderr, flush=True)


# ============================================================================== mô phỏng lệnh R
def sim_core(o, h, l, c, T: np.ndarray, risk: np.ndarray):
    """Mua mở cửa T+1, dừng = entry − risk, chốt = entry + 2·risk, tối đa 20 phiên. Trả (net ret, R ròng)."""
    entry = o[T + 1]
    stop, tgt = entry - risk, entry + RR * risk
    alive = np.ones(len(T), bool)
    exitp = np.full(len(T), np.nan)
    for j in range(1, MAX_BARS + 1):
        i = T + j
        gap = j > 1
        # dừng lỗ ưu tiên
        hit_s = alive & (l[i] <= stop)
        px_s = np.minimum(o[i], stop) if gap else stop
        exitp[hit_s] = px_s[hit_s] if gap else stop[hit_s]
        alive &= ~hit_s
        hit_t = alive & (h[i] >= tgt)
        px_t = np.maximum(o[i], tgt) if gap else tgt
        exitp[hit_t] = px_t[hit_t]
        alive &= ~hit_t
    exitp[alive] = c[T + MAX_BARS][alive]
    cost_in = entry * (1 + M.FEE)
    out = exitp * (1 - M.FEE - M.TAX)
    return out / cost_in - 1, (out - cost_in) / risk


class Pools:
    """Kết quả lệnh R của MỌI ngày, theo mã × khoảng dừng lỗ (ATR) — nền ngẫu nhiên khớp khoảng dừng lỗ."""

    def __init__(self, df: pd.DataFrame):
        o, h, l, c, a = (df[k].to_numpy(float) for k in ("o", "h", "l", "c", "atr"))
        self.n = len(df)
        self.years = df["d"].dt.year.to_numpy()
        self.T = np.flatnonzero(a[:self.n - MAX_BARS - 1] > 1e-9)      # bỏ ngày ATR = 0 (giá đứng yên) → chia 0
        self.R, self.W = {}, {}
        for X in X_GRID:
            ret, R = sim_core(o, h, l, c, self.T, X * a[self.T])
            self.R[round(float(X), 2)] = R
            self.W[round(float(X), 2)] = ret > 0
        self.by_year = {int(y): np.flatnonzero(self.years[self.T] == y) for y in np.unique(self.years)}

    @staticmethod
    def bucket(x: float) -> float:
        return round(float(np.clip(np.round(x * 4) / 4, X_GRID[0], X_GRID[-1])), 2)

    def pool(self, year: int, x: float):
        idx = self.by_year.get(int(year))
        if idx is None or len(idx) == 0:
            return None, None
        b = self.bucket(x)
        return self.R[b][idx], self.W[b][idx]


# ============================================================================== ứng viên mỗi mã
def ctx_arrays(df: pd.DataFrame, idx: pd.DataFrame | None) -> dict:
    c = df["c"]
    ma50 = c.rolling(50).mean()
    out = {"ma50": ma50.to_numpy(), "ma50_5": ma50.shift(5).to_numpy(),
           "ret20": (c / c.shift(20) - 1).to_numpy()}
    if idx is not None:
        ic = idx.set_index("d")["c"].reindex(df["d"]).ffill()
        out["idx_c"] = ic.to_numpy()
        out["idx_ma50"] = ic.rolling(50).mean().to_numpy()
        out["idx_ret20"] = (ic / ic.shift(20) - 1).to_numpy()
    return out


def ob_candidates(df: pd.DataFrame, ctx: dict, shift: float) -> list[dict]:
    """Mọi lần chạm lần đầu hợp lệ của OB tăng (H1). shift = 0 vùng thật, +2 vùng giả dịch lên 2 ATR."""
    o, h, l, c, a, vr = (df[k].to_numpy(float) for k in ("o", "h", "l", "c", "atr", "vr"))
    out = []
    for ob in M.find_obs(df, True, True):
        t = M.first_touch(h, l, ob, True, shift)
        if t is None or t + 1 >= len(df):
            continue
        lo, hi = ob["lo"] + shift * ob["atr"], ob["hi"] + shift * ob["atr"]
        if c[t] < lo:
            continue
        k, m = ob["k"], ob["m"]
        rng_ = h[k] - l[k]
        wick = (min(o[k], c[k]) - l[k]) / rng_ if rng_ > 0 else 0.0
        w60h, w60l = h[max(0, k - 59):k + 1].max(), l[max(0, k - 59):k + 1].min()
        out.append({"t": t, "lo": lo, "hi": hi, "k": k, "m": m, "w_atr": (hi - lo) / ob["atr"], "wick": wick,
                    "low_half": 0.5 * (lo + hi) <= 0.5 * (w60h + w60l), "age": t - m, "vr": vr[t],
                    "c1": bool(c[t] > ctx["ma50"][t] and ctx["ma50"][t] > ctx["ma50_5"][t]),
                    "c2": bool(ctx["idx_c"][t] > ctx["idx_ma50"][t]),
                    "c3": bool(ctx["ret20"][t] > ctx["idx_ret20"][t])})
    return out


def pass_filter(key: str, r: dict) -> bool:
    if key == "B0":
        return True
    if key == "C1":
        return r["c1"]
    if key == "C2":
        return bool(r["c2"])
    if key == "C3":
        return bool(r["c3"])
    if key == "Q1":
        return 3 <= r["age"] <= 20
    if key == "Q2":
        return r["w_atr"] <= 1.5
    if key == "Q4":
        return r["wick"] >= 0.35
    if key == "Q5":
        return r["low_half"]
    if key == "T2":
        return bool(r["vr"] < 0.8)
    raise KeyError(key)


def fvg_candidates(df: pd.DataFrame, obs_bull: list[dict]) -> tuple[list[dict], list[dict]]:
    """F1/F2/F3 (FVG tăng) và F4 (FVG giảm bị đẩy lùi)."""
    h, l, c, a = (df[k].to_numpy(float) for k in ("h", "l", "c", "atr"))
    n = len(df)
    buy, sell = [], []
    for f in M.fvg_events(h, l, a):
        mid = f["i"]
        conf = mid + 1                      # nến 3 đóng → biết FVG
        size_atr = (f["hi"] - f["lo"]) / a[mid - 1] if a[mid - 1] > 1e-9 else 0.0
        # nến 4 (phiên kế sau nến 3) chưa chạm vùng: FVG tăng Low nến 4 > mép trên; FVG giảm High nến 4 < mép dưới
        clean = bool((l[mid + 2] > f["hi"]) if f["up"] else (h[mid + 2] < f["lo"])) if mid + 2 < n else False
        armed = False
        for t in range(conf + 1, min(conf + M.FVG_LIFE, n - 2) + 1):
            if f["up"]:
                if armed and l[t] <= f["hi"]:
                    if c[t] >= f["lo"]:
                        near = False
                        for ob in obs_bull:
                            if ob["m"] < t <= ob["m"] + M.LIFE and ob["lo"] <= f["hi"] + 0.5 * a[t] \
                                    and ob["hi"] >= f["lo"] - 0.5 * a[t] and not (c[ob["m"] + 1:t + 1] < ob["lo"]).any():
                                near = True
                                break
                        buy.append({"t": t, "lo": f["lo"], "hi": f["hi"], "size": size_atr, "near_ob": near, "clean": clean})
                    break
                if l[t] > f["hi"]:
                    armed = True
                if l[t] <= f["lo"]:        # lấp kín trước khi chạm đúng luật
                    break
            else:
                if armed and h[t] >= f["lo"]:
                    if c[t] < f["hi"]:
                        sell.append({"t": t, "lo": f["lo"], "hi": f["hi"], "size": size_atr})
                    break
                if h[t] < f["lo"]:
                    armed = True
                if h[t] >= f["hi"]:
                    break
    return buy, sell


def dedup_sig(items: list[dict]) -> list[dict]:
    items = sorted({r["t"]: r for r in items}.values(), key=lambda r: r["t"])
    out, last = [], -10**9
    for r in items:
        if r["t"] - last >= M.DEDUP:
            out.append(r)
            last = r["t"]
    return out


# ============================================================================== đo
def summarize_R(rows: list[dict]) -> dict:
    """rows: mỗi tín hiệu có R, win, base_R, base_win, year, symbol. Trả thống kê một nhóm."""
    if not rows:
        return {"n": 0}
    R = np.array([r["R"] for r in rows])
    W = np.array([r["win"] for r in rows], float)
    bR = np.array([r["base_R"] for r in rows])
    bW = np.array([r["base_win"] for r in rows])
    by = {}
    for r in rows:
        by.setdefault(r["year"], []).append(r["R"] - r["base_R"])
    yrs = {int(y): [round(float(np.mean(v)), 3), len(v)] for y, v in by.items() if len(v) >= 5}
    return {"n": len(rows), "R": float(R.mean()), "base_R": float(bR.mean()), "win": float(W.mean()),
            "base_win": float(bW.mean()), "years_pos": sum(1 for v in yrs.values() if v[0] > 0),
            "years": len(yrs), "by_year": yrs}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    global N_PERM
    hist = json.loads(M.HIST.read_text(encoding="utf-8"))["bars"]
    syms = sorted(s for s in hist if s != M.INDEX)
    if a.quick:
        syms, N_PERM = syms[:6], 60
    idx_df = M.base_frame(hist[M.INDEX])[["d", "c"]] if M.INDEX in hist else None
    log(f"{len(syms)} mã, chỉ số {'có' if idx_df is not None else 'KHÔNG'}")

    frames, per_sym = [], {}
    for sym in syms:
        df = M.base_frame(hist[sym])
        ctx = ctx_arrays(df, idx_df)
        pools = Pools(df)
        obs_b = M.find_obs(df, True, True)
        cands = {0.0: ob_candidates(df, ctx, 0.0), M.FAKE: ob_candidates(df, ctx, M.FAKE)}
        fb, fs = fvg_candidates(df, obs_b)
        per_sym[sym] = {"df": df, "pools": pools, "cands": cands, "fvg_buy": fb, "fvg_sell": fs}
        x = df[["d", "touch"] + [f"net{H}" for H in M.HS]].copy()
        x["symbol"] = sym
        frames.append(x)
        log(f"  {sym}: {len(cands[0.0])} chạm OB, {len(fb)} FVG mua, {len(fs)} FVG bán")
    F = pd.concat(frames, ignore_index=True)
    F["year"] = F["d"].dt.year
    E = F[(F["year"] >= M.FROM_YEAR) & F["net20"].notna()].copy()
    bm = M.bench(E)
    tb = float(E["touch"].dropna().mean())

    # ---------- gom tín hiệu theo biến thể
    sig: dict[str, list[dict]] = {k: [] for k in VARIANTS}
    fake: dict[str, list[dict]] = {k: [] for k in OB_VARS}
    for sym, S in per_sym.items():
        df, pools = S["df"], S["pools"]
        o, h, l, c, at = (df[k].to_numpy(float) for k in ("o", "h", "l", "c", "atr"))
        year_of = df["d"].dt.year.to_numpy()

        def make(r: dict, lo: float, tkey: int) -> dict | None:
            t = r["t"]
            if year_of[t] < M.FROM_YEAR or t + MAX_BARS + 1 >= len(df):
                return None
            entry = o[t + 1]
            stop = lo - STOP_PAD * at[t]
            risk = entry - stop
            xe = risk / at[t]
            if risk <= 0 or xe < 0.4 or xe > 6:
                return None
            ret, R = sim_core(o, h, l, c, np.array([t]), np.array([risk]))
            pr, pw = pools.pool(year_of[t], xe)
            if pr is None:
                return None
            return {"symbol": sym, "t": t, "year": int(year_of[t]), "R": float(R[0]), "win": bool(ret[0] > 0),
                    "base_R": float(pr.mean()), "base_win": float(pw.mean()), "pool": pr, "size": r.get("size"), "clean": r.get("clean"),
                    "net": {H: (float(df[f"net{H}"].iloc[t]) if not np.isnan(df[f"net{H}"].iloc[t]) else None)
                            for H in M.HS}, "touch": float(df["touch"].iloc[t]) if not np.isnan(df["touch"].iloc[t]) else None}

        for shift, store in ((0.0, sig), (M.FAKE, fake)):
            for key in OB_VARS:
                rs = dedup_sig([r for r in S["cands"][shift] if pass_filter(key, r)])
                for r in rs:
                    x = make(r, r["lo"], 0)
                    if x:
                        store[key].append(x)
        for key in FVG_VARS:
            rs = S["fvg_buy"]
            if key == "F2":
                rs = [r for r in rs if r["near_ob"]]
            if key == "F3":
                rs = [r for r in rs if r["size"] >= 1.0]
            for r in dedup_sig(rs):
                x = make(r, r["lo"], 0)
                if x:
                    sig[key].append(x)
        for r in dedup_sig(S["fvg_sell"]):
            t = r["t"]
            if year_of[t] >= M.FROM_YEAR and t + 21 < len(df):
                sig["F4"].append({"symbol": sym, "t": t, "year": int(year_of[t]),
                                  "net": {H: (None if np.isnan(df[f"net{H}"].iloc[t]) else float(df[f"net{H}"].iloc[t]))
                                          for H in M.HS},
                                  "touch": None if np.isnan(df["touch"].iloc[t]) else float(df["touch"].iloc[t])})

    # ---------- kiểm tái lập H1 của lab cũ (không lọc dừng lỗ): n ≈ 1.332, ex10 ≈ −0,41 %
    chk = []
    for sym, S in per_sym.items():
        df = S["df"]
        for r in dedup_sig(S["cands"][0.0]):
            t = r["t"]
            y = int(df["d"].dt.year.iloc[t])
            n20 = df["net20"].iloc[t]
            if y >= M.FROM_YEAR and not np.isnan(n20):
                chk.append({"year": y, "touch": df["touch"].iloc[t], **{f"net{H}": df[f"net{H}"].iloc[t] for H in M.HS}})
    chk = pd.DataFrame(chk)
    h1chk = M.stats(chk, bm, 10, "MUA", tb)
    log(f"kiểm H1: n={h1chk['n']} ex10={h1chk['ex']:+.2%} (lab cũ: 1332, −0,41 %)")

    # ---------- thống kê cổng A (giữ 10 phiên, y hệt lab cũ) + cổng B (R)
    def to_hold_df(rows: list[dict]) -> pd.DataFrame:
        d = pd.DataFrame([{"year": r["year"], "touch": r["touch"], **{f"net{H}": r["net"][H] for H in M.HS}} for r in rows])
        return d

    res: dict = {"meta": {"symbols": syms, "last_day": max(r[-1][0] for r in hist.values()), "train": [M.FROM_YEAR, TRAIN_END],
                          "test": [TRAIN_END + 1, 2026], "stop_pad": STOP_PAD, "rr": RR, "max_bars": MAX_BARS,
                          "n_perm": N_PERM, "seed": SEED, "bench": {H: float(E[f"net{H}"].mean()) for H in M.HS},
                          "touch_base": tb},
                 "check_h1": {"n": h1chk["n"], "ex": h1chk["ex"], "years_win": h1chk["years_win"], "years": h1chk["years"]},
                 "variants": {}}
    split = {"all": lambda y: True, "train": lambda y: y <= TRAIN_END, "test": lambda y: y > TRAIN_END}

    perm_z: dict[str, np.ndarray] = {}
    z_actual: dict[str, float] = {}
    for key, (desc, side) in VARIANTS.items():
        rows = sig[key]
        v: dict = {"desc": desc, "side": side}
        if rows:
            hd = to_hold_df(rows)
            v["hold"] = {H: M.stats(hd, bm, H, side, tb) for H in M.HS}
            v["gate_a"] = bool(M.gate(v["hold"][10], side))
        else:
            v["hold"], v["gate_a"] = {}, False
        if side == "MUA":
            v["R"] = {sp: summarize_R([r for r in rows if fn(r["year"])]) for sp, fn in split.items()}
            test_rows = [r for r in rows if r["year"] > TRAIN_END]
            if len(test_rows) >= 10:
                mu = float(np.mean([r["pool"].mean() for r in test_rows]))
                act = float(np.mean([r["R"] for r in test_rows]))
                sims = np.empty(N_PERM)
                for p in range(N_PERM):
                    sims[p] = np.mean([r["pool"][int(rng.random() * len(r["pool"]))] for r in test_rows])
                sd = float(sims.std()) or 1e-9
                perm_z[key] = (sims - sims.mean()) / sd
                z_actual[key] = (act - mu) / sd
                v["z_test"] = z_actual[key]
            if key in fake:
                v["fake_R"] = {sp: summarize_R([r for r in fake[key] if fn(r["year"])]) for sp, fn in split.items()}
            # tập trung theo mã
            if test_rows:
                cnt: dict[str, int] = {}
                for r in test_rows:
                    cnt[r["symbol"]] = cnt.get(r["symbol"], 0) + 1
                top = max(cnt, key=cnt.get)
                rest = [r for r in test_rows if r["symbol"] != top]
                v["top_symbol"] = {"symbol": top, "share": cnt[top] / len(test_rows),
                                   "R_rest": float(np.mean([r["R"] for r in rest])) if rest else None,
                                   "base_rest": float(np.mean([r["base_R"] for r in rest])) if rest else None}
        res["variants"][key] = v
        log(f"{key:3s} n={len(rows):5d} " + (f"gateA={'✓' if v['gate_a'] else '·'} "
            f"ex10={v['hold'][10].get('ex', 0):+.2%}" if v["hold"] else ""))

    # ---------- max-z hiệu chỉnh số lần thử (chỉ các biến thể MUA có đủ mẫu)
    keys = [k for k in perm_z]
    thr = None
    if keys:
        mx = np.max(np.vstack([perm_z[k] for k in keys]), axis=0)
        thr = float(np.percentile(mx, 95))
    res["maxz_threshold"] = thr
    res["maxz_keys"] = keys
    for key, v in res["variants"].items():
        if v["side"] != "MUA":
            continue
        t = v.get("R", {}).get("test", {})
        z = z_actual.get(key)
        checks = {}
        if t.get("n", 0) > 0:
            checks = {
                f"n test ≥ {MIN_N_TEST}": t["n"] >= MIN_N_TEST,
                "R TB > nền ngẫu nhiên": t["R"] > t["base_R"],
                "thắng > nền ngẫu nhiên": t["win"] > t["base_win"],
                "z vượt max-z 95 %": bool(z is not None and thr is not None and z > thr),
            }
            if key in fake:   # FVG đứng riêng không có vùng giả → nền ngẫu nhiên cùng khoảng dừng lỗ đã là đối chứng
                fk = v.get("fake_R", {}).get("test", {})
                checks["vùng giả +2 ATR kém hơn"] = bool(fk.get("n", 0) > 0 and fk["R"] < t["R"])
            ts = v.get("top_symbol")
            checks["bỏ mã nhiều nhất vẫn > nền"] = bool(ts and ts["R_rest"] is not None and ts["R_rest"] > ts["base_rest"])
        v["gate_b_checks"] = checks
        v["gate_b"] = bool(checks) and all(checks.values())
        v["pass"] = bool(v["gate_b"] and v.get("gate_a"))
    # ---------- PHÂN TÍCH MÔ TẢ SAU KHI XEM KẾT QUẢ (post-hoc, KHÔNG dùng để qua cổng): F1 theo độ lớn FVG
    ex = []
    for lab, lo_, hi_ in (("0,5–1 ATR", 0.5, 1.0), ("1–1,5 ATR", 1.0, 1.5), ("1,5–2,5 ATR", 1.5, 2.5), ("≥ 2,5 ATR", 2.5, 99)):
        g = [r for r in sig["F1"] if r.get("size") is not None and lo_ <= r["size"] < hi_]
        row = {"label": lab}
        for sp, fn in split.items():
            sm = summarize_R([r for r in g if fn(r["year"])])
            row[sp] = {k: sm.get(k) for k in ("n", "R", "base_R", "win", "base_win", "years_pos", "years")}
        ex.append(row)
    res["explore_f1_size"] = ex
    # ---------- post-hoc: điều kiện "nến 4 chưa chạm vùng" (người dùng đề xuất 10/10/2026, không thuộc 12 biến thể khoá trước)
    exc = []
    for lab, base_f in (("F1 · mọi FVG tăng", lambda r: True), ("F3 · FVG ≥ 1 ATR", lambda r: r.get("size") is not None and r["size"] >= 1.0)):
        for tag, cf in (("tất cả", lambda r: True), ("nến 4 chưa chạm vùng", lambda r: bool(r.get("clean"))),
                        ("nến 4 đã chạm vùng", lambda r: not r.get("clean"))):
            g = [r for r in sig["F1"] if base_f(r) and cf(r)]
            row = {"label": f"{lab} — {tag}"}
            for sp, fn in split.items():
                sm = summarize_R([r for r in g if fn(r["year"])])
                row[sp] = {k: sm.get(k) for k in ("n", "R", "base_R", "win", "base_win", "years_pos", "years")}
            exc.append(row)
    res["explore_clean"] = exc
    f4 = res["variants"]["F4"]
    f4["pass"] = bool(f4.get("gate_a"))
    OUT.write_text(json.dumps(res, ensure_ascii=False, default=float), encoding="utf-8")
    log(f"max-z 95 % = {thr}; ghi {OUT.name}")
    for key, v in res["variants"].items():
        t = v.get("R", {}).get("test", {})
        tr = v.get("R", {}).get("train", {})
        print(f"{key:3s} train n={tr.get('n', 0):4d} R {tr.get('R', 0):+.3f}/{tr.get('base_R', 0):+.3f} thắng "
              f"{tr.get('win', 0):.0%}/{tr.get('base_win', 0):.0%} | test n={t.get('n', 0):4d} R {t.get('R', 0):+.3f}/"
              f"{t.get('base_R', 0):+.3f} thắng {t.get('win', 0):.0%}/{t.get('base_win', 0):.0%} z={z_actual.get(key)} "
              f"A={'✓' if v.get('gate_a') else '·'} B={'✓' if v.get('gate_b') else '·'} {'★QUA' if v.get('pass') else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
