#!/usr/bin/env python3
import argparse
import json
import re
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


def normalize_name(name: str):
    s = (name or '').lower()
    s = s.replace('®', ' ').replace('™', ' ').replace("’", "'")
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"\b\d+(?:[\.,]\d+)?\s*(oz|fl\s*oz|lb|ct|ea|each|g|kg|ml|l|gal|pt)\b", " ", s)
    s = re.sub(r"\b(organic|fresh|family\s*size|large|small|mini|original|single|individual|bag|pack|vp|no\s*salt)\b", " ", s)
    s = re.sub(r"[^a-z0-9\s\-']", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def search_openfoodfacts(product_name):
    variants = [product_name]
    n = normalize_name(product_name)
    if n and n != product_name:
        variants.append(n)
    tokens = n.split()
    if len(tokens) > 4:
        variants.append(' '.join(tokens[:4]))

    best = None
    best_score = 0.0
    for v in variants:
        q = urllib.parse.quote(v)
        url = (
            "https://world.openfoodfacts.org/cgi/search.pl"
            f"?search_terms={q}&search_simple=1&action=process&json=1&page_size=8"
        )
        try:
            data = http_json(url)
        except Exception:
            continue
        products = data.get("products", [])

        for p in products:
            name = (p.get("product_name") or "").strip()
            if not name:
                continue
            score = max(
                similarity(product_name, name),
                similarity(normalize_name(product_name), normalize_name(name))
            )
            image_url = p.get("image_front_small_url") or p.get("image_front_url") or p.get("image_url")
            if image_url and score > best_score:
                best = (image_url, name, score)
                best_score = score

    return best


def search_openverse(product_name):
    variants = [product_name]
    n = normalize_name(product_name)
    if n and n != product_name:
        variants.append(n)
    tokens = n.split()
    if len(tokens) > 4:
        variants.append(' '.join(tokens[:4]))

    best = None
    best_score = 0.0
    for v in variants:
        q = urllib.parse.quote(v)
        url = (
            "https://api.openverse.org/v1/images/"
            f"?q={q}&page_size=8&license_type=commercial&extension=jpg&extension=jpeg&extension=png"
        )
        try:
            data = http_json(url, timeout=8)
        except Exception:
            continue
        for item in data.get("results", []):
            title = (item.get("title") or "").strip()
            img = item.get("url")
            if not title or not img:
                continue
            score = max(
                similarity(product_name, title),
                similarity(normalize_name(product_name), normalize_name(title)),
            )
            if score > best_score:
                best_score = score
                best = (img, title, score)
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


GENERIC_KEYWORD_IMAGES = {
    "banana": "https://upload.wikimedia.org/wikipedia/commons/8/8a/Banana-Single.jpg",
    "apple": "https://upload.wikimedia.org/wikipedia/commons/1/15/Red_Apple.jpg",
    "tomato": "https://upload.wikimedia.org/wikipedia/commons/8/89/Tomato_je.jpg",
    "onion": "https://upload.wikimedia.org/wikipedia/commons/2/25/Onion_on_White.JPG",
    "potato": "https://upload.wikimedia.org/wikipedia/commons/6/60/Patates.jpg",
    "cucumber": "https://upload.wikimedia.org/wikipedia/commons/9/96/ARS_cucumber.jpg",
    "bell pepper": "https://upload.wikimedia.org/wikipedia/commons/8/85/Assorted_peppers.jpg",
    "pepper": "https://upload.wikimedia.org/wikipedia/commons/8/85/Assorted_peppers.jpg",
    "strawberry": "https://upload.wikimedia.org/wikipedia/commons/2/29/PerfectStrawberry.jpg",
    "blueberries": "https://upload.wikimedia.org/wikipedia/commons/1/13/Blueberries.jpg",
    "blueberry": "https://upload.wikimedia.org/wikipedia/commons/1/13/Blueberries.jpg",
    "avocado": "https://upload.wikimedia.org/wikipedia/commons/c/c9/Avocado_Hass_-_single_and_halved.jpg",
    "lemon": "https://upload.wikimedia.org/wikipedia/commons/c/c6/Lemon-Whole-Split.jpg",
    "orange": "https://upload.wikimedia.org/wikipedia/commons/c/c4/Orange-Fruit-Pieces.jpg",
    "cilantro": "https://upload.wikimedia.org/wikipedia/commons/2/2f/Coriandrum_sativum_-_K%C3%B6hler%E2%80%93s_Medizinal-Pflanzen-193.jpg",
    "parsley": "https://upload.wikimedia.org/wikipedia/commons/0/0f/Petroselinum_crispum2.jpg",
    "carrot": "https://upload.wikimedia.org/wikipedia/commons/7/70/Carrot_on_White.JPG",
    "eggplant": "https://upload.wikimedia.org/wikipedia/commons/f/fb/Aubergine.jpg",
    "squash": "https://upload.wikimedia.org/wikipedia/commons/5/59/Cucurbita_moschata_Butternut_20051011_203.jpg",
    "chayote": "https://upload.wikimedia.org/wikipedia/commons/f/f1/Chayote_BNC.jpg",
    "grapes": "https://upload.wikimedia.org/wikipedia/commons/b/bb/Table_grapes_on_white.jpg",
    "mango": "https://upload.wikimedia.org/wikipedia/commons/9/90/Hapus_Mango.jpg",
    "corn": "https://upload.wikimedia.org/wikipedia/commons/7/72/Maize_stalk.jpg",
    "milk": "https://upload.wikimedia.org/wikipedia/commons/a/a4/Milk_glass.jpg",
    "bread": "https://upload.wikimedia.org/wikipedia/commons/d/d1/Loaf_of_bread.jpg",
    "cheese": "https://upload.wikimedia.org/wikipedia/commons/4/44/Cheese_platter.jpg",
    "yogurt": "https://upload.wikimedia.org/wikipedia/commons/3/37/Yogurt.jpg",
    "butter": "https://upload.wikimedia.org/wikipedia/commons/0/0e/Butter_on_spoon.jpg",
    "rice": "https://upload.wikimedia.org/wikipedia/commons/6/6f/Rice_grains_%28IRRI%29.jpg",
    "pasta": "https://upload.wikimedia.org/wikipedia/commons/4/4f/Fusilli_pasta.jpg",
    "tortilla": "https://upload.wikimedia.org/wikipedia/commons/2/2c/Flour_tortillas.jpg",
    "beans": "https://upload.wikimedia.org/wikipedia/commons/5/5f/Black_beans.jpg",
    "shrimp": "https://upload.wikimedia.org/wikipedia/commons/8/82/Shrimps.jpg",
    "tuna": "https://upload.wikimedia.org/wikipedia/commons/d/d7/Thunnus_albacares.jpg",
    "chicken": "https://upload.wikimedia.org/wikipedia/commons/3/32/Chicken_breast.png",
    "beef": "https://upload.wikimedia.org/wikipedia/commons/9/91/Raw_beef.png",
    "pork": "https://upload.wikimedia.org/wikipedia/commons/0/01/Pork_meat.jpg",
    "honey": "https://upload.wikimedia.org/wikipedia/commons/5/52/Honey_%28food%29.jpg",
    "vinegar": "https://upload.wikimedia.org/wikipedia/commons/0/06/White_vinegar.jpg",
    "kombucha": "https://upload.wikimedia.org/wikipedia/commons/3/3e/Kombucha_Mature.jpg",
    "salt": "https://upload.wikimedia.org/wikipedia/commons/5/5d/Salt_shaker_on_white_background.jpg",
    "sugar": "https://upload.wikimedia.org/wikipedia/commons/7/70/Sugar_cubes.jpg",
}


def generic_fallback_image(product_name: str):
    n = normalize_name(product_name)
    for k, v in GENERIC_KEYWORD_IMAGES.items():
        if k in n:
            return v, k, 0.35
    return None


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
    source_counts = {"openfoodfacts": 0, "openverse": 0, "wikipedia": 0, "generic": 0}
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
            ov = search_openverse(name)
            if ov and ov[2] >= 0.33:
                url, matched_name, score = ov
                source = "openverse"
                conf = round(min(0.82, 0.38 + score * 0.35), 3)
            else:
                wh = search_wikipedia(name)
                if wh and wh[2] >= 0.45:
                    url, matched_name, score = wh
                    source = "wikipedia"
                    conf = round(min(0.85, 0.45 + score * 0.35), 3)
                else:
                    gh = generic_fallback_image(name)
                    if gh:
                        url, matched_name, conf = gh
                        source = "generic"

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
