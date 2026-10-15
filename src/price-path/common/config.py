"""Phần cấu hình tối thiểu mà dnse.py cần (chép từ price-path/common/config.py, bỏ dotenv/VAPID)."""
from __future__ import annotations

import os
from datetime import timedelta, timezone

TZ = timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "30"))
DNSE_BASE = os.getenv("DNSE_BASE", "https://services.entrade.com.vn/chart-api/v2/ohlcs")
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}
