#!/usr/bin/env python3
import csv
import sqlite3
import re
import argparse
import datetime
from pathlib import Path


def parse_price(s: str):
    if not s:
        return None
    s = s.strip()
    m = re.search(r"\$\s*([0-9]+(?:\.[0-9]{1,2})?)", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def ensure_schema(cur):
    cur.executescript(
        '''
CREATE TABLE IF NOT EXISTS stores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_name TEXT UNIQUE NOT NULL,
  size_text TEXT,
  image_url TEXT,
  image_source TEXT,
  image_confidence REAL
);
CREATE TABLE IF NOT EXISTS purchases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  store_id INTEGER NOT NULL,
  product_id INTEGER NOT NULL,
  source_file TEXT NOT NULL,
  raw_product_name TEXT NOT NULL,
  current_price REAL,
  original_price REAL,
  notes TEXT,
  size_text TEXT,
  currency TEXT DEFAULT 'USD',
  imported_at TEXT NOT NULL,
  FOREIGN KEY(store_id) REFERENCES stores(id),
  FOREIGN KEY(product_id) REFERENCES products(id)
);
CREATE INDEX IF NOT EXISTS idx_purchases_store ON purchases(store_id);
CREATE INDEX IF NOT EXISTS idx_purchases_product ON purchases(product_id);
'''
    )


def main():
    p = argparse.ArgumentParser(description='Import grocery CSV into SQLite')
    p.add_argument('--csv', required=True, help='Path to CSV file')
    p.add_argument('--store', required=True, help='Store name, e.g. frys/sprouts')
    p.add_argument('--db', default='data/grocery.db', help='SQLite DB path')
    args = p.parse_args()

    csv_path = Path(args.csv)
    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    ensure_schema(cur)

    cur.execute('INSERT OR IGNORE INTO stores(name) VALUES (?)', (args.store.lower(),))
    cur.execute('SELECT id FROM stores WHERE name=?', (args.store.lower(),))
    store_id = cur.fetchone()[0]

    inserted = 0
    with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for r in reader:
            raw_name = (r.get('Producto') or '').strip()
            if not raw_name:
                continue

            size = (r.get('Tamaño/Cantidad') or r.get('Tamaño / Cantidad') or '').strip() or None
            price_col = (r.get('Precio') or r.get('Precio Actual') or '').strip()
            cur_price = parse_price(price_col)
            notes_col = (r.get('Precio Original / Notas') or '').strip()
            orig_price = parse_price(notes_col)
            notes = notes_col if notes_col else (price_col if any(x in price_col.lower() for x in ['est', '/lb', 'variable']) else None)

            canonical = raw_name  # normalization step comes later
            cur.execute('INSERT OR IGNORE INTO products(canonical_name, size_text) VALUES (?,?)', (canonical, size))
            cur.execute('SELECT id FROM products WHERE canonical_name=?', (canonical,))
            product_id = cur.fetchone()[0]

            cur.execute(
                '''
                SELECT 1 FROM purchases
                WHERE store_id=? AND product_id=? AND source_file=? AND raw_product_name=?
                  AND IFNULL(current_price,-1)=IFNULL(?, -1)
                  AND IFNULL(original_price,-1)=IFNULL(?, -1)
                  AND IFNULL(size_text,'')=IFNULL(?, '')
                LIMIT 1
                ''',
                (store_id, product_id, csv_path.name, raw_name, cur_price, orig_price, size),
            )
            if cur.fetchone():
                continue

            cur.execute(
                '''
                INSERT INTO purchases (
                  store_id, product_id, source_file, raw_product_name,
                  current_price, original_price, notes, size_text, imported_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                ''',
                (
                    store_id,
                    product_id,
                    csv_path.name,
                    raw_name,
                    cur_price,
                    orig_price,
                    notes,
                    size,
                    datetime.datetime.utcnow().isoformat() + 'Z',
                ),
            )
            inserted += 1

    conn.commit()
    cur.execute('SELECT COUNT(*) FROM products')
    products_total = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM purchases')
    purchases_total = cur.fetchone()[0]
    conn.close()

    print(f'Inserted rows: {inserted}')
    print(f'Products total: {products_total}')
    print(f'Purchases total: {purchases_total}')
    print(f'Database: {db_path}')


if __name__ == '__main__':
    main()
