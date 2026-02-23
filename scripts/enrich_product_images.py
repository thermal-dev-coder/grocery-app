#!/usr/bin/env python3
import argparse
import json
import sqlite3
import time
import urllib.parse
import urllib.request
from difflib import SequenceMatcher

UA = "Mozilla/5.0 (compatible; RonBot/1.0; +https://openclaw.ai)"


def http_json(url, timeout=4):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="ignore"))


def similarity(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def search_openfoodfacts(product_name):
    q = urllib.parse.quote(product_name)
    url = (
        "https://world.openfoodfacts.org/cgi/search.pl"
        f"?search_terms={q}&search_simple=1&action=process&json=1&page_size=5"
    )
    try:
        data = http_json(url)
    except Exception:
        return None
    products = data.get("products", [])
    best = None
    best_score = 0.0

    for p in products:
        name = (p.get("product_name") or "").strip()
        if not name:
            continue
        score = similarity(product_name, name)
        image_url = p.get("image_front_small_url") or p.get("image_front_url") or p.get("image_url")
        if image_url and score > best_score:
            best = (image_url, name, score)
            best_score = score

    return best


def search_wikipedia(product_name):
    q = urllib.parse.quote(product_name)
    url = (
        "https://en.wikipedia.org/w/api.php?action=query&format=json"
        "&generator=search&gsrlimit=3&prop=pageimages|info&inprop=url"
        "&piprop=thumbnail&pithumbsize=400"
        f"&gsrsearch={q}"
    )
    try:
        data = http_json(url)
    except Exception:
        return None
    pages = (data.get("query") or {}).get("pages") or {}
    best = None
    best_score = 0.0
    for _, p in pages.items():
        title = p.get("title", "")
        thumb = (p.get("thumbnail") or {}).get("source")
        if not thumb:
            continue
        score = similarity(product_name, title)
        if score > best_score:
            best_score = score
            best = (thumb, title, score)
    return best


def main():
    ap = argparse.ArgumentParser(description="Enrich product images in grocery.db")
    ap.add_argument("--db", default="data/grocery.db")
    ap.add_argument("--limit", type=int, default=0, help="0 = all missing")
    ap.add_argument("--sleep-ms", type=int, default=120)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()

    q = "SELECT id, canonical_name FROM products WHERE image_url IS NULL OR image_url='' ORDER BY id"
    if args.limit and args.limit > 0:
        q += f" LIMIT {args.limit}"
    cur.execute(q)
    rows = cur.fetchall()

    updated = 0
    source_counts = {"openfoodfacts": 0, "wikipedia": 0}
    skipped = 0

    for pid, name in rows:
        hit = search_openfoodfacts(name)
        source = None
        url = None
        conf = 0.0

        if hit and hit[2] >= 0.42:
            url, matched_name, score = hit
            source = "openfoodfacts"
            conf = round(min(0.95, 0.55 + score * 0.4), 3)
        else:
            wh = search_wikipedia(name)
            if wh and wh[2] >= 0.45:
                url, matched_name, score = wh
                source = "wikipedia"
                conf = round(min(0.85, 0.45 + score * 0.35), 3)

        if source and url:
            cur.execute(
                "UPDATE products SET image_url=?, image_source=?, image_confidence=? WHERE id=?",
                (url, source, conf, pid),
            )
            updated += 1
            source_counts[source] += 1
        else:
            skipped += 1

        time.sleep(max(0, args.sleep_ms) / 1000.0)

    conn.commit()

    cur.execute("SELECT COUNT(*) FROM products")
    total = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM products WHERE image_url IS NOT NULL AND image_url<>''")
    with_img = cur.fetchone()[0]

    print(f"Processed: {len(rows)}")
    print(f"Updated: {updated}")
    print(f"Skipped: {skipped}")
    print(f"Coverage: {with_img}/{total}")
    print("By source:", source_counts)

    conn.close()


if __name__ == "__main__":
    main()
