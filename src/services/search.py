from typing import List
from sqlalchemy import select, text
from src.infrastructure.db.session import AsyncSessionLocal
from src.domain.models import Deal
from src.domain.schemas import DealRead

class SearchService:
    async def search_deals(self, query: str, limit: int = 5) -> List[DealRead]:
        async with AsyncSessionLocal() as session:
            # Prepare the TSQUERY
            # websearch_to_tsquery handles natural language better (operators like -, or, "")
            # We also rank by relevance
            
            sql_query = select(Deal).filter(
                text("search_vector @@ websearch_to_tsquery('spanish', :q)")
            ).order_by(
                text("ts_rank(search_vector, websearch_to_tsquery('spanish', :q)) DESC"),
                Deal.chollo_score.desc()
            ).limit(limit)

            result = await session.execute(sql_query, {"q": query})
            deals = result.scalars().all()
            
            return [DealRead.model_validate(deal) for deal in deals]
