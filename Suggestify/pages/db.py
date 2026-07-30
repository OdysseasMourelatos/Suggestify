# db.py

import streamlit as st
import pandas as pd
import datetime
from sqlalchemy import create_engine, text

try:
    CONNECTION_STRING = st.secrets["DATABASE_URL"]
except KeyError:
    CONNECTION_STRING = "postgresql://postgres.pxpplxyszvrzubdqykmw:dKPJjO2jZtkmwjYh@aws-0-eu-west-1.pooler.supabase.com:6543/postgres?sslmode=require"

@st.cache_resource
def get_engine():
    return create_engine(CONNECTION_STRING, pool_pre_ping=True, pool_size=5)

@st.cache_data(ttl=3600, show_spinner=False)
def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})

@st.cache_data(ttl=3600, show_spinner=False)
def run_rating_query(sql: str, params: dict | None = None, cache_gen: int = 0) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})

@st.cache_data(ttl=600, show_spinner=False)
def get_date_bounds() -> tuple[datetime.date, datetime.date]:
    df = run_query("SELECT MIN(played_at)::date AS mn, MAX(played_at)::date AS mx FROM streams;")
    if df.empty or pd.isnull(df["mn"].iloc[0]):
        return datetime.date(2023, 1, 1), datetime.date.today()
    return df["mn"].iloc[0], df["mx"].iloc[0]

@st.cache_data(ttl=3600, show_spinner=False)
def get_release_year_bounds() -> tuple[int, int]:
    df = run_query("SELECT MIN(EXTRACT(YEAR FROM release_date))::int AS mn, MAX(EXTRACT(YEAR FROM release_date))::int AS mx FROM songs WHERE release_date IS NOT NULL;")
    if df.empty or pd.isnull(df["mn"].iloc[0]):
        return 1960, datetime.date.today().year
    return int(df["mn"].iloc[0]), int(df["mx"].iloc[0])

@st.cache_resource
def _rating_cache_generations() -> dict:
    return {}

def get_rating_cache_gen(user_id: int) -> int:
    return _rating_cache_generations().get(user_id, 0)

def bump_rating_cache_gen(user_id: int) -> None:
    gens = _rating_cache_generations()
    gens[user_id] = gens.get(user_id, 0) + 1
    
def run_write_query(sql: str, params: dict | None = None):
    """Execute INSERT/UPDATE/DDL in a transaction. Returns fetched rows if the
    statement has a RETURNING clause (or SELECT), else None."""
    with get_engine().begin() as conn:
        result = conn.execute(text(sql), params or {})
        if result.returns_rows:
            return result.mappings().all()
        return None