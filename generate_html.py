# -*- coding: utf-8 -*-
"""
data/products.json を読み込み docs/index.html を生成する
使い方: python generate_html.py
"""

import io
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

JST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).parent
PRODUCTS_FILE = BASE_DIR / "data" / "products.json"
DOCS_DIR = BASE_DIR / "docs"
OUTPUT_FILE = DOCS_DIR / "index.html"


def parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def fmt(s: str, fmt_str: str = "%Y/%m/%d %H:%M") -> str:
    dt = parse_dt(s)
    return dt.strftime(fmt_str) if dt else "—"


def duration(start: str, end: str | None) -> str:
    s = parse_dt(start)
    if not s:
        return ""
    e = parse_dt(end) if end else datetime.now(JST)
    delta = e - s
    days, secs = delta.days, delta.seconds
    hours = secs // 3600
    if days >= 1:
        return f"{days}日{hours}時間"
    return f"{hours}時間{(secs % 3600) // 60}分"


def product_card(p: dict, available: bool) -> str:
    badge_class = "badge-available" if available else "badge-ended"
    badge_text = "掲載中" if available else "掲載終了"

    periods_html = ""
    for i, period in enumerate(p.get("periods", []), 1):
        end_str = fmt(period["end"]) if period["end"] else '<span class="ongoing">現在も掲載中</span>'
        dur = duration(period["start"], period["end"])
        periods_html += f"""
        <div class="period">
          <span class="period-label">期間 #{i}</span>
          <span class="period-range">{fmt(period['start'])} ～ {end_str}</span>
          <span class="period-dur">（{dur}）</span>
        </div>"""

    url = p.get("url", "")
    name_html = (
        f'<a href="{url}" target="_blank" rel="noopener">{p["name"]}</a>'
        if url else p["name"]
    )

    price_html = f'<span class="price">{p["price_text"]}</span>' if p.get("price_text") else ""

    return f"""
    <div class="card {"card-available" if available else "card-ended"}">
      <div class="card-header">
        <div class="card-title">{name_html}</div>
        <span class="badge {badge_class}">{badge_text}</span>
      </div>
      <div class="card-body">
        <div class="meta">
          <span class="part-number">型番: {p['part_number']}</span>
          {price_html}
        </div>
        <div class="first-seen">初掲載: {fmt(p['first_seen'])}</div>
        <div class="periods">{periods_html}</div>
      </div>
    </div>"""


def generate(data: dict) -> str:
    products = data.get("products", {})
    history = data.get("scrape_history", [])

    last_updated = fmt(history[-1]["timestamp"]) if history else "—"
    total_scrapes = len(history)

    available = sorted(
        [p for p in products.values() if p["is_available"]],
        key=lambda x: x.get("price", 0),
    )
    ended = sorted(
        [p for p in products.values() if not p["is_available"]],
        key=lambda x: x.get("last_seen", ""),
        reverse=True,
    )

    available_cards = "".join(product_card(p, True) for p in available)
    ended_cards = "".join(product_card(p, False) for p in ended)

    ended_section = f"""
    <section>
      <h2 class="section-title ended-title">掲載終了 <span class="count">{len(ended)}</span></h2>
      <div class="grid">{ended_cards}</div>
    </section>""" if ended else ""

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Apple 整備済 iPhone 掲載履歴</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif;
      background: #f5f5f7;
      color: #1d1d1f;
      min-height: 100vh;
    }}

    header {{
      background: #000;
      color: #fff;
      padding: 20px 24px;
      display: flex;
      align-items: center;
      gap: 16px;
    }}
    header svg {{ flex-shrink: 0; }}
    header h1 {{ font-size: 1.25rem; font-weight: 600; }}
    header .meta {{
      margin-left: auto;
      font-size: 0.75rem;
      color: #a1a1a6;
      text-align: right;
      line-height: 1.6;
    }}

    main {{ max-width: 960px; margin: 0 auto; padding: 32px 16px; }}

    .section-title {{
      font-size: 1.1rem;
      font-weight: 700;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .available-title {{ color: #1d1d1f; }}
    .ended-title {{ color: #6e6e73; margin-top: 40px; }}
    .count {{
      background: #e8e8ed;
      color: #6e6e73;
      font-size: 0.75rem;
      font-weight: 600;
      border-radius: 99px;
      padding: 2px 8px;
    }}

    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 16px;
    }}

    .card {{
      background: #fff;
      border-radius: 12px;
      padding: 18px;
      box-shadow: 0 1px 4px rgba(0,0,0,.08);
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    .card-ended {{ opacity: .65; }}

    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 8px;
    }}
    .card-title {{
      font-size: 0.92rem;
      font-weight: 600;
      line-height: 1.4;
    }}
    .card-title a {{
      color: inherit;
      text-decoration: none;
    }}
    .card-title a:hover {{ text-decoration: underline; color: #0071e3; }}

    .badge {{
      flex-shrink: 0;
      font-size: 0.7rem;
      font-weight: 600;
      border-radius: 6px;
      padding: 2px 7px;
    }}
    .badge-available {{ background: #d1f0da; color: #1a7f37; }}
    .badge-ended {{ background: #e8e8ed; color: #6e6e73; }}

    .card-body {{ display: flex; flex-direction: column; gap: 6px; }}

    .meta {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .part-number {{ font-size: 0.75rem; color: #6e6e73; font-family: monospace; }}
    .price {{ font-size: 1rem; font-weight: 700; color: #1d1d1f; }}

    .first-seen {{ font-size: 0.75rem; color: #6e6e73; }}

    .periods {{ display: flex; flex-direction: column; gap: 4px; margin-top: 2px; }}
    .period {{ font-size: 0.75rem; color: #3a3a3c; background: #f5f5f7; border-radius: 6px; padding: 5px 8px; }}
    .period-label {{ font-weight: 600; margin-right: 4px; color: #6e6e73; }}
    .period-range {{ }}
    .period-dur {{ color: #6e6e73; margin-left: 4px; }}
    .ongoing {{ color: #1a7f37; font-weight: 600; }}

    footer {{
      text-align: center;
      padding: 32px 16px;
      font-size: 0.75rem;
      color: #a1a1a6;
    }}
  </style>
</head>
<body>
  <header>
    <svg width="22" height="22" viewBox="0 0 814 1000" fill="white">
      <path d="M788.1 340.9c-5.8 4.5-108.2 62.2-108.2 190.5 0 148.4 130.3 200.9 134.2 202.2-.6 3.2-20.7 71.9-68.7 141.9-42.8 61.6-87.5 123.1-155.5 123.1s-85.5-39.5-164-39.5c-76 0-103.7 40.8-165.9 40.8s-105-37.3-155.5-127.4C46.7 790.7 0 663 0 541.8c0-207.5 135.4-317.3 269-317.3 71 0 130.5 46.4 174.5 46.4 42.8 0 109.5-49 192.7-49 31.3 0 135.4 3.1 200.7 103.3zM549.5 95.3c26.7-33.6 46-79.5 46-125.4 0-6.4-.6-12.9-1.9-18.1-44.7 1.6-97.8 29.9-130.5 70.5-24.8 28.3-47.4 74.2-47.4 120.8 0 7 1.3 13.9 1.9 16.2 2.6.4 6.4.6 10.2.6 40.2 0 89.2-26.7 121.7-64.6z"/>
    </svg>
    <h1>整備済 iPhone 掲載履歴</h1>
    <div class="meta">
      最終更新: {last_updated}<br>
      スクレイプ回数: {total_scrapes}回
    </div>
  </header>

  <main>
    <section>
      <h2 class="section-title available-title">現在掲載中 <span class="count">{len(available)}</span></h2>
      <div class="grid">{available_cards if available_cards else '<p style="color:#6e6e73">現在掲載中の商品はありません</p>'}</div>
    </section>
    {ended_section}
  </main>

  <footer>
    データソース: <a href="https://www.apple.com/jp/shop/refurbished/iphone" target="_blank">Apple 整備済製品 iPhone</a>
    &nbsp;|&nbsp; 自動更新: 1日4回（0・6・12・18時 JST）
  </footer>
</body>
</html>"""


def main():
    if not PRODUCTS_FILE.exists():
        print("データファイルがありません。先に scraper.py を実行してください。", file=sys.stderr)
        sys.exit(1)

    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    html = generate(data)

    DOCS_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"生成完了: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
