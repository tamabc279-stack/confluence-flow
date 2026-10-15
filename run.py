"""Dựng trang Confluence Flow (OB × Order Flow × Volume Profile) tự động trên GitHub Actions.

Bản chạy online của lab `c:\\Claude code\\confluence-flow-lab`. Chỉ ĐỌC dữ liệu công khai của các app đang chạy, không ghi gì ngược lại:
  nến ngày      DNSE (400 ngày lịch, tải lại toàn bộ vì DNSE điều chỉnh giá lịch sử muộn)
  delta ngày    Pages app order-flow (tamabc906-coder/order-flow)
  tick          Release t<ngày> của phongthietke-lgtm/order-flow-live (+ mục lục data/days/<ngày>.json)
  cá mập ẩn     Pages app price-path (data/algo/<ngày>.json)

Hai lượt mỗi ngày (cách A, người dùng chọn 15/10/2026):
  17:00  nến ngày đã có phiên hôm nay, tick chưa có → dựng phần nến ngày, thẻ 15' giữ tới phiên tick gần nhất
  19:00–23:00 (30 phút/lần)  tick hôm nay xuất hiện → dựng đầy đủ; đã dựng rồi thì thoát ngay

  python run.py            # bình thường (thoát 0 nếu nguồn chưa đủ hoặc đã dựng)
  python run.py --force    # dựng lại dù status.json nói đã dựng

Kết quả: site/index.html (workflow đăng lên Pages) + status.json (workflow commit). Ghi `publish=true` vào GITHUB_OUTPUT khi có trang mới.
Cổng 0 lệch → thoát 1, không đăng (trang cũ trên Pages giữ nguyên).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        s.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
LAB = SRC / "confluence-flow-lab"
CVD = SRC / "cvd-candle-lab"
SITE = ROOT / "site"
STATUS = ROOT / "status.json"
TZ = timezone(timedelta(hours=7))

# 39 mã của lab (danh sách nến ngày; giữ cố định như lab — đổi danh mục thì sửa ở đây và chép lại watchlist.json)
SYMS = ("ACB AGR BID CEO CII CTG DCM DGC DPR DXG EIB FPT GAS GMD GVR HCM HPG KBC LPB MBB MBS MSB PLX PVD PVS "
        "SHB SHS SSI STB SZC TCB TCH TPB VCB VCI VDS VIB VIX VPB").split()
GATE = ("SSI", "TCB", "HPG", "VCB", "TCH", "FPT")   # cổng 0: tick phải khớp app order-flow + DNSE
MIN_READY = 35                                      # số mã tối thiểu phải có phiên mới (phòng 1–2 mã tạm ngừng giao dịch)
FIRST_ALGO = "2026-09-25"                           # lab cộng cá mập ẩn phiên này vào CVD cá mập ngày

REPO = "phongthietke-lgtm/order-flow-live"
REL_API = f"https://api.github.com/repos/{REPO}/releases?per_page=100&page={{}}"
TAR = f"https://github.com/{REPO}/releases/download/t{{d}}/ticks-{{d}}.tar"
DAYS = f"https://raw.githubusercontent.com/{REPO}/main/data/days/{{d}}.json"
ALGO = "https://tamabc906-coder.github.io/price-path/data/algo/{}.json"
OF = "https://tamabc906-coder.github.io/order-flow/data/daily/{}.json"


def log(msg: str) -> None:
    print(f"[{datetime.now(TZ):%H:%M:%S}] {msg}", flush=True)


def get(url: str, bust: bool = False, api: bool = False) -> bytes | None:
    """Tải có thử lại (Pages thỉnh thoảng cắt kết nối). 404 → None ngay."""
    hdr = {"User-Agent": "confluence-flow"}
    if api and os.environ.get("GITHUB_TOKEN"):
        hdr["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"   # tránh giới hạn 60 lần/giờ của API ẩn danh
    for k in range(4):
        try:
            u = f"{url}{'&' if '?' in url else '?'}t={int(time.time())}" if bust else url
            with urllib.request.urlopen(urllib.request.Request(u, headers=hdr), timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            log(f"thử lại {k + 1} {url} {exc}")
        except Exception as exc:  # noqa: BLE001
            log(f"thử lại {k + 1} {url} {exc}")
        time.sleep(3 * (k + 1))
    raise RuntimeError(f"không tải được {url}")


# ----------------------------------------------------------------------------- nguồn
def fetch_daily() -> str:
    """Nến ngày DNSE → src/confluence-flow-lab/data/daily/<MÃ>.json (đúng định dạng fetch_daily.py của lab). Trả phiên mới nhất."""
    sys.path.insert(0, str(SRC / "price-path"))
    from common.dnse import DnseClient  # noqa: E402

    out = LAB / "data" / "daily"
    out.mkdir(parents=True, exist_ok=True)
    last = {}
    with DnseClient() as c:
        for s in SYMS:
            d = c.daily(s, 400)
            if not d:
                raise RuntimeError(f"DNSE không trả nến {s}")
            (out / f"{s}.json").write_text(
                json.dumps([[str(b["d"]), b["o"], b["h"], b["l"], b["c"], b["v"]] for b in d], separators=(",", ":")), encoding="utf-8")
            last[s] = str(d[-1]["d"])
    day = max(last.values())
    n = sum(v == day for v in last.values())
    log(f"nến ngày DNSE: phiên mới nhất {day} ({n}/{len(SYMS)} mã)")
    if n < MIN_READY:
        raise SystemExit(0)   # nguồn đang chốt dở → lượt sau
    return day


def fetch_of(day: str) -> bool:
    out = LAB / "data" / "of"
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for s in SYMS:
        data = get(OF.format(s), bust=True)
        if data is None:
            log(f"order-flow KHÔNG CÓ {s}")
            continue
        (out / f"{s}.json").write_bytes(data)
        n += any(x.get("d") == day for x in json.loads(data)["days"])
    log(f"delta order-flow: {n}/{len(SYMS)} mã có phiên {day}")
    return n >= MIN_READY


def fetch_ticks() -> list[str]:
    """Release tick → src/cvd-candle-lab/data/raw (chỉ tải tar còn thiếu; workflow cache giữ tar cũ) + mục lục days/. Trả các phiên tick."""
    raw, idx = CVD / "data" / "raw", CVD / "data" / "days"
    raw.mkdir(parents=True, exist_ok=True)
    idx.mkdir(parents=True, exist_ok=True)
    tags, page = [], 1
    while True:
        rel = json.loads(get(REL_API.format(page), api=True) or b"[]")
        tags += [r["tag_name"] for r in rel if r["tag_name"].startswith("t20") and not r.get("draft")]
        if len(rel) < 100:
            break
        page += 1
    days = sorted(t[1:] for t in tags)
    for d in days:
        tp, ip = raw / f"ticks-{d}.tar", idx / f"{d}.json"
        if not tp.exists():
            data = get(TAR.format(d=d))
            if data is None:
                log(f"Release t{d} không có tar — bỏ phiên")
                continue
            tp.write_bytes(data)
            log(f"tải tick {d} {len(data) / 1e6:.1f} MB")
        if not ip.exists():
            data = get(DAYS.format(d=d))
            if data is None:
                tp.unlink()
                log(f"thiếu mục lục {d} — bỏ phiên, lượt sau thử lại")
                continue
            ip.write_bytes(data)
    have = sorted(p.stem[len("ticks-"):] for p in raw.glob("ticks-*.tar") if (idx / f"{p.stem[len('ticks-'):]}.json").exists())
    log(f"tick: {len(have)} phiên ({have[0]} → {have[-1]})")
    return have


def fetch_algo(days: list[str]) -> None:
    out = CVD / "data" / "algo"
    out.mkdir(parents=True, exist_ok=True)
    for d in [FIRST_ALGO] + days:
        p = out / f"{d}.json"
        if p.exists():
            continue
        data = get(ALGO.format(d), bust=True)
        if data is None:
            log(f"price-path không có cá mập ẩn {d} (phiên đó chỉ tính lệnh lớn, như lab)")
            continue
        p.write_bytes(data)


# ----------------------------------------------------------------------------- dựng + kiểm
def step(script: Path, built: str) -> None:
    log(f"== {script.parent.name}/{script.name}")
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "CF_BUILT": built}
    r = subprocess.run([sys.executable, str(script)], cwd=script.parent, env=env)
    if r.returncode:
        raise SystemExit(r.returncode)


def gate0(tday: str) -> None:
    """Phiên tick cuối: delta tick = delta app order-flow, giá đóng tick = DNSE, KL tick = KL DNSE (như lab làm tay)."""
    bars = json.loads((CVD / "data" / "bars.json").read_text(encoding="utf-8"))
    bad = []
    for s in GATE:
        r = bars[s]["days"].get(tday)
        of = {x["d"]: x for x in json.loads((LAB / "data" / "of" / f"{s}.json").read_text(encoding="utf-8"))["days"]}.get(tday)
        dl = next((x for x in json.loads((LAB / "data" / "daily" / f"{s}.json").read_text(encoding="utf-8")) if x[0] == tday), None)
        if r is None or of is None or dl is None:
            bad.append(f"{s}: thiếu dữ liệu (tick {r is not None}, order-flow {of is not None}, DNSE {dl is not None})")
            continue
        chk = [("delta", r["buy"] - r["sell"], of.get("delta")), ("giá đóng", r["c"], dl[4]), ("KL", r["vol"], dl[5])]
        for name, a, b in chk:
            if b is None or abs(a - b) > 1e-6 * max(1, abs(b)):
                bad.append(f"{s} {name}: tick {a} ≠ {b}")
    if bad:
        log("CỔNG 0 LỆCH — không đăng trang:\n  " + "\n  ".join(bad))
        raise SystemExit(1)
    log(f"cổng 0: {len(GATE)}/{len(GATE)} mã khớp ở phiên {tday}")


def main() -> int:
    force = "--force" in sys.argv
    now = datetime.now(TZ)
    status = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else {}

    day = fetch_daily()
    if not fetch_of(day):
        log("delta order-flow chưa có phiên mới — lượt sau")
        return 0
    ticks = fetch_ticks()
    tday = ticks[-1]
    if not force and status.get("daily") == day and status.get("tick") == tday:
        log(f"đã dựng nến ngày {day} + tick {tday} — không có gì mới")
        return 0
    fetch_algo(ticks)

    built = f"{now:%d/%m/%Y %H:%M}"
    step(CVD / "build.py", built)
    gate0(tday)
    step(LAB / "m_tick.py", built)
    step(LAB / "build.py", built)

    SITE.mkdir(exist_ok=True)
    shutil.copyfile(LAB / "index.html", SITE / "index.html")
    alerts = json.loads((LAB / "data" / "daily_alerts.json").read_text(encoding="utf-8"))
    tick = json.loads((LAB / "data" / "tick.json").read_text(encoding="utf-8"))
    new = {"daily": day, "tick": tday, "tick_days": len(ticks), "full": tday == day, "built": now.isoformat(timespec="seconds"),
           "touches": len(tick["events"]), "alert_stage": alerts["stage"]}
    STATUS.write_text(json.dumps(new, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    log(f"xong: nến ngày {day}, tick {tday} ({'đầy đủ' if new['full'] else 'chờ tick hôm nay'}), "
        f"{new['touches']} lần chạm vùng, {(SITE / 'index.html').stat().st_size / 1e6:.2f} MB")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"publish=true\nlabel={day} tick {tday}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
