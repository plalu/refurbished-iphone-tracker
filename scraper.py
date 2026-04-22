# -*- coding: utf-8 -*-
"""
Apple Japan 整備済商品監視スクレイパー
使い方: python scraper.py [iphone|mac|ipad]  (デフォルト: iphone)
"""

import asyncio
import io
import json
import re
import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from datetime import datetime, timezone, timedelta
from pathlib import Path

from playwright.async_api import async_playwright, Browser

JST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

CATEGORIES = {
    "iphone": "https://www.apple.com/jp/shop/refurbished/iphone",
    "mac":    "https://www.apple.com/jp/shop/refurbished/mac",
    "ipad":   "https://www.apple.com/jp/shop/refurbished/ipad",
}


def now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def load_data(category: str) -> dict:
    path = DATA_DIR / f"{category}.json"
    if category == "iphone" and not path.exists():
        legacy = DATA_DIR / "products.json"
        if legacy.exists():
            with open(legacy, encoding="utf-8") as f:
                return json.load(f)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {"products": {}, "scrape_history": []}


def save_data(data: dict, category: str) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"{category}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def extract_part_number(url: str) -> str:
    if not url:
        return ""
    match = re.search(r"/product/([a-z0-9]+)/([a-z0-9]+)/", url, re.IGNORECASE)
    if match:
        return f"{match.group(1).upper()}/{match.group(2).upper()}"
    match = re.search(r"/product/([a-z0-9]{6,10})", url, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return ""


async def scrape_products(url: str, browser: Browser) -> list[dict]:
    """整備済ページから商品リストを取得する"""
    context = await browser.new_context(locale="ja-JP")
    page = await context.new_page()

    print(f"ページを取得中: {url}")
    await page.goto(url, wait_until="networkidle", timeout=45000)

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
            const partNumber = link.getAttribute("data-part-number") || "";
            const rawName = link.innerText.trim().replace(/\u00a0/g, " ");
            const name = rawName.replace(/\[整備済製品\]$/, "").trim();
            const priceEl = li.querySelector("span.rf-refurb-producttile-currentprice");
            const priceText = priceEl ? priceEl.innerText.trim() : "";
            const priceNum = parseInt(priceText.replace(/[^0-9]/g, ""), 10) || 0;
            if (partNumber && name) {
                results.push({ name, price_text: priceText, price: priceNum, part_number: partNumber, url: link.href });
            }
        });
        return results;
    }
    """)

    await context.close()
    return items


async def fetch_retail_price(url: str, browser: Browser) -> str:
    """Apple商品ページから定価（新品価格）を取得する"""
    if not url:
        return ""
    context = await browser.new_context(locale="ja-JP")
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)

        result = await page.evaluate("""
        () => {
            // JSON-LD structured data を確認
            for (const script of document.querySelectorAll('script[type="application/ld+json"]')) {
                try {
                    const data = JSON.parse(script.textContent);
                    const extract = (obj) => {
                        if (!obj || typeof obj !== 'object') return null;
                        if (obj['@type'] === 'Product' && obj.offers) {
                            const offers = Array.isArray(obj.offers) ? obj.offers : [obj.offers];
                            for (const offer of offers) {
                                const p = parseInt(offer.price);
                                if (p > 0) return '¥' + p.toLocaleString('ja-JP');
                            }
                        }
                        return null;
                    };
                    const items = Array.isArray(data) ? data : [data];
                    for (const item of items) {
                        const found = extract(item);
                        if (found) return found;
                    }
                } catch(e) {}
            }

            // ページ内の価格要素を探す（複数セレクタを試す）
            const selectors = [
                '[data-autom="full-price"]',
                '[data-autom="original-price"]',
                '.rc-prices-fullPrice',
                '.as-price-fullPrice',
                'span[class*="fullprice"]',
                'span[class*="full-price"]',
                'span[class*="original"]',
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el && el.innerText.includes('¥')) return el.innerText.trim();
            }

            // __NEXT_DATA__ などのページ埋め込みJSONを確認
            const nextData = document.getElementById('__NEXT_DATA__');
            if (nextData) {
                try {
                    const json = JSON.parse(nextData.textContent);
                    const str = JSON.stringify(json);
                    const m = str.match(/"fullPrice"\s*:\s*"?([\d]+)"?/);
                    if (m) return '¥' + parseInt(m[1]).toLocaleString('ja-JP');
                } catch(e) {}
            }

            return "";
        }
        """)
        return result or ""
    except Exception as e:
        print(f"  定価取得エラー: {e}")
        return ""
    finally:
        await context.close()


def update_records(data: dict, scraped: list[dict], timestamp: str) -> dict:
    products = data.get("products", {})
    scraped_parts = set()

    for item in scraped:
        part = item.get("part_number") or extract_part_number(item.get("url", ""))
        if not part or not item.get("name"):
            continue
        scraped_parts.add(part)

        if part not in products:
            products[part] = {
                "name": item["name"],
                "price": item["price"],
                "price_text": item.get("price_text", ""),
                "retail_price_text": item.get("retail_price_text", ""),
                "part_number": part,
                "url": item.get("url", ""),
                "first_seen": timestamp,
                "last_seen": timestamp,
                "is_available": True,
                "periods": [{"start": timestamp, "end": None}],
            }
            print(f"  [新規] {item['name']} ({part}) - {item.get('price_text', '')} / 定価: {item.get('retail_price_text', '—')}")
        else:
            existing = products[part]
            if not existing["is_available"]:
                existing["is_available"] = True
                existing["periods"].append({"start": timestamp, "end": None})
                print(f"  [再入荷] {existing['name']} ({part})")
            else:
                print(f"  [継続] {existing['name']} ({part}) - {item.get('price_text', '')}")
            existing["name"] = item["name"]
            existing["last_seen"] = timestamp
            existing["price"] = item["price"]
            existing["price_text"] = item.get("price_text", "")
            # 定価は一度取得できたら上書きしない
            if item.get("retail_price_text") and not existing.get("retail_price_text"):
                existing["retail_price_text"] = item["retail_price_text"]

    for part, product in products.items():
        if product["is_available"] and part not in scraped_parts:
            product["is_available"] = False
            if product["periods"] and product["periods"][-1]["end"] is None:
                product["periods"][-1]["end"] = timestamp
            print(f"  [終了] {product['name']} ({part})")

    data["products"] = products
    data.setdefault("scrape_history", []).append({
        "timestamp": timestamp,
        "product_count": len(scraped_parts),
    })
    return data


async def main():
    category = sys.argv[1] if len(sys.argv) > 1 else "iphone"
    if category not in CATEGORIES:
        print(f"不明なカテゴリ: {category}。有効: {list(CATEGORIES.keys())}", file=sys.stderr)
        sys.exit(1)

    timestamp = now_jst()
    print(f"[{category}] スクレイピング開始: {timestamp}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        try:
            scraped = await scrape_products(CATEGORIES[category], browser)
        except Exception as e:
            print(f"エラー: {e}", file=sys.stderr)
            await browser.close()
            sys.exit(1)

        print(f"取得件数: {len(scraped)} 件")
        if len(scraped) == 0:
            print("警告: 商品が0件でした。データは更新しません。", file=sys.stderr)
            await browser.close()
            sys.exit(1)

        # 定価が未取得の商品を対象に取得する
        data = load_data(category)
        existing_products = data.get("products", {})
        for item in scraped:
            part = item.get("part_number")
            already_has = existing_products.get(part, {}).get("retail_price_text", "")
            if not already_has and item.get("url"):
                print(f"  定価を取得中: {item['name']}")
                item["retail_price_text"] = await fetch_retail_price(item["url"], browser)
                if item["retail_price_text"]:
                    print(f"    → {item['retail_price_text']}")
                else:
                    print(f"    → 取得できませんでした")

        await browser.close()

    data = update_records(data, scraped, timestamp)
    save_data(data, category)
    print(f"データを保存しました: data/{category}.json")


if __name__ == "__main__":
    asyncio.run(main())
