# Confluence — OB × Order Flow × Volume Profile (bản chạy online)

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

## Cài lên điện thoại (PWA "Confluence")
- Logo "Ba dòng chảy hợp lại": xanh dương (OB/cầu), tím (Volume Profile), vàng (dòng tiền) nhập vào một chấm sáng. Vector ở
  `web/icons/logo.svg`; PNG vẽ bằng `scripts/make_icons.py` (cần Pillow, chạy trên máy dev rồi commit PNG):
  `"c:\Claude code\candle-radar\venv\Scripts\python" scripts\make_icons.py`.
- `web/` (manifest, sw.js, icons) được `run.py` chép vào `site/` cạnh trang. Nút vàng "⬇ Cài app xuống điện thoại" ở đầu trang
  (chỉ hiện khi Chrome cho cài); tab Cách đọc có hộp "Cài app" kèm cách cài tay (Chrome ⋮ → Cài đặt ứng dụng; iPhone Safari → Chia sẻ → Thêm vào MH chính).
- Đẩy code lên `main` (web/, src/, run.py…) → workflow tự dựng lại ngay.

## Tiêu chí "OB chỉ dùng một lần" (16/10/2026)
OB đã dùng = sau lần chạm đầu, phiên đầu tiên giá bật hẳn ra khỏi vùng (OB tăng Low > đỉnh; OB giảm High < đáy) → ẩn như OB thủng,
không còn là vùng ở thẻ 15'. Chi tiết và số liệu trước/sau: README của lab `confluence-flow-lab`. Cảnh báo thẻ ngày không đổi.

## OB bình thường phải có imbalance (16/10/2026)
OB bình thường = OB cũ (đỏ→xanh, BOS, đẩy ≥ 1,5 ATR) + có FVG hoặc Volume Imbalance trong nhịp đẩy (nến k … m+2). Chi tiết, số liệu trước/sau:
README của lab. `src/confluence-flow-lab/data/daily.json`, `alert_stats.json` đã đo lại theo định nghĩa mới; `daily_w60.json`, `*_v1x2.json` là biến thể cũ không có imbalance.

## 19/10/2026 — nhãn LQ trên thẻ nến ngày
Vá từ lab (người dùng đã duyệt bản lab): `src/confluence-flow-lab/lq.py` (luật Sweep Lab: LQ mua L1/L2/✓L3, LQ bán B1/B2/✓B3/Δ B4),
`build.py` trả `d.lq`, `template.html` có ô "Nhãn LQ" (mặc định bật), chú giải và mục giải thích ở tab Cách đọc. Δ đọc
`src/cvd-candle-lab/data/bars.json` do run.py dựng. Luật chưa qua cổng thống kê.
