"""Ba tầng dùng lại mã đã kiểm của lab khác (chỉ ĐỌC, import theo đường dẫn):
  V  Vị trí  : OB (order-block-lab/valid_ob.py, measure.py) ∩ Volume Profile (volume-profile-lab/measure.py)
  F  Dòng tiền: tick thật (cvd-candle-lab) — xem m_tick.py
  K  Kích hoạt: nến xác nhận
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]   # = src/ của repo confluence-flow (giữ cấu trúc thư mục như trên máy)
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "order-block-lab"))
import valid_ob as VO  # noqa: E402  (kéo theo measure, tune của order-block-lab)

M, TU = VO.M, VO.TU

# V1 (nến ★ mạnh): KL ngày m ≥ VOL_X × TB20. order-block-lab giữ 2,0; người dùng hạ xuống 1,2 trong lab này (14/10/2026).
# Ghi đè biến toàn cục của valid_ob (hàm flags() đọc VOL_X lúc gọi) — KHÔNG sửa file của order-block-lab. Phần "đóng cửa trong 10 % trên cùng" giữ nguyên.
VOL_X = 1.2
VO.VOL_X = VOL_X


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


VPM = _load("vpm", ROOT / "volume-profile-lab" / "measure.py")

VP_W = 40            # cửa sổ profile ngày (phiên); 13/10 đổi 60 → 40 theo yêu cầu người dùng (kết quả 60 giữ ở data/*_w60.json)
TOL = 0.25           # dung sai chồng vùng, ATR
FAKE = 2.0           # vùng giả: mức VP dịch + 2 ATR
LAG = 3              # chạm lại phải sau ★ + 3 (như valid_ob)


def vp_frame(df: pd.DataFrame, W: int = VP_W) -> pd.DataFrame:
    """POC/VAL/VAH profile W phiên TÍNH ĐẾN HÔM QUA (shift 1): tại t chỉ dùng thông tin đã biết."""
    return VPM.rolling_levels(df, W, "T")[["poc", "val", "vah"]].shift(1)


def overlap(lo: float, hi: float, lvl: float, tol: float) -> bool:
    return bool(not np.isnan(lvl) and lo - tol <= lvl <= hi + tol)


def vp_tags(ob: dict, L: pd.DataFrame, t: int, atr_t: float, bull: bool, shift: float = 0.0) -> dict:
    """OB chồng mức VP nào tại phiên t. Mua: POC/VAL (hỗ trợ). Bán: POC/VAH (kháng cự)."""
    tol = TOL * atr_t
    poc = L["poc"].iat[t] + shift * atr_t
    edge = (L["val"] if bull else L["vah"]).iat[t] + shift * atr_t
    p, e = overlap(ob["lo"], ob["hi"], poc, tol), overlap(ob["lo"], ob["hi"], edge, tol)
    return {"poc": p, "edge": e, "any": p or e}
