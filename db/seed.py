"""Load the CSVs and the policy PDF from data/ into Postgres.

Usage: python -m db.seed   (safe to re-run: tables are emptied and reloaded)
"""

import csv
import json
import re
from pathlib import Path

from pypdf import PdfReader

from db.connection import get_pool

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
PREFIX = "desafio_tecnico_ai_eng - "
POLICY_PDF = DATA_DIR / "políticas_da_loja.pdf"


def read_csv(name: str) -> list[dict]:
    with open(DATA_DIR / f"{PREFIX}{name}.csv", encoding="utf-8-sig", newline="") as f:
        # empty strings become NULL
        return [{k: (v if v != "" else None) for k, v in row.items()} for row in csv.DictReader(f)]


def insert(cur, table: str, rows: list[dict]) -> None:
    cols = list(rows[0])
    cur.executemany(
        f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(f'%({c})s' for c in cols)})",
        rows,
    )
    print(f"{table}: {len(rows)} rows")


def parse_policies(pdf_path: Path) -> list[dict]:
    """Split the manual into one chunk per subsection (e.g. '4.2 Trocas por Defeito')."""
    # default extraction yields one word per line; layout mode keeps real lines
    pages = [p.extract_text(extraction_mode="layout") for p in PdfReader(pdf_path).pages[1:]]  # skip cover
    lines: list[str] = []
    for line in "\n".join(pages).splitlines():
        line = line.strip()
        if not line or line.startswith("Empório da Música Manual") or re.fullmatch(r"Página \d+", line):
            continue
        lines.append(line)

    chunks: list[dict] = []
    current: dict | None = None
    top_title, next_top = "", 1
    for line in lines:
        top = re.match(rf"{next_top}\. (\S.*)", line)
        sub = re.match(r"(\d+\.\d+) (\S.*)", line)
        if top:
            next_top += 1
            top_title = top.group(1)
            current = {"section": str(next_top - 1), "title": top_title, "lines": []}
            chunks.append(current)
        elif sub:
            current = {"section": sub.group(1), "title": f"{top_title} - {sub.group(2)}", "lines": []}
            chunks.append(current)
        elif current:
            current["lines"].append(line)

    return [
        {
            "section": c["section"],
            "title": c["title"],
            # the PDF spells the store e-mail with an accent in section 1.2; the real one has none
            "content": re.sub(r"\s+", " ", " ".join(c["lines"])).replace("empóriodamusica", "emporiodamusica"),
        }
        for c in chunks
        if c["lines"]
    ]


def main() -> None:
    policies = parse_policies(POLICY_PDF)
    products = read_csv("products")
    for p in products:
        json.loads(p["specs"])  # fail early on malformed JSON
    promotions = read_csv("promotions")
    for p in promotions:
        p["is_active"] = p["is_active"] == "1"

    with get_pool().connection() as conn, conn.cursor() as cur:
        cur.execute((ROOT / "db" / "schema.sql").read_text(encoding="utf-8"))
        cur.execute(
            "TRUNCATE policy_chunks, order_items, orders, customers, promotions, products, categories"
            " RESTART IDENTITY"
        )
        insert(cur, "categories", read_csv("categories"))
        insert(cur, "products", products)
        insert(cur, "promotions", promotions)
        insert(cur, "customers", read_csv("customers"))
        insert(cur, "orders", read_csv("orders"))
        insert(cur, "order_items", read_csv("order_items"))

        cur.executemany(
            "INSERT INTO policy_chunks (section, title, content, search) VALUES"
            " (%(section)s, %(title)s, %(content)s,"
            "  to_tsvector('portuguese', unaccent(%(title)s || ' ' || %(content)s)))",
            policies,
        )
        print(f"policy_chunks: {len(policies)} rows")


if __name__ == "__main__":
    try:
        main()
    finally:
        get_pool().close()
