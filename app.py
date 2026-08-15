"""
app.py
Streamlit-based GenAI-Powered Text-to-SQL Business Intelligence Dashboard.
Theme-aware CSS for professional light/dark mode compatibility.
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

import streamlit as st

# Try to load .env for local development (optional — won't crash if not installed)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ModuleNotFoundError:
    pass

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from database import DatabaseManager, DBConfig
from ai_agent import SQLAgent, LLMConfig

# Configure page
st.set_page_config(
    page_title="GenAI BI Dashboard",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
logger = logging.getLogger("app")

# ============================================================
# THEME-AWARE CSS — Works in Light & Dark Mode
# ============================================================
CUSTOM_CSS = """
<style>
    /* Headers inherit theme color so they flip white/black automatically */
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        margin-bottom: 0.5rem;
        color: inherit;
    }
    .sub-header {
        font-size: 1.1rem;
        margin-bottom: 2rem;
        opacity: 0.75;
        color: inherit;
    }

    /* SQL banner: subtle tinted background that works on both themes */
    .sql-banner {
        background-color: rgba(128, 128, 128, 0.12);
        border-left: 4px solid #ff4b4b;
        padding: 1rem;
        border-radius: 0.5rem;
        font-family: 'Courier New', monospace;
        font-size: 0.9rem;
        color: inherit;
        margin: 1rem 0;
    }

    /* Metric card: translucent so theme shows through */
    .metric-card {
        background-color: rgba(128, 128, 128, 0.06);
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 0.75rem;
        padding: 1rem;
    }

    /* REMOVE forced white sidebar background — let Streamlit theme handle it */
    div[data-testid="stSidebarContent"] {
        background-color: transparent !important;
    }

    /* Ensure sidebar text inherits theme color properly */
    section[data-testid="stSidebar"] {
        color: inherit;
    }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ============================================================
# Session State Management
# ============================================================
def init_session_state() -> None:
    defaults = {
        "db_manager": None,
        "sql_agent": None,
        "last_query": None,
        "last_results": None,
        "schema_loaded": False,
        "query_history": []
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ============================================================
# Database Initialization
# ============================================================
@st.cache_resource
def get_database_manager() -> DatabaseManager:
    config = DBConfig(db_type="sqlite", db_path="bi_dashboard.db")
    db = DatabaseManager(config)
    schema_path = Path("schema.sql")
    if schema_path.exists():
        try:
            db.initialize_from_schema(schema_path)
        except Exception as e:
            logger.warning(f"Schema initialization note: {e}")
    return db


# ============================================================
# LLM Agent Initialization
# ============================================================
@st.cache_resource
def get_sql_agent() -> SQLAgent:
    """
    Initialize and cache the SQL agent.
    Reads API key from: Streamlit Secrets > .env / Environment Variable
    """
    groq_key = None

    # 1. Streamlit Cloud Secrets
    try:
        groq_key = st.secrets["GROQ_API_KEY"]
    except (KeyError, FileNotFoundError):
        pass

    # 2. Local environment / .env
    if not groq_key:
        groq_key = os.environ.get("GROQ_API_KEY")

    # 3. Hard stop with clear instructions
    if not groq_key:
        st.error(
            "🔴 **Groq API Key Missing**\n\n"
            "**For Local VS Code:**\n"
            "1. Run: `pip install python-dotenv`\n"
            "2. Create a `.env` file in your project folder with:\n"
            "   `GROQ_API_KEY=gsk_your_key_here`\n\n"
            "**For Streamlit Cloud:**\n"
            "Go to Manage app → Secrets → Add `GROQ_API_KEY = \"gsk_your_key_here\"`"
        )
        st.stop()

    groq_key = groq_key.strip().strip('"').strip("'")

    config = LLMConfig(
        provider="groq",
        model="llama-3.3-70b-versatile",
        api_key=groq_key,
        temperature=0.0
    )
    return SQLAgent(config)


# ============================================================
# Schema Sidebar Component
# ============================================================
def render_schema_sidebar(db_manager: DatabaseManager) -> None:
    st.sidebar.markdown("## 📊 Database Schema")
    st.sidebar.markdown("---")

    try:
        metadata = db_manager.get_tables_metadata()
        for table_name, columns in metadata.items():
            with st.sidebar.expander(f"📋 `{table_name}`", expanded=False):
                for col in columns:
                    pk_badge = " 🔑" if col.get("pk") else ""
                    nullable = "NULL" if col.get("nullable") else "NOT NULL"
                    st.markdown(
                        f"• `{col['name']}` `{col['type']}` *{nullable}*{pk_badge}"
                    )

        st.sidebar.markdown("---")
        st.sidebar.info(
            "💡 The AI agent uses this schema to generate accurate SQL queries. "
            "Ask questions about users, products, orders, and their relationships."
        )

    except Exception as e:
        st.sidebar.error(f"Failed to load schema: {e}")


# ============================================================
# Query History Component
# ============================================================
def render_query_history() -> None:
    if st.session_state.query_history:
        st.sidebar.markdown("## 🕐 Recent Queries")
        for idx, item in enumerate(reversed(st.session_state.query_history[-5:])):
            q_num = len(st.session_state.query_history) - idx
            with st.sidebar.expander(f"Q{q_num}", expanded=False):
                st.markdown(f"**Question:** {item['question']}")
                st.markdown(f"```sql\n{item['sql']}\n```")
                st.markdown(f"**Rows returned:** {item['rows']}")


# ============================================================
# Auto-Visualization Logic
# ============================================================
def auto_visualize(df: pd.DataFrame, query: str) -> Optional[go.Figure]:
    if df.empty or len(df) == 0:
        return None

    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    categorical_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
    date_cols = df.select_dtypes(include=["datetime64"]).columns.tolist()

    fig = None

    if len(numeric_cols) == 1 and len(categorical_cols) == 1 and len(df) <= 20:
        fig = px.bar(
            df, x=categorical_cols[0], y=numeric_cols[0],
            title=f"{numeric_cols[0]} by {categorical_cols[0]}",
            color=categorical_cols[0], template="plotly_white"
        )
        fig.update_layout(showlegend=False)

    elif len(numeric_cols) == 2 and len(df) > 1:
        fig = px.scatter(
            df, x=numeric_cols[0], y=numeric_cols[1],
            title=f"{numeric_cols[1]} vs {numeric_cols[0]}",
            template="plotly_white"
        )

    elif len(date_cols) >= 1 and len(numeric_cols) >= 1:
        fig = px.line(
            df, x=date_cols[0], y=numeric_cols[0],
            title=f"{numeric_cols[0]} over Time",
            template="plotly_white", markers=True
        )

    elif len(numeric_cols) > 1 and len(categorical_cols) >= 1:
        fig = px.bar(
            df, x=categorical_cols[0], y=numeric_cols,
            title=f"Comparison across {categorical_cols[0]}",
            template="plotly_white", barmode="group"
        )

    elif len(numeric_cols) == 1 and len(df) > 20:
        fig = px.histogram(
            df, x=numeric_cols[0],
            title=f"Distribution of {numeric_cols[0]}",
            template="plotly_white", nbins=20
        )

    if fig:
        fig.update_layout(
            margin=dict(l=40, r=40, t=60, b=40),
            title_x=0.5,
            font=dict(size=12)
        )
    return fig


# ============================================================
# Main Application
# ============================================================
def main() -> None:
    init_session_state()

    try:
        db_manager = get_database_manager()
        sql_agent = get_sql_agent()
        st.session_state.schema_loaded = True
    except Exception as e:
        st.error(f"🔴 System Initialization Failed: {e}")
        return

    # Sidebar
    st.sidebar.markdown("# 🧠 GenAI BI Dashboard")
    st.sidebar.markdown("---")
    render_schema_sidebar(db_manager)
    render_query_history()

    st.sidebar.markdown("---")
    st.sidebar.markdown("## ⚙️ Settings")
    st.sidebar.markdown("**LLM:** Groq `llama-3.3-70b-versatile`")
    st.sidebar.markdown("**DB:** SQLite `bi_dashboard.db`")

    # Main Content
    st.markdown('<div class="main-header">🧠 GenAI-Powered BI Dashboard</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Ask questions in plain English. '
        'The AI generates SQL, queries your database, and visualizes results instantly.</div>',
        unsafe_allow_html=True
    )

    # Suggestion chips
    st.markdown("**Try asking:**")
    c1, c2, c3, c4 = st.columns(4)
    suggestions = [
        "Show total revenue by product category",
        "Who are the top 5 customers by total spending?",
        "What is the average order value per month?",
        "Which products have low stock and high sales?"
    ]
    selected = None
    with c1:
        if st.button(suggestions[0], use_container_width=True):
            selected = suggestions[0]
    with c2:
        if st.button(suggestions[1], use_container_width=True):
            selected = suggestions[1]
    with c3:
        if st.button(suggestions[2], use_container_width=True):
            selected = suggestions[2]
    with c4:
        if st.button(suggestions[3], use_container_width=True):
            selected = suggestions[3]

    st.markdown("---")

    # Query Input
    default_val = selected if selected else ""
    user_question = st.text_input(
        "Ask your database a question in plain English",
        value=default_val,
        placeholder="e.g., What are the top 3 best-selling products by revenue?",
        key="user_query_input"
    )

    c_submit, c_clear = st.columns([1, 6])
    with c_submit:
        submit_clicked = st.button("🚀 Execute Query", type="primary", use_container_width=True)
    with c_clear:
        if st.button("🔄 Clear Results", use_container_width=False):
            st.session_state.last_query = None
            st.session_state.last_results = None
            st.rerun()

    # Query Execution Pipeline
    if submit_clicked and user_question.strip():
        with st.spinner("🧠 AI is analyzing your question and generating SQL..."):
            try:
                schema_ddl = db_manager.get_schema_ddl()
                generated_sql = sql_agent.generate_sql(
                    question=user_question,
                    schema_ddl=schema_ddl,
                    dialect="SQLite"
                )

                validation = sql_agent.validate_sql_syntax(generated_sql)
                if not validation["valid"]:
                    st.warning(f"⚠️ SQL Validation Warning: {', '.join(validation['issues'])}")

                results_df = db_manager.execute_query(generated_sql)

                st.session_state.last_query = generated_sql
                st.session_state.last_results = results_df
                st.session_state.query_history.append({
                    "question": user_question,
                    "sql": generated_sql,
                    "rows": len(results_df)
                })

            except ValueError as ve:
                st.error(f"🚫 Security Block: {ve}")
                return
            except RuntimeError as re:
                st.error(f"❌ Execution Error: {re}")
                return
            except Exception as e:
                st.error(f"💥 Unexpected Error: {e}")
                return

    # Results Display
    if st.session_state.last_query and st.session_state.last_results is not None:
        st.markdown("---")
        st.markdown("### 📝 Generated SQL Query")
        st.markdown(
            f'<div class="sql-banner"><code>{st.session_state.last_query}</code></div>',
            unsafe_allow_html=True
        )

        results_df = st.session_state.last_results
        st.markdown("### 📈 Query Results")
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Rows Returned", len(results_df))
        with m2:
            st.metric("Columns", len(results_df.columns))
        with m3:
            st.metric("Execution", "✅ Success")

        st.dataframe(
            results_df,
            use_container_width=True,
            hide_index=True,
            height=min(400, 35 + len(results_df) * 35)
        )

        csv = results_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Results as CSV",
            data=csv,
            file_name="query_results.csv",
            mime="text/csv"
        )

        st.markdown("---")
        st.markdown("### 📊 Auto-Generated Visualization")
        fig = auto_visualize(results_df, st.session_state.last_query)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(
                "ℹ️ No automatic visualization available for this data structure. "
                "The results are best viewed in the table above."
            )


if __name__ == "__main__":
    main()