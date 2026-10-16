"""Dựng index.html: nến NGÀY + nến 15' cùng lúc, OB, Volume Profile, delta/CVD, mũi tên hợp lưu.

  "c:\\Claude code\\price-path\\venv\\Scripts\\python" build.py     (cần đã chạy m_daily.py và m_tick.py)

Chỉ ĐỌC dữ liệu lab khác. Dữ liệu nhúng thẳng vào trang (mở được bằng file://, không gọi mạng).
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

from layers import FAKE, HERE, LAG, M, ROOT, TOL, VO, VOL_X, VP_W, VPM, vp_frame, vp_tags
from m_tick import CV, DAILY, LIFE, zones_for
import hidden   # cvd-candle-lab/hidden.py (sys.path đã được m_tick thêm): cá mập ẩn của tab Cá mập ẩn (price-path)

SHOW_D = 40           # số nến ngày hiển thị (13/10: người dùng chỉ muốn 40 phiên)
OF = HERE / "data" / "of"
CVD_PCT = 0.15        # CVD nửa đầu phiên phải lệch ≥ 15 % KL phiên (người dùng chốt 13/10)
HALF_END = 11 * 60 + 30   # hết phiên sáng = hết "nửa đầu phiên"
POC_BAND = (0.25, 0.75)   # dải giữa OB (0 % = đáy, 100 % = đỉnh) mà POC phải nằm trong (người dùng chốt 13/10)
CLOSES: dict[str, dict[str, float]] = {}   # {mã: {ngày: đóng cửa}} để tính lợi suất sau cảnh báo


def r4(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), 4)


def profile_pack(lo, hi, tp, v, nb=40):
    edges, tot = VPM.profile(lo, hi, tp, v, "T", nb)
    poc, val, vah = VPM.levels(edges, tot)
    mid = 0.5 * (edges[:-1] + edges[1:])
    return {"p": [r4(x) for x in mid], "v": [round(float(x), 1) for x in tot], "poc": r4(poc), "val": r4(val), "vah": r4(vah)}


def flow_check(sym: str, date: str, bull: bool, kl: float, raw: dict, delta: dict) -> dict:
    """Dòng tiền của phiên test T — chỉ để gắn dấu ★ (KHÔNG quyết định cảnh báo; 14/10/2026).
    d_ok: delta ngày > 0 (BÁN: < 0).  c_ok: CVD (mua−bán chủ động cộng dồn, nến 5' khớp liên tục) chạm đáy ≤ −15 % KL trước 11:30
    (BÁN: đỉnh ≥ +15 % KL).  None = thiếu dữ liệu (delta ngày từ 18/09/2026, nến 5' từ 30/09/2026)."""
    d = delta.get(date) or {}
    day = (raw.get(sym) or {}).get("days", {}).get(date)
    dv = d.get("delta")
    if dv is None and day:
        dv = day["buy"] - day["sell"]
    out = {"kl": kl, "delta": dv, "dpct": None if dv is None or not kl else dv / kl, "cvd": None, "cpct": None, "d_ok": None, "c_ok": None}
    if dv is not None:
        out["d_ok"] = bool(dv > 0 if bull else dv < 0)
    if day:
        cum, ext = 0.0, 0.0
        for row in day["b5"]:
            if row[0] >= HALF_END:
                break
            cum += row[5] - row[6]
            ext = min(ext, cum) if bull else max(ext, cum)
        out["cvd"], out["cpct"] = ext, ext / kl if kl else None
        out["c_ok"] = bool((ext <= -CVD_PCT * kl) if bull else (ext >= CVD_PCT * kl))
    return out


def daily_pack(sym: str, raw: dict, HID: dict) -> dict:
    rows = json.loads((DAILY / f"{sym}.json").read_text(encoding="utf-8"))
    df = M.base_frame(rows)
    n = len(df)
    h, l, c, a, v = (df[k].to_numpy(float) for k in ("h", "l", "c", "atr", "v"))
    fv = M.fvg_events(h, l, a)
    L = vp_frame(df)      # POC/VAL/VAH profile VP_W phiên TÍNH ĐẾN HÔM QUA (shift 1): tại t chỉ dùng thông tin đã biết
    dates = [str(x.date()) for x in df["d"]]
    CLOSES[sym] = {dates[i]: float(c[i]) for i in range(n)}
    delta = {}
    p = OF / f"{sym}.json"
    if p.exists():
        for d in json.loads(p.read_text(encoding="utf-8"))["days"]:
            delta[d["d"]] = {"delta": d.get("delta"), "cvd": d.get("cvd"), "big": d.get("big"), "vw": d.get("vw"), "bb": d.get("bb"), "bs": d.get("bs")}
    cvd_day, cum = {}, 0.0                # CVD ngày = cộng dồn delta ngày thật (app order-flow) từ phiên đầu có dữ liệu (18/09/2026)
    for dd in sorted(delta):
        if delta[dd].get("delta") is not None:
            cum += delta[dd]["delta"]
            cvd_day[dd] = cum
    # CVD CÁ MẬP ngày = cộng dồn delta cá mập: lệnh lớn ≥ 500 tr (bb − bs của app order-flow, từ 18/09) + cá mập ẩn (Σ adj của hidden.py;
    # chỉ có phiên 25/09 và 30/09 → 13/10; phiên khác chỉ có lệnh lớn). Cờ hid = 1 nếu phiên đó đã cộng cá mập ẩn.
    wc_day, hid_day, wcum = {}, {}, 0.0
    for dd in sorted(delta):
        bbv, bsv = delta[dd].get("bb"), delta[dd].get("bs")
        if bbv is None or bsv is None:
            continue
        w = bbv - bsv
        hh = HID.get((sym, dd))
        if hh:
            w += sum(sh for _, sh in hh["adj"])
            hid_day[dd] = 1
        wcum += w
        wc_day[dd] = wcum
    i0 = max(0, n - SHOW_D)
    obs, marks, cands = [], [], []
    stage = {"valid_ob": 0, "touched": 0, "zone_ok": 0, "alert": 0, "has_data": 0, "star": 0}
    for bull in (True, False):
        for ob in M.find_obs(df, bull, True):
            f = VO.flags(df, ob, fv, bull)
            m = ob["m"]
            end = min(m + M.LIFE, n - 1)
            for j in range(m + 1, end + 1):
                if (bull and c[j] < ob["lo"]) or (not bull and c[j] > ob["hi"]):
                    end, broken = j, True
                    break
            else:
                broken = False
            t = M.first_touch(h, l, ob, bull)
            # "ĐÃ DÙNG" (16/10/2026, người dùng): sau lần chạm đầu, phiên đầu tiên giá RỜI HẲN vùng về phía nhịp (Low > đỉnh; OB giảm High < đáy)
            # → OB chết, các lần quay lại test sau bỏ qua. Thủng đáy trước khi bật ra thì vẫn là "thủng", không phải "đã dùng".
            used = False
            if t is not None:
                for u in range(t + 1, min(m + M.LIFE, n - 1) + 1):
                    if (l[u] > ob["hi"]) if bull else (h[u] < ob["lo"]):
                        if not broken or u < end:
                            end, used, broken = u, True, False
                        break
            marked = False
            stage["valid_ob"] += bool(f["valid"])
            if f["valid"] and t is not None and t > m + LAG:
                stage["touched"] += 1
                mid = (ob["lo"] + ob["hi"]) / 2
                still = not ((c[m + 1:t] < ob["lo"]).any() if bull else (c[m + 1:t] > ob["hi"]).any())
                zone_ok = still and ((mid <= l[t] <= ob["hi"] and c[t] >= mid) if bull else (ob["lo"] <= h[t] <= mid and c[t] <= mid))
                if zone_ok:
                    stage["zone_ok"] += 1
                    # điều kiện 6: POC (profile ngày VP_W phiên, tới hôm trước) nằm trong dải giữa 25–75 % chiều cao OB
                    b_lo, b_hi = ob["lo"] + POC_BAND[0] * (ob["hi"] - ob["lo"]), ob["lo"] + POC_BAND[1] * (ob["hi"] - ob["lo"])
                    poc = float(L["poc"].iat[t])
                    poc_ok = (not np.isnan(poc)) and b_lo <= poc <= b_hi
                    fl = flow_check(sym, dates[t], bull, float(v[t]), raw, delta)
                    star = fl["d_ok"] is True or fl["c_ok"] is True
                    st, why = ("alert", "") if poc_ok else ("miss", "POC ngoài dải giữa OB")   # cảnh báo = ①②③④ (chỉ giá)
                    if poc_ok:
                        stage["alert"] += 1
                        stage["has_data"] += fl["d_ok"] is not None or fl["c_ok"] is not None
                        stage["star"] += star
                    rec = {"s": sym, "d": dates[t], "bull": bull, "st": st, "why": why, "lo": r4(ob["lo"]), "hi": r4(ob["hi"]),
                           "mid": r4(mid), "px": r4(l[t] if bull else h[t]), "close": r4(c[t]), "delta": fl["delta"], "dpct": r4(fl["dpct"]),
                           "cvd": fl["cvd"], "cpct": r4(fl["cpct"]), "kl": int(v[t]), "poc": r4(poc), "poc_ok": bool(poc_ok),
                           "band": [r4(b_lo), r4(b_hi)], "d_ok": fl["d_ok"], "c_ok": fl["c_ok"], "star": bool(star), "_t": t}
                    cands.append(rec)
                    marked = marked or t >= i0
                    if t >= i0:
                        marks.append({**{k: rec[k] for k in ("bull", "st", "why", "lo", "hi", "mid", "px", "close", "delta", "dpct", "cvd", "cpct", "kl",
                                                              "poc", "poc_ok", "band", "d_ok", "c_ok", "star")}, "i": t - i0})
            if end < i0:
                continue
            obs.append({"bull": bull, "k": ob["k"] - i0, "m": m - i0, "end": end - i0, "lo": r4(ob["lo"]), "hi": r4(ob["hi"]),
                        "valid": f["valid"], "broken": broken, "used": used, "marked": marked})
    sw = slice(n - VP_W, n)
    tp = (df["h"] + df["l"] + df["c"]) / 3
    prof = profile_pack(df["l"].to_numpy(float)[sw], df["h"].to_numpy(float)[sw], tp.to_numpy(float)[sw],
                        df["v"].to_numpy(float)[sw])
    ma20 = df["v"].astype(float).shift(1).rolling(20).mean()     # TB20 của 20 phiên TRƯỚC, đúng cột `vr` của lab (tiêu chí V1)
    bars = [[dates[i], r4(df["o"].iat[i]), r4(df["h"].iat[i]), r4(df["l"].iat[i]), r4(df["c"].iat[i]), int(df["v"].iat[i]),
             (delta.get(dates[i]) or {}).get("delta"), (delta.get(dates[i]) or {}).get("big"),
             None if np.isnan(ma20.iat[i]) else int(round(ma20.iat[i])), cvd_day.get(dates[i]),
             wc_day.get(dates[i]), hid_day.get(dates[i], 0)] for i in range(i0, n)]
    return {"bars": bars, "obs": obs, "marks": marks, "vp": prof, "atr": r4(a[-1]), "last": dates[-1], "_cands": cands, "_stage": stage}


def tick_pack(mk, sym: str, events: list[dict]) -> dict:
    days = [d for d in mk.days if (sym, d) in mk.b15]
    out, zones, vwap, dp, cp = [], {}, [], {}, {}
    lo5, hi5, tp5, v5 = [], [], [], []
    for di, d in enumerate(days):
        b = mk.b15[(sym, d)]
        rec = mk.raw[sym]["days"][d]
        for s_ in [x for x in CV.SLOTS if x in b]:
            x = b[s_]
            out.append([di, s_, r4(x["o"]), r4(x["h"]), r4(x["l"]), r4(x["c"]), x["buy"], x["sell"], x["bb"], x["bs"]])
        pv = vv = 0.0
        d_lo, d_hi, d_tp, d_v = [], [], [], []
        for m_, o, h, l, c, buy, sell, bb, bs, _x in rec["b5"]:
            v = buy + sell
            lo5.append(l), hi5.append(h), tp5.append((h + l + c) / 3), v5.append(v)
            d_lo.append(l), d_hi.append(h), d_tp.append((h + l + c) / 3), d_v.append(v)
            pv += (h + l + c) / 3 * v
            vv += v
            vwap.append([di, m_, r4(pv / vv) if vv else None])
        if sum(d_v) > 0:     # profile RIÊNG phiên di (24 ô) và profile CỘNG DỒN 0..di (40 ô, như cột phải)
            dp[di] = profile_pack(np.array(d_lo), np.array(d_hi), np.array(d_tp), np.array(d_v, float), nb=24)
            cu = profile_pack(np.array(lo5), np.array(hi5), np.array(tp5), np.array(v5, float))
            cp[di] = {"poc": cu["poc"], "val": cu["val"], "vah": cu["vah"]}
        try:
            zs = zones_for(sym, d)
        except FileNotFoundError:
            zs = []
        zones[di] = [{"t": z["type"], "role": z["role"], "lo": r4(z["lo"]), "hi": r4(z["hi"]), "P": z["P"], "valid": z["valid"]} for z in zs]
    prof = profile_pack(np.array(lo5), np.array(hi5), np.array(tp5), np.array(v5, float)) if v5 else None
    dmap = {d: i for i, d in enumerate(days)}
    ev = [{"di": dmap[e["d"]], "m": e["m"], "side": e["side"], "P": e["P"], "F": e["F"], "K": e["K"], "types": e["types"],
           "lo": r4(e["lo"]), "hi": r4(e["hi"]), "valid": e["valid"]} for e in events if e["s"] == sym and e["d"] in dmap]
    if prof and cp:      # cộng dồn ngày cuối phải trùng profile 10 phiên ở cột phải
        last = cp[max(cp)]
        assert (last["poc"], last["val"], last["vah"]) == (prof["poc"], prof["val"], prof["vah"]), (sym, last, prof["poc"])
    return {"days": days, "bars": out, "zones": zones, "vwap": vwap, "vp": prof, "ev": ev, "dp": dp, "cp": cp}


def main() -> int:
    daily = json.loads((HERE / "data" / "daily.json").read_text(encoding="utf-8"))
    tick = json.loads((HERE / "data" / "tick.json").read_text(encoding="utf-8"))
    raw, days, uni = CV.load("kingstock")
    HID = hidden.load(["2026-09-25"] + days)       # cá mập ẩn theo (mã, ngày)
    CV.add_hidden(raw, days, uni)
    mk = CV.Market(raw, days, uni)
    syms = sorted(p.stem for p in DAILY.glob("*.json"))
    w60 = json.loads((HERE / "data" / "daily_w60.json").read_text(encoding="utf-8"))
    data = {"w60": {"bull": w60["bull"], "marginal": w60["marginal"], "vp_w": w60["meta"]["vp_w"]}, "daily": daily, "tick": {k: v for k, v in tick.items() if k != "events"}, "sym": {}, "scan": []}
    last = days[-1]
    for sym in syms:
        d = daily_pack(sym, raw, HID)
        t = tick_pack(mk, sym, tick["events"]) if sym in uni else None
        data["sym"][sym] = {"d": d, "t": t}
        sc = [e for e in (t["ev"] if t else []) if t["days"][e["di"]] == last]
        best = max(sc, key=lambda e: e["P"] + e["F"] + e["K"], default=None)
        valid_alive = [o for o in d["obs"] if o["valid"] and not o["broken"] and not o["used"] and o["end"] >= len(d["bars"]) - 1]
        data["scan"].append({"s": sym, "score": (best["P"] + best["F"] + best["K"]) if best else 0, "side": best["side"] if best else None,
                             "n_ev": len(sc), "valid": len(valid_alive), "tick": sym in uni, "last": d["bars"][-1][4],
                             "chg": r4(d["bars"][-1][4] / d["bars"][-2][4] - 1)})
    data["scan"].sort(key=lambda r: (-r["score"], -r["valid"], r["s"]))
    # tổng hợp cảnh báo thẻ ngày: đếm theo giai đoạn + lợi suất sau cảnh báo (đóng cửa T → T+k, trừ trung bình các mã cùng kỳ)
    items, stage = [], {k: 0 for k in ("valid_ob", "touched", "zone_ok", "alert", "has_data", "star")}
    for sym in syms:
        for k in stage:
            stage[k] += data["sym"][sym]["d"]["_stage"][k]
        items += data["sym"][sym]["d"]["_cands"]
    all_syms = list(CLOSES)

    def fwd(sym, date, k):
        ds = sorted(CLOSES[sym]); i = ds.index(date) if date in CLOSES[sym] else None
        return None if i is None or i + k >= len(ds) else CLOSES[sym][ds[i + k]] / CLOSES[sym][date] - 1, (ds[i + k] if i is not None and i + k < len(ds) else None)

    for it in items:
        if it["st"] != "alert":
            continue
        for k in (1, 3, 5):
            r, d2 = fwd(it["s"], it["d"], k)
            if r is None:
                it[f"r{k}"] = None
                continue
            peers = [x for x in (fwd(o, it["d"], k)[0] if it["d"] in CLOSES[o] else None for o in all_syms) if x is not None]
            it[f"r{k}"] = r4(r - sum(peers) / len(peers)) if peers else None
    for it in items:
        it.pop("_t", None)
    for sym in syms:
        data["sym"][sym]["d"].pop("_cands"); data["sym"][sym]["d"].pop("_stage")
    items.sort(key=lambda r: (r["d"], r["s"]))
    sp = HERE / "data" / "alert_stats.json"
    data["astats"] = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else None
    # so sánh với bản V1 = 2× (đã sao lưu trước khi hạ ngưỡng)
    old = {}
    try:
        o_al = json.loads((HERE / "data" / "daily_alerts_v1x2.json").read_text(encoding="utf-8"))
        o_st = json.loads((HERE / "data" / "alert_stats_v1x2.json").read_text(encoding="utf-8"))
        o_dl = json.loads((HERE / "data" / "daily_v1x2.json").read_text(encoding="utf-8"))
        old = {"stage": o_al["stage"], "n_items": len(o_al["items"]), "groups": o_st["groups"], "tierA_valid": o_dl["bull"]["valid"], "vol_x": 2.0}
    except FileNotFoundError:
        pass
    data["v1old"] = old
    data["meta_v1"] = {"vol_x": VOL_X}
    data["alerts"] = {"items": items, "stage": stage, "cfg": {"cvd_pct": CVD_PCT, "half_end": HALF_END, "poc_band": list(POC_BAND), "vp_w": VP_W}}
    (HERE / "data" / "daily_alerts.json").write_text(json.dumps(data["alerts"], ensure_ascii=False), encoding="utf-8")
    print("cảnh báo thẻ ngày:", stage, "| chi tiết:", [(i["s"], i["d"], "MUA" if i["bull"] else "BÁN", i["st"]) for i in items if i["st"] == "alert"])
    data["meta"] = {"last_tick_day": last, "tick_days": days, "last_daily": data["sym"][syms[0]]["d"]["last"],
                    "slots": CV.SLOTS, "vp_w": VP_W, "tol": TOL, "fake": FAKE,
                    "built": os.environ.get("CF_BUILT", "")}   # giờ dựng (run.py đặt), hiện ở đầu trang
    tpl = (HERE / "template.html").read_text(encoding="utf-8")
    html = tpl.replace("{{VPW}}", str(VP_W)).replace("{{VOLX}}", f"{VOL_X:g}".replace(".", ",")).replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=float))
    (HERE / "index.html").write_text(html, encoding="utf-8")
    print("ghi index.html", round((HERE / "index.html").stat().st_size / 1e6, 2), "MB;", len(syms), "mã")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
