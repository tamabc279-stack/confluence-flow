"""Tick thật order-flow-live (data/raw/ticks-<ngày>.tar) → data/bars.json.

Mỗi mã-phiên: tóm tắt ngày + nến 5' khớp liên tục (bỏ ATO/ATC khỏi delta, nhưng giữ giá ATC làm giá đóng).
Dùng lại flow/ticks.py của order-flow-live (chỉ đọc, import theo đường dẫn) để delta/cá mập khớp app.

Chạy: ../order-flow-live/venv/Scripts/python build.py
"""
from __future__ import annotations

import gzip
import json
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "order-flow-live"))
from flow.ticks import session_bars  # noqa: E402

RAW, DAYS, OUT = HERE / "data" / "raw", HERE / "data" / "days", HERE / "data" / "bars.json"


def unpack(data: bytes) -> list[dict]:
    doc = json.loads(gzip.decompress(data).decode("utf-8"))
    return [{"date": doc["date"], **dict(zip(doc["fields"], row))} for row in doc["ticks"]]


def minute(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def main() -> None:
    out: dict[str, dict] = {}
    for tar_path in sorted(RAW.glob("ticks-*.tar")):
        day = tar_path.stem[len("ticks-"):]
        index = json.loads((DAYS / f"{day}.json").read_text(encoding="utf-8"))["symbols"]
        with tarfile.open(tar_path) as tar:
            for m in tar.getmembers():
                sym = Path(m.name).name.split(".")[0]
                ticks = unpack(tar.extractfile(m).read())
                if not ticks or ticks[-1]["date"] != day:
                    continue
                bars = session_bars(ticks)
                cont = [b for b in bars if not b["auction"]]
                if not cont:
                    continue
                prices = [t["price"] for t in ticks]
                val = sum(t["price"] * t["vol"] for t in ticks) / 1e6  # tỷ đồng (giá nghìn × cp)
                rec = {
                    "o": ticks[0]["price"], "h": max(prices), "l": min(prices), "c": ticks[-1]["price"],
                    "vol": sum(t["vol"] for t in ticks), "val": round(val, 3),
                    "buy": sum(b["buy"] for b in bars), "sell": sum(b["sell"] for b in bars),
                    "bb": sum(b["bb"] for b in bars), "bs": sum(b["bs"] for b in bars),
                    "no_side": not any(b["buy"] or b["sell"] for b in bars),
                    # nến 5': [phút, o, h, l, c, mua CĐ, bán CĐ, mua lớn, bán lớn, x]
                    "b5": [[minute(b["t"]), b["o"], b["h"], b["l"], b["c"], b["buy"], b["sell"], b["bb"], b["bs"], b["x"]]
                           for b in cont],
                }
                s = out.setdefault(sym, {"ex": (index.get(sym) or {}).get("ex", "HOSE"), "days": {}})
                s["days"][day] = rec
        print(day, "xong", sum(1 for s in out.values() if day in s["days"]), "mã")
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print("ghi", OUT, round(OUT.stat().st_size / 1e6, 1), "MB")


if __name__ == "__main__":
    main()
