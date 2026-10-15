"""Tầng C — tick thật (cvd-candle-lab bars.json, nạp thêm phiên bằng tar Release; 10 phiên tới 13/10) × vùng OB/VP từ nến ngày → data/tick.json

  "c:\\Claude code\\price-path\\venv\\Scripts\\python" m_tick.py

Sự kiện = nến 15' lần ĐẦU tiên trong phiên vào một vùng (đi từ ngoài vào), vùng tính từ nến ngày TỚI HÔM TRƯỚC:
  OB cơ bản còn sống (≤ 60 phiên, chưa đóng cửa thủng) + POC/VAL/VAH profile VP_W phiên (40). Hướng theo phía tiếp cận:
  từ trên xuống = vùng cầu (mua): OB tăng, POC, VAL;  từ dưới lên = vùng cung (bán): OB giảm, POC, VAH.
Ba điểm, nhị phân (README):
  P hợp lưu vị trí = OB chồng mức VP (dung sai 0,25 ATR ngày) hoặc mức VP nằm trong/sát OB cùng phía
  F dòng tiền: mua = delta nến ≥ +20 % KL hoặc (CVD cá mập phiên > 0 khi giá chạm đáy phiên);
               bán = hấp thụ mua (delta ≥ +30 %, đóng nửa dưới) hoặc (CVD cá mập phiên < 0 khi giá chạm đỉnh phiên)
  K kích hoạt: mua = nến xanh, bóng chạm vùng, đóng cửa ≥ đáy vùng; bán = nến đỏ, chạm vùng, đóng cửa ≤ đỉnh vùng
Lợi suất = vượt rổ cùng ngày + cùng mốc 15' (cvd-candle-lab.measure.evaluate, cổng cũ). Cá mập = lệnh ≥ 500 tr + cá mập ẩn.
Chính (khoá trước): C1 = P∧F∧K mua, C2 = P∧F∧K bán, tại T+1. Mọi ô khác chỉ mô tả.
"""
from __future__ import annotations

import json
import random
import statistics as st
import sys

import numpy as np

from layers import FAKE, HERE, LAG, M, ROOT, TOL, VO, VP_W, VPM, _load

sys.path.insert(0, str(ROOT / "cvd-candle-lab"))
CV = _load("cvdm", ROOT / "cvd-candle-lab" / "measure.py")

DAILY = HERE / "data" / "daily"      # làm mới bằng fetch_daily.py (nến ngày DNSE 400 phiên)
OUT = HERE / "data" / "tick.json"
LIFE = 60
RNG = random.Random(20261012)


# ----------------------------------------------------------------------------- vùng từ nến ngày (tới hôm trước)
def zones_for(sym: str, day: str, shift: float = 0.0) -> list[dict]:
    rows = json.loads((DAILY / f"{sym}.json").read_text(encoding="utf-8"))
    rows = [r for r in rows if r[0] < day]
    if len(rows) < 80:
        return []
    df = M.base_frame(rows)
    n = len(df)
    h, l, c, a = (df[k].to_numpy(float) for k in ("h", "l", "c", "atr"))
    atr = float(a[-1])
    lv = VPM.rolling_levels(df, VP_W, "T").iloc[-1]
    poc, val, vah = float(lv["poc"]), float(lv["val"]), float(lv["vah"])
    fv = M.fvg_events(h, l, a)
    obs = []
    for bull in (True, False):
        for ob in M.find_obs(df, bull, True):
            if n - 1 - ob["m"] > LIFE or n - 1 - ob["m"] < LAG:
                continue
            if bull and (c[ob["m"] + 1:] < ob["lo"]).any():
                continue
            if not bull and (c[ob["m"] + 1:] > ob["hi"]).any():
                continue
            f = VO.flags(df, ob, fv, bull)
            obs.append({"bull": bull, "lo": ob["lo"] + shift * atr, "hi": ob["hi"] + shift * atr, "valid": f["valid"],
                        "m": str(df["d"].iloc[ob["m"]].date())})
    tol = TOL * atr
    lev = {"poc": poc + shift * atr, "val": val + shift * atr, "vah": vah + shift * atr}
    out = []
    for ob in obs:
        k = ("poc", "val") if ob["bull"] else ("poc", "vah")
        p = any(VPM_overlap(ob, lev[x], tol) for x in k)
        out.append({"type": "OB", "role": "buy" if ob["bull"] else "sell", "lo": ob["lo"], "hi": ob["hi"], "P": p,
                    "valid": ob["valid"], "m": ob["m"]})
    for name, x in lev.items():
        if np.isnan(x):
            continue
        for role, bull in (("buy", True), ("sell", False)):
            if name == ("vah" if bull else "val"):
                continue          # VAH chỉ là cung, VAL chỉ là cầu; POC cả hai
            near = any(o["bull"] == bull and o["lo"] - tol <= x <= o["hi"] + tol for o in obs)
            out.append({"type": name.upper(), "role": role, "lo": x, "hi": x, "P": near, "valid": False, "m": None})
    return out


def VPM_overlap(ob: dict, lvl: float, tol: float) -> bool:
    return bool(not np.isnan(lvl) and ob["lo"] - tol <= lvl <= ob["hi"] + tol)


# ----------------------------------------------------------------------------- sự kiện 15'
def events(mk, shift: float = 0.0, prev_close: dict | None = None) -> list[dict]:
    ev = []
    zc: dict[tuple, list] = {}
    for s in mk.uni:
        for d in mk.days:
            b = mk.b15.get((s, d))
            if not b:
                continue
            key = (s, d)
            if key not in zc:
                try:
                    zc[key] = zones_for(s, d, shift)
                except FileNotFoundError:
                    zc[key] = []
            zones = zc[key]
            if not zones:
                continue
            i = mk.days.index(d)
            prev = mk.raw[s]["days"].get(mk.days[i - 1]) if i > 0 else None
            pc = prev["c"] if prev else None
            seen = set()
            cvw = 0
            day_lo, day_hi = float("inf"), float("-inf")
            for m in [x for x in CV.SLOTS if x in b]:
                x = b[m]
                vol = x["buy"] + x["sell"]
                cvw += x["bb"] - x["bs"]
                day_lo, day_hi = min(day_lo, x["l"]), max(day_hi, x["h"])
                if pc is not None and vol > 0 and m < CV.SLOTS[-1]:
                    rng = x["h"] - x["l"]
                    clv = (x["c"] - x["l"]) / rng if rng > 0 else 0.5
                    dr = (x["buy"] - x["sell"]) / vol
                    for side in ("buy", "sell"):
                        hit = []
                        for zi, z in enumerate(zones):
                            if z["role"] != side or (zi, side) in seen:
                                continue
                            if side == "buy" and pc > z["hi"] and x["l"] <= z["hi"]:
                                hit.append(zi)
                            if side == "sell" and pc < z["lo"] and x["h"] >= z["lo"]:
                                hit.append(zi)
                        if not hit:
                            continue
                        for zi in hit:
                            seen.add((zi, side))
                        zz = [zones[zi] for zi in hit]
                        Pf = any(z["P"] for z in zz)
                        if side == "buy":
                            F = dr >= 0.2 or (cvw > 0 and x["l"] <= day_lo)
                            K = x["c"] > x["o"] and x["c"] >= min(z["lo"] for z in zz)
                        else:
                            F = (dr >= 0.3 and clv <= 0.5) or (cvw < 0 and x["h"] >= day_hi)
                            K = x["c"] < x["o"] and x["c"] <= max(z["hi"] for z in zz)
                        ev.append({"s": s, "d": d, "m": m, "side": side, "P": bool(Pf), "F": bool(F), "K": bool(K),
                                   "types": sorted({z["type"] for z in zz}), "lo": min(z["lo"] for z in zz),
                                   "hi": max(z["hi"] for z in zz), "valid": any(z["valid"] for z in zz)})
                pc = x["c"]
    return ev


def subset(ev: list[dict], side: str, p: bool | None, f: bool | None, k: bool | None) -> list[tuple]:
    out = []
    for e in ev:
        if e["side"] != side:
            continue
        if (p is not None and e["P"] != p) or (f is not None and e["F"] != f) or (k is not None and e["K"] != k):
            continue
        out.append((e["s"], e["d"], e["m"]))
    return out


def main() -> int:
    raw, days, uni = CV.load("kingstock")
    chain = CV.add_hidden(raw, days, uni)       # cá mập tổng hợp (lệnh ≥ 500 tr + cá mập ẩn)
    mk = CV.Market(raw, days, uni)
    tb = st.median(CV.tick_size(raw[s]["days"][days[-1]]["c"], raw[s]["ex"]) / raw[s]["days"][days[-1]]["c"] * 1e4
                   for s in uni if days[-1] in raw[s]["days"])
    print(f"{len(uni)} mã, {len(days)} phiên ({days[0]}..{days[-1]}), bước giá trung vị {tb:.1f} bps", file=sys.stderr)
    ev = events(mk)
    ev_fake = events(mk, shift=FAKE)
    print(f"sự kiện: {len(ev)} (mua {sum(e['side'] == 'buy' for e in ev)}, bán {sum(e['side'] == 'sell' for e in ev)}); giả {len(ev_fake)}",
          file=sys.stderr)
    cells = {"Z": (None, None, None), "P": (True, None, None), "F": (None, True, None), "K": (None, None, True),
             "PF": (True, True, None), "PK": (True, None, True), "FK": (None, True, True), "PFK": (True, True, True),
             "notP_FK": (False, True, True)}
    res = {"meta": {"days": days, "n_sym": len(uni), "tick_bps": round(tb, 1), "n_events": len(ev), "tol_atr": TOL, "fake_atr": FAKE,
                    "n_tested": 2, "chain_pairs": len(chain)}, "cells": {}, "fake": {}, "events": ev}
    print("ô        phía  T+  n   mean_bps  giả97.5  hit  ngày   QUA")
    for side, want in (("buy", +1), ("sell", -1)):
        for name, (p, f, k) in cells.items():
            for kk in (1, 2):
                r = CV.evaluate(mk, f"{side} {name}", subset(ev, side, p, f, k), want, kk, tb)
                res["cells"][f"{side}|{name}|{kk}"] = r
                print(f"{name:8s} {side:4s}  T+{kk} {r['n']:4d} {r.get('mean_bps', '-'):>8} {r.get('fake975', '-'):>8} "
                      f"{r.get('hit', '-')} {r.get('days_same', '-'):>5}  {'QUA' if r['pass_'] else 'trượt'}")
        # vùng giả: cùng bộ P∧F∧K nhưng vùng dịch +2 ATR
        for kk in (1, 2):
            r = CV.evaluate(mk, f"{side} PFK giả", subset(ev_fake, side, True, True, True), want, kk, tb)
            res["fake"][f"{side}|PFK|{kk}"] = r
            print(f"PFK giả  {side:4s}  T+{kk} {r['n']:4d} {r.get('mean_bps', '-'):>8} {r.get('fake975', '-'):>8} {r.get('hit', '-')}")
    plc = [(RNG.choice(uni), RNG.choice(days), RNG.choice(CV.SLOTS[:-1])) for _ in range(400)]
    res["placebo"] = [CV.evaluate(mk, "Giả dược", plc, w, kk, tb) for w in (1, -1) for kk in (1, 2)]
    for p in res["placebo"]:
        print("giả dược", p["want"], "T+", p["k"], p.get("mean_bps"), "QUA" if p["pass_"] else "trượt")
    OUT.write_text(json.dumps(res, ensure_ascii=False, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
