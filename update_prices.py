#!/usr/bin/env python3
"""Đọc giá dầu Diesel Petrolimex (Vùng 1, Vùng 2) và cập nhật data.json.
- Chỉ thêm một kỳ giá mới khi giá khác với kỳ gần nhất trong data.json.
- Luôn cập nhật dataThrough = hôm nay (giờ Việt Nam) khi đọc nguồn thành công.
- Lỗi (không đọc được / số bất thường) -> thoát mã 1, KHÔNG ghi file, GitHub sẽ báo Action thất bại.
"""
import json, re, sys, time, urllib.request
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from pathlib import Path

URL = "https://webgia.com/gia-xang-dau/petrolimex/"
DATA = Path(__file__).resolve().parent / "data.json"
ICT = timezone(timedelta(hours=7))
ROWS = {"do 0,05s": "do", "do 0,001s": "do001"}   # từ khoá tên dòng -> khoá dữ liệu


class RowParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def to_price(text):
    digits = re.sub(r"\D", "", text)
    if not digits:
        raise ValueError(f"Không đọc được số từ ô: {text!r}")
    v = int(digits)
    if not 10_000 <= v <= 100_000:
        raise ValueError(f"Giá bất thường: {v}")
    return v


def parse(html):
    p = RowParser()
    p.feed(html)
    found = {}
    for row in p.rows:
        if len(row) < 3:
            continue
        name = row[0].lower()
        for needle, key in ROWS.items():
            if needle in name and key not in found:
                found[key] = (to_price(row[1]), to_price(row[2]))
    missing = [k for k in ROWS.values() if k not in found]
    if missing:
        raise ValueError(f"Không tìm thấy dòng giá: {missing}")
    return {
        "v1": {k: found[k][0] for k in ("do", "do001")},
        "v2": {k: found[k][1] for k in ("do", "do001")},
    }


def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (compatible; gia-dau-diesel-bot/1.0)",
                "Accept-Language": "vi,en;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"Không tải được {url}: {last}")


def changed(latest, new):
    for region in ("v1", "v2"):
        for k in ("do", "do001"):
            old = latest[region].get(k)
            if old is not None and old != new[region][k]:
                return True
    return False


def apply(data, new, now):
    """Trả về (data đã cập nhật, thông điệp)."""
    msg = "Giá không đổi."
    latest = data["periods"][-1]
    if changed(latest, new):
        start = now.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M")
        if start <= latest["from"]:
            start = (datetime.strptime(latest["from"], "%Y-%m-%dT%H:%M") + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M")
        data["periods"].append({"from": start, "v1": new["v1"], "v2": new["v2"]})
        msg = f"Kỳ giá mới từ {start}: {new}"
    data["dataThrough"] = now.date().isoformat()
    return data, msg


def main():
    new = parse(fetch(URL))
    data = json.loads(DATA.read_text(encoding="utf-8"))
    data, msg = apply(data, new, datetime.now(ICT))
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(msg)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        print("LỖI:", e, file=sys.stderr)
        sys.exit(1)
