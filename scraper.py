# -*- coding: utf-8 -*-
"""
Apple Japan 整備済 iPhone 商品監視スクレイパー
使い方: python scraper.py
"""

import asyncio
import io
import json
import re
import sys

# Windows端末でのUTF-8出力を強制
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import unquote

from playwright.async_api import async_playwright

JST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
PRODUCTS_FILE = DATA_DIR / "products.json"
URL = "https://www.apple.com/jp/shop/refurbished/iphone"


def now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def load_data() -> dict:
    if PRODUCTS_FILE.exists():
        with open(PRODUCTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"products": {}, "scrape_history": []}


def save_data(data: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def extract_part_number(url: str) -> str:
    """URLから型番を抽出する。例: /product/ftmj3j/a/ -> FTMJ3J/A"""
    if not url:
        return ""
    match = re.search(r"/product/([a-z0-9]+)/([a-z0-9]+)/", url, re.IGNORECASE)
    if match:
        return f"{match.group(1).upper()}/{match.group(2).upper()}"
    match = re.search(r"/product/([a-z0-9]{6,10})", url, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return ""


async def scrape_products() -> list[dict]:
    """Apple整備済iPhoneページから商品リストを取得する"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="ja-JP")
        page = await context.new_page()

        print(f"ページを取得中: {URL}")
        await page.goto(URL, wait_until="networkidle", timeout=45000)

        # 商品リストが読み込まれるまで少し待機
        try:
            await page.wait_for_selector("li[class*='refurb'] a[href*='/product/']", timeout=10000)
        except Exception:
            pass

        items = await page.evaluate("""
        () => {
            const results = [];
            const liItems = document.querySelectorAll("li[class*='refurb']");

            liItems.forEach(li => {
                const link = li.querySelector("a[data-part-number]");
                if (!link) return;

                // 型番は data-part-number 属性から直接取得
                const partNumber = link.getAttribute("data-part-number") || "";

                // 商品名（\u00a0などの特殊スペースを通常スペースに置換）
                const rawName = link.innerText.trim().replace(/\\u00a0/g, " ");
                // "[整備済製品]" サフィックスを除去
                const name = rawName.replace(/\\[整備済製品\\]$/, "").trim();

                // 価格: span.rf-refurb-producttile-currentprice
                const priceEl = li.querySelector("span.rf-refurb-producttile-currentprice");
                const priceText = priceEl ? priceEl.innerText.trim() : "";
                const priceNum = parseInt(priceText.replace(/[^0-9]/g, ""), 10) || 0;

                if (partNumber && name) {
                    results.push({
                        name: name,
                        price_text: priceText,
                        price: priceNum,
                        part_number: partNumber,
                        url: link.href,
                    });
                }
            });

            return results;
        }
        """)

        await browser.close()
        return items


def update_records(data: dict, scraped: list[dict], timestamp: str) -> dict:
    """スクレイプ結果でレコードを更新する"""
    products = data.get("products", {})

    # 現在スクレイプした型番セット
    scraped_parts = set()

    for item in scraped:
        # data-part-number 属性を優先し、なければURLから抽出
        part = item.get("part_number") or extract_part_number(item.get("url", ""))
        if not part or not item.get("name"):
            continue

        scraped_parts.add(part)

        if part not in products:
            # 新規商品
            products[part] = {
                "name": item["name"],
                "price": item["price"],
                "price_text": item.get("price_text", ""),
                "part_number": part,
                "url": item.get("url", ""),
                "first_seen": timestamp,
                "last_seen": timestamp,
                "is_available": True,
                "periods": [{"start": timestamp, "end": None}],
            }
            print(f"  [新規] {item['name']} ({part}) - {item.get('price_text', '')}")
        else:
            existing = products[part]
            if not existing["is_available"]:
                # 再入荷
                existing["is_available"] = True
                existing["periods"].append({"start": timestamp, "end": None})
                print(f"  [再入荷] {existing['name']} ({part})")
            else:
                print(f"  [継続] {existing['name']} ({part}) - {item.get('price_text', '')}")

            # 情報を更新（名前・価格・最終確認日時）
            existing["name"] = item["name"]
            existing["last_seen"] = timestamp
            existing["price"] = item["price"]
            existing["price_text"] = item.get("price_text", "")

    # 掲載終了した商品を検出
    for part, product in products.items():
        if product["is_available"] and part not in scraped_parts:
            product["is_available"] = False
            if product["periods"] and product["periods"][-1]["end"] is None:
                product["periods"][-1]["end"] = timestamp
            print(f"  [終了] {product['name']} ({part})")

    data["products"] = products

    # スクレイプ履歴を記録
    data.setdefault("scrape_history", []).append({
        "timestamp": timestamp,
        "product_count": len(scraped_parts),
    })

    return data


async def main():
    timestamp = now_jst()
    print(f"スクレイピング開始: {timestamp}")

    try:
        scraped = await scrape_products()
    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"取得件数: {len(scraped)} 件")

    data = load_data()
    data = update_records(data, scraped, timestamp)
    save_data(data)

    print(f"データを保存しました: {PRODUCTS_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
