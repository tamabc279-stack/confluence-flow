# Confluence Flow — OB × Order Flow × Volume Profile (bản chạy online)

Trang: https://tamabc279-stack.github.io/confluence-flow/

Bản tự động của lab `c:\Claude code\confluence-flow-lab` (nghiên cứu, **không phải tín hiệu**: tầng A đo 10 năm 0/5 qua cổng,
tầng C chưa đủ mẫu). Không gửi thông báo. Chỉ ĐỌC dữ liệu công khai của các app đang chạy:

| Dữ liệu | Nguồn | Có lúc |
|---|---|---|
| Nến ngày 400 ngày lịch | DNSE | sau 15:00 |
| Delta ngày, lệnh lớn | Pages app order-flow | chiều |
| Cá mập ẩn | Pages app price-path `data/algo/` | ~15:40 |
| Tick từng lệnh | Release `t<ngày>` của `phongthietke-lgtm/order-flow-live` | ~19:00–22:00 |

## Lịch (GitHub Actions, T2–T6, giờ VN)
- **17:00** — dựng phần nến ngày của phiên hôm nay; thẻ 15' giữ tới phiên tick gần nhất (đầu trang ghi rõ).
- **19:00 → 23:00, 30 phút/lần** — khi tick hôm nay có → dựng đầy đủ; đã dựng thì thoát ngay.
- Bấm tay: Actions → build → Run workflow (`force = true` để dựng lại).

Mỗi lần dựng: `run.py` tải nguồn → `cvd-candle-lab/build.py` (tick → nến 5') → **cổng 0** (6 mã: delta tick = app order-flow,
giá đóng và KL tick = DNSE; lệch → không đăng) → `m_tick.py` → `build.py` → `site/index.html` lên Pages, `status.json` commit.

## Cấu trúc
`src/` giữ đúng tên thư mục như trên máy để code lab chép sang gần như nguyên vẹn:
- `src/confluence-flow-lab/` — `layers.py`, `m_tick.py`, `build.py`, `template.html`; `data/*.json` = kết quả đo 10 năm
  **đóng băng** (`m_daily.py`/`m_alert.py` cần `price-path/data/history.json`, không chạy ở đây).
- `src/order-block-lab/`, `src/volume-profile-lab/`, `src/cvd-candle-lab/` — module dùng chung của các lab.
- `src/order-flow-live/flow/ticks.py` — cách dựng nến/delta/cá mập từ tick, giống app order-flow.
- `src/price-path/common/dnse.py` — client DNSE.
- `src/cvd-candle-lab/data/algo/watchlist.json` — danh mục KingStock chụp từ lab (quyết định mã nào có thẻ 15').

Khác lab: đường dẫn tương đối; đầu trang ghi giờ dựng và "tick phiên … chưa có" khi chạy lượt 17:00.

## Lưu ý
- **Sửa lab trên máy KHÔNG tự cập nhật lên đây** — muốn đồng bộ thì chép lại file tương ứng vào `src/`.
- Đo lại 10 năm (~15/11, cuối 11/2026): chạy lab trên máy rồi chép `daily*.json`, `alert_stats*.json` vào `src/confluence-flow-lab/data/`.
- Đổi danh mục: sửa `SYMS` trong `run.py` và `watchlist.json`.
- Repo public: Actions và Pages miễn phí. Bật Pages: Settings → Pages → Source = **GitHub Actions**.

Chạy trên máy: `"c:\Claude code\price-path\venv\Scripts\python" run.py --force` → mở `site/index.html`.
