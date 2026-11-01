import re

from langchain_core.tools import tool

from agent.store import store_status
from db.connection import get_pool

# Price with the active promotion applied. Per the store policy, promotions are not cumulative
# and the 5% PIX discount does not apply on top of promotional prices.
_PRODUCT_SELECT = """
    SELECT p.product_id, p.name, c.name AS category, p.description, p.price_brl,
           p.stock_quantity, p.status, p.specs,
           pr.discount_percent, pr.description AS promotion,
           round(p.price_brl * (1 - pr.discount_percent / 100), 2) AS promo_price_brl,
           CASE WHEN pr.promotion_id IS NULL THEN round(p.price_brl * 0.95, 2) END AS pix_price_brl
    FROM products p
    JOIN categories c USING (category_id)
    LEFT JOIN LATERAL (
        SELECT * FROM promotions
        WHERE product_id = p.product_id AND is_active
        ORDER BY discount_percent DESC LIMIT 1
    ) pr ON true
"""


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value)


@tool
def search_products(
    query: str = "",
    category: str = "",
    min_price: float | None = None,
    max_price: float | None = None,
    only_in_stock: bool = False,
) -> list[dict]:
    """Search the instrument catalog.

    Use it whenever the customer asks about products, prices, stock or promotions. Never state
    price or availability without calling this first. All filters are optional and combined.

    Args:
        query: words to look for in name, description and specs (e.g. "violão nylon yamaha").
        category: category name or part of it (e.g. "Guitarras", "Teclados").
        min_price: minimum price in BRL.
        max_price: maximum price in BRL.
        only_in_stock: if true, return only products with stock available.

    Returns up to 10 products with price, active promotion (if any), PIX price (only when there
    is no promotion), stock and status (active, discontinued or coming_soon).
    """
    where, params = ["true"], {}
    for i, word in enumerate(query.split()):
        where.append(
            f"unaccent(p.name || ' ' || coalesce(p.description, '') || ' ' || coalesce(p.specs::text, ''))"
            f" ILIKE unaccent(%(w{i})s)"
        )
        params[f"w{i}"] = f"%{word}%"
    if category:
        where.append("unaccent(c.name) ILIKE unaccent(%(category)s)")
        params["category"] = f"%{category}%"
    if min_price is not None:
        where.append("p.price_brl >= %(min_price)s")
        params["min_price"] = min_price
    if max_price is not None:
        where.append("p.price_brl <= %(max_price)s")
        params["max_price"] = max_price
    if only_in_stock:
        where.append("p.stock_quantity > 0 AND p.status = 'active'")

    sql = f"{_PRODUCT_SELECT} WHERE {' AND '.join(where)} ORDER BY p.status = 'active' DESC, p.price_brl LIMIT 10"
    with get_pool().connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return rows or [{"result": "Nenhum produto encontrado com esses filtros."}]


@tool
def get_product(product_id: int) -> dict:
    """Get full details of one product by id (specs, stock, status, promotion, PIX price)."""
    with get_pool().connection() as conn:
        row = conn.execute(f"{_PRODUCT_SELECT} WHERE p.product_id = %s", (product_id,)).fetchone()
    return row or {"result": f"Produto {product_id} não encontrado."}


@tool
def list_active_promotions() -> list[dict]:
    """List all promotions currently active, with original and promotional price."""
    sql = f"""
        SELECT * FROM ({_PRODUCT_SELECT}) x
        WHERE promotion IS NOT NULL AND status = 'active'
        ORDER BY discount_percent DESC
    """
    with get_pool().connection() as conn:
        rows = conn.execute(sql).fetchall()
    return [
        {k: r[k] for k in ("product_id", "name", "price_brl", "discount_percent", "promotion",
                           "promo_price_brl", "stock_quantity")}
        for r in rows
    ] or [{"result": "Não há promoções ativas no momento."}]


@tool
def get_order_status(order_id: int, customer_email_or_phone: str) -> dict:
    """Look up an order (status, tracking code, delivery estimate, items).

    Orders are private: always ask the customer for the e-mail or phone registered on the order
    and pass it here. If it does not match, nothing is returned.

    Args:
        order_id: the order number.
        customer_email_or_phone: e-mail or phone of the customer who placed the order.
    """
    sql = """
        SELECT o.order_id, o.order_date, o.status, o.total_brl, o.payment_method,
               o.tracking_code, o.estimated_delivery, o.notes, c.name AS customer_name, c.email, c.phone
        FROM orders o JOIN customers c USING (customer_id)
        WHERE o.order_id = %s
    """
    items_sql = """
        SELECT p.name, i.quantity FROM order_items i JOIN products p USING (product_id)
        WHERE i.order_id = %s ORDER BY i.id
    """
    with get_pool().connection() as conn:
        order = conn.execute(sql, (order_id,)).fetchone()
        given = customer_email_or_phone.strip().lower()
        matches = order and (
            given == (order["email"] or "").lower()
            or (_digits(given) and _digits(given)[-9:] == _digits(order["phone"] or "")[-9:])
        )
        if not matches:
            # same answer for "doesn't exist" and "not yours", so ids can't be probed
            return {"result": "Pedido não encontrado para esse e-mail/telefone."}
        order["items"] = conn.execute(items_sql, (order_id,)).fetchall()
    del order["email"], order["phone"]
    return order


@tool
def search_policies(question: str) -> list[dict]:
    """Search the store's policy manual.

    Use it for anything about shipping, delivery, returns/exchanges, warranty, payment methods and
    installments, store hours, address/contact, promotion rules, privacy and customer service rules.

    Args:
        question: the topic or question, in Portuguese (e.g. "prazo para devolução").

    Returns the most relevant manual sections.
    """
    with get_pool().connection() as conn:
        plain = conn.execute("SELECT unaccent(%s) AS q", (question.lower(),)).fetchone()["q"]
        # Prefix match on the first 5 letters, because the stemmer misses variations such as
        # devolver/devolução or rastrear/rastreamento.
        words = {w[:5] for w in re.findall(r"[a-z0-9]+", plain) if len(w) > 2}
        if not words:
            return [{"result": "Pergunta vazia."}]
        # OR between words: natural-language questions rarely match every term
        rows = conn.execute(
            """
            SELECT section, title, content, ts_rank(search, q) AS rank
            FROM policy_chunks, to_tsquery('portuguese', %s) q
            WHERE search @@ q
            ORDER BY rank DESC LIMIT 3
            """,
            (" | ".join(f"{w}:*" for w in sorted(words)),),
        ).fetchall()
    return [{"section": r["section"], "title": r["title"], "content": r["content"]} for r in rows] or [
        {"result": "Nada encontrado no manual de políticas. Encaminhe para um atendente."}
    ]


@tool
def get_store_status() -> dict:
    """Get the current date and time in Campo Grande and whether the store is open right now.

    Call it before saying whether the store is open, when it opens again, or that the team is
    unavailable. Opening hours: Mon-Fri 9h-18h, Sat 9h-13h, closed on Sunday.
    """
    return store_status()


TOOLS = [
    search_products,
    get_product,
    list_active_promotions,
    get_order_status,
    search_policies,
    get_store_status,
]
