# -*- coding: utf-8 -*-
"""
Apple Japan 整備済 iPhone 掲載履歴ビューアー
使い方: python viewer.py
"""

import io
import json
import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))
DATA_DIR = Path(__file__).parent / "data"
PRODUCTS_FILE = DATA_DIR / "products.json"


def parse_dt(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def format_dt(s: str) -> str:
    dt = parse_dt(s)
    if dt is None:
        return "不明"
    return dt.strftime("%Y/%m/%d %H:%M")


def calc_duration(start: str, end: str | None) -> str:
    s = parse_dt(start)
    if s is None:
        return ""
    e = parse_dt(end) if end else datetime.now(JST)
    delta = e - s
    days = delta.days
    hours = delta.seconds // 3600
    if days > 0:
        return f"{days}日{hours}時間"
    return f"{hours}時間"


def main():
    if not PRODUCTS_FILE.exists():
        print("データファイルがありません。先に scraper.py を実行してください。")
        sys.exit(1)

    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    products = data.get("products", {})
    history = data.get("scrape_history", [])

    if not products:
        print("商品データがありません。")
        return

    # 現在掲載中と掲載終了で分類
    available = [p for p in products.values() if p["is_available"]]
    ended = [p for p in products.values() if not p["is_available"]]

    # 最終スクレイプ日時
    if history:
        last = history[-1]
        print(f"最終更新: {format_dt(last['timestamp'])}  (スクレイプ回数: {len(history)}回)")
    print()

    # ===== 現在掲載中 =====
    print("=" * 70)
    print(f"  現在掲載中  ({len(available)} 件)")
    print("=" * 70)

    available_sorted = sorted(available, key=lambda x: x.get("price", 0))
    for p in available_sorted:
        print(f"\n  {p['name']}")
        print(f"    型番    : {p['part_number']}")
        print(f"    価格    : {p.get('price_text', '不明')}")
        print(f"    初掲載  : {format_dt(p['first_seen'])}")
        print(f"    最終確認: {format_dt(p['last_seen'])}")
        for i, period in enumerate(p.get("periods", []), 1):
            dur = calc_duration(period["start"], period["end"])
            end_str = format_dt(period["end"]) if period["end"] else "現在も掲載中"
            print(f"    掲載期間 #{i}: {format_dt(period['start'])} ～ {end_str}  ({dur})")

    # ===== 掲載終了 =====
    if ended:
        print()
        print("=" * 70)
        print(f"  掲載終了  ({len(ended)} 件)")
        print("=" * 70)

        ended_sorted = sorted(ended, key=lambda x: x.get("last_seen", ""), reverse=True)
        for p in ended_sorted:
            print(f"\n  {p['name']}")
            print(f"    型番    : {p['part_number']}")
            print(f"    価格    : {p.get('price_text', '不明')}")
            print(f"    初掲載  : {format_dt(p['first_seen'])}")
            print(f"    掲載終了: {format_dt(p['last_seen'])}")
            for i, period in enumerate(p.get("periods", []), 1):
                dur = calc_duration(period["start"], period["end"])
                end_str = format_dt(period["end"]) if period["end"] else "不明"
                print(f"    掲載期間 #{i}: {format_dt(period['start'])} ～ {end_str}  ({dur})")

    print()
    print(f"合計: {len(products)} 件 (掲載中 {len(available)}, 終了 {len(ended)})")


if __name__ == "__main__":
    main()
