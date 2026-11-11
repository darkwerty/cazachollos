"""Deals for the web: filters, sorting and pages, in one parametrised SQL query (no string-built user input)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from sqlalchemy import text

from src.infrastructure.db.session import AsyncSessionLocal

PAGE_SIZE = 24

# Discount even when only the two prices were stored
DISCOUNT = (
    "COALESCE(d.discount_percentage, CASE WHEN d.price_before > d.price_sale AND d.price_before > 0 "
    "THEN FLOOR((d.price_before - d.price_sale) * 100 / d.price_before)::int END)"
)
SORTS = {
    "recientes": "d.created_at DESC",
    "puntuacion": "d.chollo_score DESC, d.created_at DESC",
    "descuento": "discount DESC NULLS LAST, d.created_at DESC",
    "precio_asc": "d.price_sale ASC NULLS LAST, d.created_at DESC",
    "precio_desc": "d.price_sale DESC NULLS LAST, d.created_at DESC",
    "relevancia": "rank DESC, d.chollo_score DESC",
}
SORT_LABELS = {
    "recientes": "Más recientes",
    "puntuacion": "Mejor puntuación",
    "descuento": "Mayor descuento",
    "precio_asc": "Precio más bajo",
    "precio_desc": "Precio más alto",
    "relevancia": "Más relevantes",
}


@dataclass
class Filters:
    q: str = ""
    category: str = ""
    shop: str = ""
    channel: str = ""
    min_discount: int = 0
    max_price: Decimal | None = None
    sort: str = "recientes"
    page: int = 1

    def normalised(self) -> Filters:
        sort = self.sort if self.sort in SORTS else "recientes"
        if sort == "relevancia" and not self.q:
            sort = "recientes"
        return Filters(
            q=" ".join(self.q.split())[:100],
            category=self.category[:30],
            shop=self.shop[:100],
            channel=self.channel[:100],
            min_discount=max(0, min(95, self.min_discount)),
            max_price=self.max_price if self.max_price is None or self.max_price >= 0 else None,
            sort=sort,
            page=max(1, min(200, self.page)),
        )


@dataclass
class DealCard:
    id: str
    title: str
    url: str
    price: Decimal | None
    before: Decimal | None
    discount: int | None
    shop: str | None
    channel: str | None
    category: str
    score: int
    image_url: str | None
    post_url: str | None
    created_at: datetime


@dataclass
class Page:
    deals: list[DealCard]
    total: int
    filters: Filters
    categories: list[tuple[str, int]] = field(default_factory=list)
    shops: list[str] = field(default_factory=list)
    channels: list[str] = field(default_factory=list)

    @property
    def has_more(self) -> bool:
        return self.filters.page * PAGE_SIZE < self.total


def where_clause(f: Filters, with_category: bool = True) -> tuple[str, dict]:
    """WHERE for the filters. Every user value travels as a bound parameter."""
    parts, params = ["TRUE"], {}
    if f.q:
        parts.append("d.search_vector @@ websearch_to_tsquery('spanish', :q)")
        params["q"] = f.q
    if with_category and f.category:
        parts.append("d.category = :category")
        params["category"] = f.category
    if f.shop:
        parts.append("d.shop = :shop")
        params["shop"] = f.shop
    if f.channel:
        parts.append("d.source = :channel")
        params["channel"] = f.channel
    if f.min_discount:
        parts.append(f"{DISCOUNT} >= :min_discount")
        params["min_discount"] = f.min_discount
    if f.max_price is not None:
        parts.append("d.price_sale <= :max_price")
        params["max_price"] = f.max_price
    return " AND ".join(parts), params


async def find_deals(filters: Filters) -> Page:
    f = filters.normalised()
    where, params = where_clause(f)
    rank = "ts_rank(d.search_vector, websearch_to_tsquery('spanish', :q))" if f.q else "0"
    sql = text(
        f"SELECT d.id, d.title, d.url, d.price_sale, d.price_before, {DISCOUNT} AS discount, d.shop, d.source, "
        f"d.category, d.chollo_score, d.image_url, d.post_url, d.created_at, {rank} AS rank "
        f"FROM deals d WHERE {where} ORDER BY {SORTS[f.sort]} LIMIT :limit OFFSET :offset"
    )
    cat_where, cat_params = where_clause(f, with_category=False)
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(sql, {**params, "limit": PAGE_SIZE, "offset": (f.page - 1) * PAGE_SIZE})).all()
        total = (await session.execute(text(f"SELECT COUNT(*) FROM deals d WHERE {where}"), params)).scalar() or 0
        categories = (
            await session.execute(
                text(f"SELECT d.category, COUNT(*) FROM deals d WHERE {cat_where} GROUP BY 1 ORDER BY 2 DESC"),
                cat_params,
            )
        ).all()
        shops = (
            await session.execute(
                text("SELECT shop FROM deals WHERE shop IS NOT NULL GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 30")
            )
        ).scalars()
        channels = (
            await session.execute(
                text("SELECT source FROM deals WHERE source IS NOT NULL GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 30")
            )
        ).scalars()
        shops, channels = list(shops), list(channels)
    deals = [
        DealCard(
            id=str(r.id),
            title=r.title,
            url=r.url,
            price=r.price_sale,
            before=r.price_before,
            discount=r.discount,
            shop=r.shop,
            channel=r.source,
            category=r.category or "otros",
            score=r.chollo_score,
            image_url=r.image_url,
            post_url=r.post_url,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return Page(deals, total, f, [(c, n) for c, n in categories], shops, channels)
