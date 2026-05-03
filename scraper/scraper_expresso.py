#!/usr/bin/env python3
"""
News Articles Scraper — scrape_news style
Fetches ALL politics articles from Expresso and Publico APIs directly,
stores in a unified articles table. No per-deputy matching.

Schema matches scrape_news:
  code, title, lead, friendly_uri, link, published_date, last_modified_date,
  main_category, article_type, exclusive, authors, picture_url, picture_caption,
  picture_credits, domain, uuid
"""

import os
import sys
import time
import json
from datetime import datetime
from typing import Optional

import requests
import psycopg2

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

# ── Configuration ────────────────────────────────────────────────────────────
EXPRESSO_FEED_URL = "https://expresso.pt/api/gs/expresso/v1/molecule/feed"
PUBLICO_LIST_URL = "https://www.publico.pt/api/list/politica"
STOP_DATE = "2020-01-01T00:00:00.000Z"
STOP_DATE_PUBLICO = "2020-01-01"

EXPRESSO_MAX_RETRIES = 3
EXPRESSO_BASE_DELAY = 2
PUBLICO_MAX_RETRIES = 5
PUBLICO_BASE_DELAY = 3

# ── DB helpers ───────────────────────────────────────────────────────────────

def _find_env_file() -> Optional[str]:
    start = os.path.dirname(os.path.abspath(__file__))
    for _ in range(5):
        for name in ("website/.env", ".env"):
            candidate = os.path.join(start, name)
            if os.path.exists(candidate):
                return candidate
        parent = os.path.dirname(start)
        if parent == start:
            break
        start = parent
    return None


def get_db_url() -> str:
    env_path = _find_env_file()
    if env_path:
        with open(env_path) as f:
            for line in f:
                if line.startswith("DATABASE_URL="):
                    return line.strip().split("=", 1)[1].strip('"').strip("'")
    return os.environ.get(
        "DATABASE_URL", "postgresql://populi:populi@localhost:5432/populi-db"
    )


def get_connection():
    db_url = get_db_url()
    if not db_url:
        raise RuntimeError("DATABASE_URL not found in .env or environment")
    return psycopg2.connect(db_url)


def ensure_articles_table(conn):
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id SERIAL PRIMARY KEY,
                code TEXT UNIQUE,
                title TEXT,
                lead TEXT,
                friendly_uri TEXT,
                link TEXT,
                published_date TEXT,
                last_modified_date TEXT,
                main_category TEXT,
                article_type TEXT,
                exclusive INTEGER DEFAULT 0,
                authors TEXT,
                picture_url TEXT,
                picture_caption TEXT,
                picture_credits TEXT,
                domain TEXT,
                uuid TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_articles_published_date ON articles (published_date)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_articles_domain ON articles (domain)
        """)
    conn.commit()


def insert_article(cur, article: dict) -> bool:
    try:
        cur.execute("""
            INSERT INTO articles
            (code, title, lead, friendly_uri, link, published_date, last_modified_date,
             main_category, article_type, exclusive, authors, picture_url, picture_caption,
             picture_credits, domain, uuid)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (code) DO NOTHING
        """, (
            article.get("code", ""),
            article.get("title", ""),
            article.get("lead", ""),
            article.get("friendly_uri", ""),
            article.get("link", ""),
            article.get("published_date", ""),
            article.get("last_modified_date", ""),
            article.get("main_category", ""),
            article.get("article_type", ""),
            article.get("exclusive", 0),
            article.get("authors", ""),
            article.get("picture_url", ""),
            article.get("picture_caption", ""),
            article.get("picture_credits", ""),
            article.get("domain", ""),
            article.get("uuid", ""),
        ))
        return cur.rowcount > 0
    except Exception:
        return False


# ── Progress bar ─────────────────────────────────────────────────────────────

def print_progress(current, estimated_total, label, extra=""):
    pct = min(100, int((current / estimated_total) * 100)) if estimated_total else 0
    bar_len = 40
    filled = int(bar_len * pct / 100)
    bar = "\u2588" * filled + "\u2591" * (bar_len - filled)
    sys.stdout.write(f"\r[{bar}] {pct}% | {label}: {current} {extra}")
    sys.stdout.flush()


# ── Expresso scraper ─────────────────────────────────────────────────────────

def fetch_expresso_batch(until: str, page: int, limit: int) -> Optional[dict]:
    params = {
        "categories": "/politica",
        "category": "politica",
        "contentTypes": "ARTICLE",
        "limit": limit,
        "until": until,
        "page": page,
    }
    for attempt in range(EXPRESSO_MAX_RETRIES):
        try:
            resp = requests.get(EXPRESSO_FEED_URL, params=params, timeout=30)
            if resp.status_code == 500 and attempt < EXPRESSO_MAX_RETRIES - 1:
                wait = EXPRESSO_BASE_DELAY * (2 ** attempt)
                sys.stdout.write(f"\n  Expresso: server error, retrying in {wait}s...\n")
                sys.stdout.flush()
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            if attempt < EXPRESSO_MAX_RETRIES - 1:
                wait = EXPRESSO_BASE_DELAY * (2 ** attempt)
                sys.stdout.write(f"\n  Expresso: {e}, retrying in {wait}s...\n")
                sys.stdout.flush()
                time.sleep(wait)
            else:
                raise
    return None


def transform_expresso_item(item: dict) -> dict:
    authors_list = item.get("authors", []) or []
    authors_str = ", ".join([a.get("name", "") for a in authors_list if isinstance(a, dict) and a.get("name")])

    picture = item.get("picture", {}) or {}
    picture_url = picture.get("urlLandscape", "") or ""
    picture_caption = picture.get("caption", "") or ""
    picture_credits = picture.get("credits", "") or ""

    main_cat = item.get("mainCategory", "")
    if isinstance(main_cat, dict):
        main_cat = main_cat.get("name", "")

    domain_obj = item.get("domain", "")
    if isinstance(domain_obj, dict):
        domain = domain_obj.get("name", "")
    else:
        domain = domain_obj or "Expresso"

    return {
        "code": str(item.get("code", "")),
        "title": str(item.get("title", "") or ""),
        "lead": str(item.get("lead", "") or ""),
        "friendly_uri": str(item.get("friendlyURI", "") or ""),
        "link": str(item.get("link", "") or ""),
        "published_date": str(item.get("publishedDate", "") or ""),
        "last_modified_date": str(item.get("lastModifiedDate", "") or ""),
        "main_category": str(main_cat) if main_cat else "",
        "article_type": str(item.get("articleType", "") or ""),
        "exclusive": 1 if item.get("exclusive") else 0,
        "authors": authors_str,
        "picture_url": picture_url,
        "picture_caption": picture_caption,
        "picture_credits": picture_credits,
        "domain": domain,
        "uuid": str(item.get("uuid", "") or ""),
    }


def scrape_expresso_to_db(conn):
    print("\n=== Expresso ===")
    ensure_articles_table(conn)

    seen_codes = set()
    total_inserted = 0
    total_fetched = 0

    until = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    page = 0
    limit = 100
    estimated_total = 30000

    print("Fetching Expresso Politica articles back to 2020...")
    print_progress(0, estimated_total, "Fetched")

    with conn.cursor() as cur:
        while True:
            data = fetch_expresso_batch(until, page, limit)
            if data is None:
                print("\nFailed to fetch after retries. Stopping.")
                break

            items = data.get("contents", [])
            if not items:
                print("\nNo more items returned by API.")
                break

            dates = [item.get("publishedDate", "9999") for item in items]
            oldest_in_batch = min(dates)

            for item in items:
                code = item.get("code")
                if code and code not in seen_codes:
                    seen_codes.add(code)
                    total_fetched += 1

                    article_type = item.get("type", "")
                    published = item.get("publishedDate", "")
                    if article_type == "ARTICLE" and published >= STOP_DATE:
                        article = transform_expresso_item(item)
                        if insert_article(cur, article):
                            total_inserted += 1

            print_progress(total_fetched, estimated_total, "Fetched",
                         f"| Inserted: {total_inserted} | Oldest: {oldest_in_batch[:10]}")

            if oldest_in_batch < STOP_DATE:
                print("\nReached 2020! Stopping.")
                break

            if len(items) < limit:
                until = oldest_in_batch
                page = 0
            else:
                page += 1

            if page >= 80:
                until = oldest_in_batch
                page = 0

            time.sleep(0.3)

    conn.commit()
    print(f"\nExpresso done: {total_fetched} unique items, {total_inserted} new articles inserted.")
    return total_inserted


# ── Publico scraper ──────────────────────────────────────────────────────────

def fetch_publico_page(page: int) -> Optional[list]:
    for attempt in range(PUBLICO_MAX_RETRIES):
        try:
            resp = requests.get(f"{PUBLICO_LIST_URL}?page={page}", timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            if attempt < PUBLICO_MAX_RETRIES - 1:
                wait = PUBLICO_BASE_DELAY * (1.5 ** attempt)
                sys.stdout.write(f"\n  Publico page {page}: {e}, retrying in {wait:.0f}s...\n")
                sys.stdout.flush()
                time.sleep(wait)
            else:
                raise
    return None


def transform_publico_item(item: dict) -> dict:
    authors_list = item.get("autores", []) or []
    authors_str = ", ".join([a.get("nome", "") for a in authors_list if isinstance(a, dict) and a.get("nome")])

    picture_url = item.get("multimediaPrincipal", "") or ""
    picture_caption = item.get("multimediaPrincipalLegenda", "") or ""
    main_cat = item.get("rubrica", "") or ""

    code = str(item.get("itemId", ""))
    link = item.get("fullUrl", "") or item.get("url", "") or ""
    title = item.get("titulo", "") or ""
    lead = item.get("descricao", "") or ""
    published_date = item.get("data", "") or ""
    last_modified = item.get("dataActualizacao", "") or ""
    article_type = item.get("tipo", "") or ""
    is_exclusive = 1 if item.get("isExclusive") else 0

    return {
        "code": code,
        "title": title,
        "lead": lead,
        "friendly_uri": "",
        "link": link,
        "published_date": published_date,
        "last_modified_date": last_modified,
        "main_category": main_cat,
        "article_type": article_type,
        "exclusive": is_exclusive,
        "authors": authors_str,
        "picture_url": picture_url,
        "picture_caption": picture_caption,
        "picture_credits": "",
        "domain": "Publico",
        "uuid": code,
    }


def scrape_publico_to_db(conn):
    print("\n=== Publico ===")
    ensure_articles_table(conn)

    seen_ids = set()
    total_inserted = 0
    total_fetched = 0
    page = 1
    estimated_total = 30000

    print("Fetching Publico Politica articles back to 2020...")
    print_progress(0, estimated_total, "Fetched")

    with conn.cursor() as cur:
        while True:
            data = fetch_publico_page(page)
            if data is None:
                print(f"\nPage {page}: failed after retries. Stopping.")
                break

            if not data:
                print(f"\nPage {page}: empty, stopping.")
                break

            dates = [item.get("data", "9999") for item in data]
            oldest_in_batch = min(dates)

            for item in data:
                item_id = item.get("id")
                if item_id and item_id not in seen_ids:
                    seen_ids.add(item_id)
                    total_fetched += 1

                    published = item.get("data", "")
                    if published >= STOP_DATE_PUBLICO:
                        article = transform_publico_item(item)
                        if insert_article(cur, article):
                            total_inserted += 1

            print_progress(total_fetched, estimated_total, "Fetched",
                         f"| Inserted: {total_inserted} | Page: {page} | Oldest: {oldest_in_batch[:10]}")

            if oldest_in_batch < STOP_DATE_PUBLICO:
                print(f"\nReached 2019 at page {page}! Stopping.")
                break

            if len(data) < 10:
                print(f"\nLast page ({page}): {len(data)} items.")
                break

            page += 1
            time.sleep(0.2)

    conn.commit()
    print(f"\nPublico done: {total_fetched} unique items, {total_inserted} new articles inserted.")
    return total_inserted


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    start_time = time.time()

    conn = get_connection()
    try:
        expresso_count = scrape_expresso_to_db(conn)
        publico_count = scrape_publico_to_db(conn)

        elapsed = time.time() - start_time
        print(f"\n{'='*50}")
        print(f"Total: {expresso_count + publico_count} new articles inserted")
        print(f"  Expresso: {expresso_count}")
        print(f"  Publico:  {publico_count}")
        print(f"Time: {elapsed:.1f}s")

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM articles")
            total = cur.fetchone()[0]
            cur.execute("SELECT domain, COUNT(*) FROM articles GROUP BY domain ORDER BY COUNT(*) DESC")
            by_domain = cur.fetchall()
            cur.execute("""
                SELECT EXTRACT(YEAR FROM TO_DATE(published_date, 'YYYY-MM-DD')) as year, COUNT(*)
                FROM articles WHERE published_date IS NOT NULL
                GROUP BY year ORDER BY year DESC LIMIT 10
            """)
            by_year = cur.fetchall()

        print(f"\nTotal articles in DB: {total}")
        print("By domain:")
        for domain, count in by_domain:
            print(f"  {domain}: {count}")
        print("By year (top 10):")
        for year, count in by_year:
            print(f"  {int(year) if year else 'NULL'}: {count}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
