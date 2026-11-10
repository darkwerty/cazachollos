import os

import altair as alt
import streamlit as st

from src.web.access import allowed_emails, can_enter
from src.web.db_sync import get_deals_today, get_recent_deals, get_total_deals, search_deals

st.set_page_config(page_title="CazaChollos", page_icon="🛍️", layout="wide")

# En Azure el login (Google) lo hace Container Apps; aquí solo se mira si ese correo puede entrar
if not can_enter(st.context.headers, allowed_emails(os.getenv("ALLOWED_EMAILS", ""))):
    st.error("Esta cuenta no tiene acceso al panel.")
    st.markdown("[Entrar con otra cuenta](/.auth/logout?post_logout_redirect_uri=/)")
    st.stop()
st.title("🛍️ CazaChollos")

COLUMN_CONFIG = {
    "title": st.column_config.TextColumn("Oferta", width="large"),
    "url": st.column_config.LinkColumn("Enlace"),
    "price_sale": st.column_config.NumberColumn("Precio", format="%.2f €"),
    "price_before": st.column_config.NumberColumn("Antes", format="%.2f €"),
    "discount_percentage": st.column_config.NumberColumn("Dto.", format="%d %%"),
    "shop": "Tienda",
    "source": "Canal",
    "category": "Categoría",
    "chollo_score": st.column_config.ProgressColumn("Puntuación", min_value=0, max_value=100),
    "created_at": st.column_config.DatetimeColumn("Recibida", format="DD/MM/YYYY HH:mm"),
    "relevancia": None,  # se ordena por ella, pero no se enseña
}

try:
    total, today = get_total_deals(), get_deals_today()
except Exception as e:
    st.error(f"No se puede conectar con la base de datos: {e}")
    st.stop()

c1, c2 = st.columns(2)
c1.metric("Ofertas guardadas", total)
c2.metric("Recibidas hoy", today)

st.divider()

q = st.text_input("Buscar ofertas", placeholder='auriculares sony, "freidora de aire", portátil -reacondicionado')
try:
    if q.strip():
        df = search_deals(q.strip())
        st.subheader(f"{len(df)} resultados para «{q.strip()}»")
    else:
        df = get_recent_deals(limit=50)
        st.subheader("Últimas ofertas")
except Exception as e:
    st.error(f"Error al cargar las ofertas: {e}")
    st.stop()

if df.empty:
    st.info("No hay ofertas que mostrar." if q.strip() else "Todavía no hay ofertas en la base de datos.")
else:
    left, right = st.columns([1, 2])
    with left:
        chart = (
            alt.Chart(df)
            .mark_bar()
            .encode(
                x=alt.X("count()", title="Ofertas"),
                y=alt.Y("category", sort="-x", title=None),
                color=alt.Color("category", legend=None),
                tooltip=["category", "count()"],
            )
            .properties(title="Por categoría")
        )
        st.altair_chart(chart, use_container_width=True)
    with right:
        st.dataframe(df, column_config=COLUMN_CONFIG, hide_index=True)

if st.sidebar.button("Actualizar"):
    st.rerun()
