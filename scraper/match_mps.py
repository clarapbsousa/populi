#!/usr/bin/env python3
"""Match MPs (deputies) to news articles using name-based text matching.

Reads articles from PostgreSQL articles table, matches against all deputies
using regex patterns, stores results in article_mp_matches table.
"""

import os
import sys
import re
import time
from collections import defaultdict
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

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


# ── Helpers ──────────────────────────────────────────────────────────────────

def strip_html(text: str) -> str:
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', ' ', text)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def get_deputies(conn) -> list[dict]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT d.id, d.dep_nome_parlamentar, d.dep_nome_completo,
                   COALESCE(ph.sigla, '') as party
            FROM deputies d
            LEFT JOIN LATERAL (
                SELECT p.sigla
                FROM party_history ph2
                JOIN parties p ON p.id = ph2.party_id
                WHERE ph2.deputy_id = d.id
                ORDER BY ph2.gp_dt_inicio DESC
                LIMIT 1
            ) ph ON true
            WHERE EXISTS (
                SELECT 1 FROM status_history sh
                WHERE sh.deputy_id = d.id
                AND sh.sio_dt_fim IS NULL
                AND sh.sio_des != 'Suplente'
            )
            ORDER BY d.id
        """)
        return [dict(row) for row in cur.fetchall()]


def build_mp_patterns(deputies: list[dict]) -> dict:
    surname_counts = defaultdict(list)
    for dep in deputies:
        name = dep["dep_nome_parlamentar"].strip()
        parts = name.split()
        last = parts[-1].lower() if len(parts) > 1 else ""
        if last:
            surname_counts[last].append(dep["id"])

    colliding_surnames = {s for s, ids in surname_counts.items() if len(ids) > 1}

    mp_info = {}
    for dep in deputies:
        mp_id = dep["id"]
        name = dep["dep_nome_parlamentar"].strip()
        fullname = dep["dep_nome_completo"].strip()
        party = dep.get("party", "")

        parts = name.split()
        first = parts[0] if parts else ""
        last = parts[-1] if len(parts) > 1 else ""

        patterns = []

        if len(fullname.split()) > 1:
            patterns.append(("full", re.compile(r'\b' + re.escape(fullname) + r'\b', re.IGNORECASE)))

        if len(parts) >= 2:
            patterns.append(("short", re.compile(r'\b' + re.escape(name) + r'\b', re.IGNORECASE)))

        if len(parts) >= 2:
            patterns.append(("first_last", re.compile(
                r'\b' + re.escape(first) + r'\s+' + re.escape(last) + r'\b', re.IGNORECASE)))

        if last and last.lower() not in colliding_surnames and len(last) > 3:
            patterns.append(("last", re.compile(r'\b' + re.escape(last) + r'\b', re.IGNORECASE)))

        mp_info[mp_id] = {
            "name": name,
            "party": party,
            "patterns": patterns,
        }
    return mp_info


def find_best_match(title: str, lead: str, patterns: list) -> tuple[int, Optional[str]]:
    title_text = title or ""
    lead_text = strip_html(lead or "")

    best_quality = None
    best_count = 0

    for priority in ("full", "short", "first_last", "last"):
        for p, pattern in patterns:
            if p == priority:
                title_matches = pattern.findall(title_text)
                lead_matches = pattern.findall(lead_text)
                total = len(title_matches) + len(lead_matches)
                if total > 0 and best_quality is None:
                    if title_matches:
                        best_quality = f"title_{priority}"
                    else:
                        best_quality = f"lead_{priority}"
                    best_count = total

    return best_count, best_quality


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    conn = get_connection()
    deputies = get_deputies(conn)
    mp_info = build_mp_patterns(deputies)

    print(f"Loaded {len(deputies)} deputies")

    with conn.cursor() as cur:
        cur.execute("SELECT id, title, lead, domain FROM articles")
        articles = cur.fetchall()

        cur.execute("DELETE FROM article_mp_matches")

        total = len(articles)
        matches_count = 0
        start = time.time()

        print(f"Matching {total} articles against {len(mp_info)} deputies...")
        iterator = tqdm(range(total), desc="Matching articles", unit="article") if tqdm else range(total)
        for i in iterator:
            art_id, title, lead, domain = articles[i]
            source = (domain or "unknown").lower()

            for mp_id, info in mp_info.items():
                count, quality = find_best_match(title, lead, info["patterns"])
                if count > 0:
                    cur.execute(
                        """INSERT INTO article_mp_matches
                        (article_id, mp_id, mp_name, mp_party, mention_count, match_quality, article_source)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (art_id, mp_id, info["name"], info["party"], count, quality, source)
                    )
                    matches_count += 1

            if not tqdm:
                pct = (i + 1) * 100 // total
                if (i + 1) % 1000 == 0 or (i + 1) == total:
                    elapsed = time.time() - start
                    eta = elapsed / (i + 1) * (total - i - 1) if i > 0 else 0
                    print(f"  [{pct:3d}%] {i+1}/{total} articles, {matches_count} matches ({elapsed:.0f}s elapsed, ~{eta:.0f}s remaining)")

        conn.commit()

        elapsed = time.time() - start
        print(f"\nDone in {elapsed:.1f}s")
        print(f"Total article-MP matches: {matches_count}")

        cur.execute("SELECT COUNT(DISTINCT article_id) FROM article_mp_matches")
        print(f"Articles with at least 1 MP mention: {cur.fetchone()[0]}")

        cur.execute("SELECT COUNT(DISTINCT mp_id) FROM article_mp_matches")
        print(f"Unique MPs mentioned: {cur.fetchone()[0]}")

        print("\nMatch quality distribution:")
        cur.execute("""
            SELECT match_quality, COUNT(*) as matches, COUNT(DISTINCT article_id) as articles
            FROM article_mp_matches
            GROUP BY match_quality
            ORDER BY CASE match_quality
                WHEN 'title_full' THEN 1
                WHEN 'title_short' THEN 2
                WHEN 'title_first_last' THEN 3
                WHEN 'title_last' THEN 4
                WHEN 'lead_full' THEN 5
                WHEN 'lead_short' THEN 6
                WHEN 'lead_first_last' THEN 7
                WHEN 'lead_last' THEN 8
            END
        """)
        for quality, matches, arts in cur.fetchall():
            print(f"  {quality:16s}: {matches:5d} matches in {arts:5d} articles")

        print("\nMatches by source:")
        cur.execute("""
            SELECT article_source, COUNT(*) as matches, COUNT(DISTINCT article_id) as articles
            FROM article_mp_matches
            GROUP BY article_source
            ORDER BY matches DESC
        """)
        for source, matches, arts in cur.fetchall():
            print(f"  {source:16s}: {matches:5d} matches in {arts:5d} articles")

        print("\nTop 25 most mentioned MPs:")
        cur.execute("""
            SELECT mp_name, mp_party, SUM(mention_count) as total_mentions,
                   COUNT(DISTINCT article_id) as articles
            FROM article_mp_matches
            GROUP BY mp_id, mp_name, mp_party
            ORDER BY total_mentions DESC
            LIMIT 25
        """)
        for name, party, mentions, arts in cur.fetchall():
            print(f"  {name:30s} ({party:6s}) {mentions:4d} mentions in {arts:3d} articles")

    conn.close()


if __name__ == "__main__":
    main()
