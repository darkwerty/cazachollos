import streamlit as st
import pandas as pd
import altair as alt
from src.web.db_sync import get_total_deals, get_deals_today, get_recent_deals

st.set_page_config(
    page_title="CazaChollos Dashboard", 
    page_icon="🛍️",
    layout="wide"
)

st.title("🛍️ CazaChollos Monitor")

# -- Metrics Section --
try:
    total = get_total_deals()
    today = get_deals_today()
except Exception as e:
    st.error(f"Database Connection Error: {e}")
    total = 0
    today = 0

col1, col2, col3 = st.columns(3)
with col1:
    st.metric(label="Total Chollos", value=total)
with col2:
    st.metric(label="Ingested Today", value=today, delta="Today")

st.markdown("---")

# -- Charts & Data --
st.subheader("Latest Activity")

try:
    df = get_recent_deals(limit=50)
    
    if not df.empty:
        # Category Chart
        chart = alt.Chart(df).mark_bar().encode(
            x='count()',
            y=alt.Y('category', sort='-x'),
            color='category',
            tooltip=['category', 'count()']
        ).properties(title="Distribución por Categoría (Top 50)")
        
        c1, c2 = st.columns([1, 2])
        
        with c1:
            st.altair_chart(chart, use_container_width=True)
            
        with c2:
            st.dataframe(
                df,
                column_config={
                    "url": st.column_config.LinkColumn("Link"),
                    "price_sale": st.column_config.NumberColumn("Price", format="%.2f €"),
                    "price_before": st.column_config.NumberColumn("Price Before", format="%.2f €"),
                    "shop": "Shop",
                    "source": "Source",
                    "chollo_score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100),
                    "raw_text": st.column_config.TextColumn("Raw Text", width="small")
                },
                hide_index=True
            )
    else:
        st.info("No deals found in database yet.")

except Exception as e:
    st.error(f"Error loading data: {e}")

st.sidebar.info("CazaChollos Admin v0.1")
if st.sidebar.button("Refresh Data"):
    st.rerun()
