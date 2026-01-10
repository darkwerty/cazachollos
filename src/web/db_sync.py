import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def get_sync_engine():
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "secret")
    host = os.getenv("POSTGRES_HOST", "localhost") # Default to localhost for local run
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "cazachollos")
    
    # Use psycopg2 driver
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url)

def get_total_deals():
    engine = get_sync_engine()
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM deals"))
        return result.scalar()

def get_deals_today():
    engine = get_sync_engine()
    with engine.connect() as conn:
        # Postgres specific 'now()::date'
        result = conn.execute(text("SELECT COUNT(*) FROM deals WHERE created_at >= current_date"))
        return result.scalar()

def get_recent_deals(limit=50):
    engine = get_sync_engine()
    query = f"SELECT title, price_sale, price_before, shop, source, currency, chollo_score, category, url, created_at, raw_text FROM deals ORDER BY created_at DESC LIMIT {limit}"
    return pd.read_sql(query, engine)
