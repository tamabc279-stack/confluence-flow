"""OB tăng "hợp lệ" theo tiêu chí chuẩn rút ra từ ví dụ TCB 29,2–29,75 — CHỈ trong order-block-lab (10/10/2026).

    "c:\\Claude code\\price-path\\venv\\Scripts\\python" valid_ob.py   # → valid_ob.json + ob_valid.js

NỀN: OB tăng theo luật lab (nến k đỏ, k+1 xanh, ≤ 3 phiên có BOS và đóng cửa ≥ C[k] + 1,5 ATR14), ★ = phiên m.
HỢP LỆ (khoá trước khi chạy) khi đủ cả ba:
  V1 nến ★ mạnh: KL ngày m ≥ 2× TB20 (20 phiên trước) và đóng cửa ≥ Low + 0,9·(High − Low) của nến ★.
  V2 FVG hợp lưu: FVG tăng ≥ 1 ATR14 (ATR tại nến 1) do chính nhịp đẩy tạo ra (nến 2 của FVG ∈ [k+1, m+1]), chồng hoặc sát OB
     (≤ 0,5 ATR14[k]), và nến 4 chưa chạm vùng FVG (Low nến 4 > mép trên).
  V3 vùng hẹp: (High k − Low k) / ATR14[k] ≤ 1,5.
Không nhìn trước: hợp lệ chỉ biết tại nến 4 của FVG (≤ m+3). Mọi nhóm đo dùng cùng một quy tắc: lần chạm lại đầu tiên (luật lab:
giá rời hẳn vùng rồi quay lại, đóng cửa ≥ đáy vùng) phải xảy ra SAU phiên m+3, nếu không bỏ OB đó (kể cả OB không hợp lệ).
Lệnh: mua mở cửa phiên sau lần chạm, dừng lỗ = đáy vùng − 0,25 ATR, chốt 2R, tối đa 20 phiên, phí + thuế như lab; so với nền ngẫu nhiên
cùng mã, cùng năm, cùng khoảng dừng lỗ (tune.Pools). Chọn 2016–2021, kiểm 2022–2026.
Giả thuyết chính: DUY NHẤT nhóm "hợp lệ" ở giai đoạn kiểm (xáo 300 lần); các nhóm khác chỉ để mô tả.
"""
from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

import measure as M
import tune as TU

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8", errors="replace")

HERE = M.HERE
OUT = HERE / "valid_ob.json"
JS = HERE / "ob_valid.js"
VOL_X, CLOSE_POS, FVG_ATR, NEAR_ATR, MAX_W = 2.0, 0.90, 1.0, 0.5, 1.5
LAG = 3                      # chạm lại phải sau m + LAG
N_PERM = 300
rng = np.random.default_rng(20261010)


def flags(df: pd.DataFrame, ob: dict, fvgs: list[dict], bull: bool = True) -> dict:
    """bull=False: bản đối xứng cho OB giảm (V1 đóng cửa ★ trong 10 % DƯỚI cùng, V2 FVG giảm với nến 4 High < mép dưới, V3 như nhau)."""
    o, h, l, c, a, v, vr = (df[k].to_numpy(float) for k in ("o", "h", "l", "c", "atr", "v", "vr"))
    n = len(df)
    k, m = ob["k"], ob["m"]
    rg = h[m] - l[m]
    pos = (c[m] - l[m]) / rg if rg > 0 else 0.0
    f = {"vr": float(vr[m]) if not np.isnan(vr[m]) else None, "pos": float(pos), "w_atr": float((ob["hi"] - ob["lo"]) / a[k]),
         "fvg": None}
    f["v1"] = bool(f["vr"] is not None and f["vr"] >= VOL_X and (pos >= CLOSE_POS if bull else pos <= 1 - CLOSE_POS))
    f["v3"] = bool(f["w_atr"] <= MAX_W)
    f["v2"] = False
    for g in fvgs:
        if g["up"] != bull or not (k + 1 <= g["i"] <= m + 1) or g["i"] - 1 < 0 or g["i"] + 2 >= n:
            continue
        size = (g["hi"] - g["lo"]) / a[g["i"] - 1] if a[g["i"] - 1] > 1e-9 else 0.0
        near = ob["lo"] <= g["hi"] + NEAR_ATR * a[k] and ob["hi"] >= g["lo"] - NEAR_ATR * a[k]
        clean = (l[g["i"] + 2] > g["hi"]) if bull else (h[g["i"] + 2] < g["lo"])
        if size >= FVG_ATR and near and clean:
            f["v2"] = True
            f["fvg"] = {"lo": float(g["lo"]), "hi": float(g["hi"]), "size": float(size), "mid": int(g["i"])}
            break
    f["valid"] = bool(f["v1"] and f["v2"] and f["v3"])
    return f


def trade_row(S: dict, t: int, lo: float):
    df, pools = S["df"], S["pools"]
    o, h, l, c, a = (df[k].to_numpy(float) for k in ("o", "h", "l", "c", "atr"))
    n = len(df)
    y = int(df["d"].iloc[t].year)
    if y < M.FROM_YEAR or t + TU.MAX_BARS + 1 >= n or a[t] <= 1e-9:
        return None
    entry = o[t + 1]
    risk = entry - (lo - TU.STOP_PAD * a[t])
    xe = risk / a[t]
    if risk <= 0 or not (0.4 <= xe <= 6):
        return None
    ret, R = TU.sim_core(o, h, l, c, np.array([t]), np.array([risk]))
    pr, pw = pools.pool(y, xe)
    if pr is None:
        return None
    row = {"symbol": S["sym"], "t": t, "year": y, "R": float(R[0]), "win": bool(ret[0] > 0), "base_R": float(pr.mean()),
           "base_win": float(pw.mean()), "pool": pr}
    for H in M.HS:
        v = df[f"net{H}"].iloc[t]
        row[f"net{H}"] = None if np.isnan(v) else float(v)
    tc = df["touch"].iloc[t]
    row["touch"] = None if np.isnan(tc) else float(tc)
    return row


def main() -> int:
    hist = json.loads(M.HIST.read_text(encoding="utf-8"))["bars"]
    syms = sorted(s for s in hist if s != M.INDEX)
    S_all, frames = {}, []
    for sym in syms:
        df = M.base_frame(hist[sym])
        S_all[sym] = {"sym": sym, "df": df, "pools": TU.Pools(df)}
        x = df[["d", "touch"] + [f"net{H}" for H in M.HS]].copy()
        x["symbol"] = sym
        frames.append(x)
    F = pd.concat(frames, ignore_index=True)
    F["year"] = F["d"].dt.year
    E = F[(F["year"] >= M.FROM_YEAR) & F["net20"].notna()]
    bm = M.bench(E)
    tb = float(E["touch"].dropna().mean())

    groups = {k: [] for k in ("valid", "other", "no_v1", "no_v2", "no_v3", "v1", "v2", "v3", "all")}
    fake_valid, n_ob, n_flag = [], 0, {"v1": 0, "v2": 0, "v3": 0, "valid": 0}
    for sym, S in S_all.items():
        df = S["df"]
        h, l, c, a = (df[k].to_numpy(float) for k in ("h", "l", "c", "atr"))
        fv = M.fvg_events(h, l, a)
        for ob in M.find_obs(df, True, True):
            f = flags(df, ob, fv)
            if df["d"].iloc[ob["m"]].year >= M.FROM_YEAR:
                n_ob += 1
                for key in n_flag:
                    n_flag[key] += f[key]
            t = M.first_touch(h, l, ob, True)
            if t is not None and t > ob["m"] + LAG and c[t] >= ob["lo"]:
                r = trade_row(S, t, ob["lo"])
                if r:
                    r["flags"] = {k: f[k] for k in ("v1", "v2", "v3", "valid")}
                    groups["all"].append(r)
                    groups["valid" if f["valid"] else "other"].append(r)
                    if f["v2"] and f["v3"]:
                        groups["no_v1"].append(r)
                    if f["v1"] and f["v3"]:
                        groups["no_v2"].append(r)
                    if f["v1"] and f["v2"]:
                        groups["no_v3"].append(r)
                    for q in ("v1", "v2", "v3"):
                        if f[q]:
                            groups[q].append(r)
            if f["valid"]:      # vùng giả: cùng OB hợp lệ, vùng dịch +2 ATR
                tf = M.first_touch(h, l, ob, True, M.FAKE)
                lo_f = ob["lo"] + M.FAKE * ob["atr"]
                if tf is not None and tf > ob["m"] + LAG and c[tf] >= lo_f:
                    r = trade_row(S, tf, lo_f)
                    if r:
                        fake_valid.append(r)
    print(f"OB tăng (2016+): {n_ob}; V1 {n_flag['v1']}, V2 {n_flag['v2']}, V3 {n_flag['v3']}, hợp lệ {n_flag['valid']}", file=sys.stderr)

    split = {"all": lambda y: True, "train": lambda y: y <= TU.TRAIN_END, "test": lambda y: y > TU.TRAIN_END}

    def hold(rows):
        if not rows:
            return {}
        d = pd.DataFrame([{"year": r["year"], "touch": r["touch"], **{f"net{H}": r[f"net{H}"] for H in M.HS}} for r in rows])
        st10 = M.stats(d, bm, 10, "MUA", tb)
        st10["gate"] = bool(M.gate(st10, "MUA"))
        return st10

    res = {"meta": {"vol_x": VOL_X, "close_pos": CLOSE_POS, "fvg_atr": FVG_ATR, "near_atr": NEAR_ATR, "max_w_atr": MAX_W, "lag": LAG,
                    "n_perm": N_PERM, "last_day": max(r[-1][0] for r in hist.values()), "n_ob": n_ob, "flags": n_flag,
                    "bench": {H: float(E[f"net{H}"].mean()) for H in M.HS}},
           "groups": {}}
    labels = {"valid": "OB HỢP LỆ (đủ V1 + V2 + V3)", "other": "OB thường (không đủ 3)", "all": "Mọi OB (nền, chạm sau ★+3)",
              "no_v1": "Chỉ cần V2 + V3 (bỏ V1)", "no_v2": "Chỉ cần V1 + V3 (bỏ V2)", "no_v3": "Chỉ cần V1 + V2 (bỏ V3)",
              "v1": "Chỉ V1 nến ★ mạnh", "v2": "Chỉ V2 FVG hợp lưu", "v3": "Chỉ V3 vùng hẹp"}
    for key, rows in groups.items():
        res["groups"][key] = {"label": labels[key], "hold": hold(rows),
                              "R": {sp: TU.summarize_R([r for r in rows if fn(r["year"])]) for sp, fn in split.items()}}
    res["groups"]["fake"] = {"label": "Vùng giả: OB hợp lệ dịch +2 ATR", "hold": hold(fake_valid),
                             "R": {sp: TU.summarize_R([r for r in fake_valid if fn(r["year"])]) for sp, fn in split.items()}}

    # giả thuyết chính: OB hợp lệ ở giai đoạn kiểm — xáo ngày vào lệnh trong cùng mã-năm-khoảng dừng lỗ
    test = [r for r in groups["valid"] if r["year"] > TU.TRAIN_END]
    if len(test) >= 10:
        mu = float(np.mean([r["pool"].mean() for r in test]))
        act = float(np.mean([r["R"] for r in test]))
        sims = np.array([np.mean([r["pool"][int(rng.random() * len(r["pool"]))] for r in test]) for _ in range(N_PERM)])
        res["main"] = {"n": len(test), "R": act, "mu": mu, "z": float((act - mu) / (sims.std() or 1e-9)),
                       "p": float((sims >= act).mean())}
    # độ nhạy "nhìn trước": dịch lần chạm sớm hơn 1 phiên không được làm kết quả đẹp lên bất thường (kiểm tra, không báo cáo là kết quả)
    # (đã kiểm tay ở dưới bằng cách đọc tune/valid_ob, xem README)

    # ------------------------------------------------------------------ quét hôm nay + xuất cho biểu đồ (nến ngày DNSE tới phiên cuối)
    scan, js = [], {}
    for p in sorted((HERE / "data" / "daily").glob("*.json")):
        sym = p.stem
        df = M.base_frame(json.loads(p.read_text(encoding="utf-8")))
        n = len(df)
        o, h, l, c, a = (df[k].to_numpy(float) for k in ("o", "h", "l", "c", "atr"))
        dates = [str(x.date()) for x in df["d"]]
        fv = M.fvg_events(h, l, a)
        lst = []
        for bull in (True, False):
          for ob in M.find_obs(df, bull, True):
            f = flags(df, ob, fv, bull)
            if not f["valid"]:
                continue
            k, m = ob["k"], ob["m"]
            rec = {"bull": bull, "k": dates[k], "m": dates[m], "lo": round(float(ob["lo"]), 4), "hi": round(float(ob["hi"]), 4),
                   "vr": round(f["vr"], 2), "pos": round(f["pos"], 2), "w": round(f["w_atr"], 2),
                   "fvg": [round(f["fvg"]["lo"], 4), round(f["fvg"]["hi"], 4), round(f["fvg"]["size"], 2)]}
            lst.append(rec)
            broken = (c[m + 1:] < ob["lo"]).any() if bull else (c[m + 1:] > ob["hi"]).any()
            alive = n - 1 - m <= M.LIFE and not broken
            if alive:
                touched = bool((l[m + 1:] <= ob["hi"]).any()) if bull else bool((h[m + 1:] >= ob["lo"]).any())
                dist = 0.0 if ob["lo"] <= c[-1] <= ob["hi"] else min(abs(c[-1] - ob["lo"]), abs(c[-1] - ob["hi"]))
                scan.append({**rec, "symbol": sym, "age": n - 1 - m, "touched": touched, "in_zone": bool(ob["lo"] <= c[-1] <= ob["hi"]),
                             "close": float(c[-1]), "dist_pct": float(dist / c[-1]), "dist_atr": float(dist / a[-1]), "date": dates[-1]})
        if lst:
            js[sym] = lst
    res["scan"] = sorted(scan, key=lambda r: (r["dist_atr"], r["symbol"]))
    OUT.write_text(json.dumps(res, ensure_ascii=False, default=float), encoding="utf-8")
    JS.write_text("window.OB_VALID = " + json.dumps(js, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")

    f = lambda x, p=2: "—" if x is None else f"{x * 100:+.{p}f}%"
    print("nhóm".ljust(36), "n(tr/te)  hold10 ex  win | R test / nền  thắng test / nền")
    for key, g in res["groups"].items():
        tr, te = g["R"]["train"], g["R"]["test"]
        h10 = g["hold"]
        print(f"{g['label'][:35]:36s} {tr.get('n', 0):4d}/{te.get('n', 0):4d}  {f(h10.get('ex'))} {f(h10.get('win'), 0)}  gate={h10.get('gate')}"
              f" | {te.get('R', 0):+.3f}/{te.get('base_R', 0):+.3f}  {te.get('win', 0):.0%}/{te.get('base_win', 0):.0%}  train {tr.get('R', 0):+.3f}/{tr.get('base_R', 0):+.3f}")
    print("chính:", res.get("main"))
    print(f"quét: {len(scan)} OB hợp lệ còn sống; {sum(len(v) for v in js.values())} OB hợp lệ trên {len(js)} mã")
    for r in res["scan"][:12]:
        print(r["symbol"], r["lo"], r["hi"], "tuổi", r["age"], "chạm" if r["touched"] else "chưa", f"cách {r['dist_pct']*100:.1f}% ({r['dist_atr']:.1f}ATR)", "KL★", r["vr"], "pos", r["pos"], "w", r["w"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
