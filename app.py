"""
app.py
Streamlit-based GenAI-Powered Text-to-SQL Business Intelligence Dashboard.
Production-grade UI with automated visualization, schema explorer, and
robust error handling.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Import project modules
from database import DatabaseManager, DBConfig
from ai_agent import SQLAgent, LLMConfig

# Configure page
st.set_page_config(
    page_title="GenAI BI Dashboard",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
logger = logging.getLogger("app")

# ============================================================
# CSS Styling
# ============================================================
CUSTOM_CSS = """
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1f2937;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #6b7280;
        margin-bottom: 2rem;
    }
    .sql-banner {
        background-color: #f3f4f6;
        border-left: 4px solid #3b82f6;
        padding: 1rem;
        border-radius: 0.5rem;
        font-family: 'Courier New', monospace;
        font-size: 0.9rem;
        color: #1f2937;
        margin: 1rem 0;
    }
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e5e7eb;
        border-radius: 0.75rem;
        padding: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .stAlert {
        border-radius: 0.5rem;
    }
    div[data-testid="stSidebarContent"] {
        background-color: #f9fafb;
    }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ============================================================
# Session State Management
# ============================================================
def init_session_state() -> None:
    """Initialize Streamlit session state variables."""
    defaults = {
        "db_manager": None,
        "sql_agent": None,
        "last_query": None,
        "last_results": None,
        "schema_loaded": False,
        "error_count": 0,
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
    """
    Initialize and cache the database manager.
    Uses SQLite by default for local testing.
    """
    config = DBConfig(
        db_type="sqlite",
        db_path="bi_dashboard.db"
    )
    db = DatabaseManager(config)
    
    # Initialize schema if database is empty/new
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
    Auto-detects GROQ_API_KEY and falls back gracefully.
    """
    # Priority: Groq (free/fast) > OpenAI > Gemini
    if os.getenv("GROQ_API_KEY"):
        config = LLMConfig(
            provider="groq",
            model="llama-3.3-70b-versatile",
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=0.0
        )
    elif os.getenv("OPENAI_API_KEY"):
        config = LLMConfig(
            provider="openai",
            model="gpt-4o-mini",
            api_key=os.getenv("OPENAI_API_KEY")
        )
    elif os.getenv("GOOGLE_API_KEY"):
        config = LLMConfig(
            provider="gemini",
            model="gemini-1.5-flash",
            api_key=os.getenv("GOOGLE_API_KEY")
        )
    else:
        # Default to Groq so the error message from ai_agent.py is explicit
        config = LLMConfig(provider="groq")

    return SQLAgent(config)


# ============================================================
# Schema Sidebar Component
# ============================================================
def render_schema_sidebar(db_manager: DatabaseManager) -> None:
    """
    Render the database schema explorer in the sidebar.
    
    Args:
        db_manager: Initialized DatabaseManager instance.
    """
    st.sidebar.markdown("## 📊 Database Schema")
    st.sidebar.markdown("---")
    
    try:
        metadata = db_manager.get_tables_metadata()
        
        for table_name, columns in metadata.items():
            with st.sidebar.expander(f"📋 `{table_name}`", expanded=False):
                for col in columns:
                    pk_badge = " 🔑" if col.get("pk") else ""
                    nullable = "NULL" if col.get("nullable") else "NOT NULL"
                    st.sidebar.markdown(
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
# Auto-Visualization Logic
# ============================================================
def auto_visualize(df: pd.DataFrame, query: str) -> Optional[go.Figure]:
    """
    Automatically generate an appropriate Plotly chart based on DataFrame structure.
    
    Args:
        df: Query result DataFrame.
        query: The SQL query that produced the data.
        
    Returns:
        Plotly Figure object or None if no suitable chart found.
    """
    if df.empty or len(df) == 0:
        return None
    
    numeric_cols = df.select_dtypes(include=["number"]).columns.tolist()
    categorical_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
    date_cols = df.select_dtypes(include=["datetime64"]).columns.tolist()
    
    # Try to infer chart type from data structure
    fig = None
    
    # Case 1: Single numeric column + single categorical -> Bar chart
    if len(numeric_cols) == 1 and len(categorical_cols) == 1 and len(df) <= 20:
        fig = px.bar(
            df,
            x=categorical_cols[0],
            y=numeric_cols[0],
            title=f"{numeric_cols[0]} by {categorical_cols[0]}",
            color=categorical_cols[0],
            template="plotly_white"
        )
        fig.update_layout(showlegend=False)
    
    # Case 2: Two numeric columns -> Scatter plot
    elif len(numeric_cols) == 2 and len(df) > 1:
        fig = px.scatter(
            df,
            x=numeric_cols[0],
            y=numeric_cols[1],
            title=f"{numeric_cols[1]} vs {numeric_cols[0]}",
            template="plotly_white",
            trendline="ols" if len(df) > 3 else None
        )
    
    # Case 3: Single numeric column, no categorical -> Pie chart (if few rows)
    elif len(numeric_cols) == 1 and len(categorical_cols) == 0 and len(df) <= 10:
        fig = px.pie(
            df,
            values=numeric_cols[0],
            names=df.index.astype(str),
            title=f"Distribution of {numeric_cols[0]}",
            template="plotly_white"
        )
    
    # Case 4: Date column + numeric -> Line chart (time series)
    elif len(date_cols) >= 1 and len(numeric_cols) >= 1:
        fig = px.line(
            df,
            x=date_cols[0],
            y=numeric_cols[0],
            title=f"{numeric_cols[0]} over Time",
            template="plotly_white",
            markers=True
        )
    
    # Case 5: Multiple numeric columns -> Grouped bar or area
    elif len(numeric_cols) > 1 and len(categorical_cols) >= 1:
        fig = px.bar(
            df,
            x=categorical_cols[0],
            y=numeric_cols,
            title=f"Comparison across {categorical_cols[0]}",
            template="plotly_white",
            barmode="group"
        )
    
    # Case 6: Single numeric, many rows -> Histogram
    elif len(numeric_cols) == 1 and len(df) > 20:
        fig = px.histogram(
            df,
            x=numeric_cols[0],
            title=f"Distribution of {numeric_cols[0]}",
            template="plotly_white",
            nbins=20
        )
    
    if fig:
        fig.update_layout(
            margin=dict(l=40, r=40, t=60, b=40),
            title_x=0.5,
            font=dict(size=12)
        )
    
    return fig


# ============================================================
# Query History Component
# ============================================================
def render_query_history() -> None:
    """Render the query history in the sidebar."""
    if st.session_state.query_history:
        st.sidebar.markdown("## 🕐 Recent Queries")
        for idx, item in enumerate(reversed(st.session_state.query_history[-5:])):
            with st.sidebar.expander(f"Q{len(st.session_state.query_history)-idx}", expanded=False):
                st.sidebar.markdown(f"**Question:** {item['question']}")
                st.sidebar.markdown(f"```sql\n{item['sql']}\n```")
                st.sidebar.markdown(f"**Rows:** {item['rows']}")


# ============================================================
# Main Application
# ============================================================
def main() -> None:
    """Main Streamlit application entry point."""
    init_session_state()
    
    # Initialize backend
    try:
        db_manager = get_database_manager()
        sql_agent = get_sql_agent()
        st.session_state.schema_loaded = True
    except Exception as e:
        st.error(f"🔴 System Initialization Failed: {e}")
        st.info("Please ensure your API keys are configured and schema.sql is present.")
        return
    
    # ============================================================
    # Sidebar
    # ============================================================
    st.sidebar.markdown("# 🧠 GenAI BI Dashboard")
    st.sidebar.markdown("---")
    
    # Schema Explorer
    render_schema_sidebar(db_manager)
    render_query_history()
    
    # Settings
    st.sidebar.markdown("---")
    st.sidebar.markdown("## ⚙️ Settings")
    
    provider = sql_agent.config.provider.upper()
    model = sql_agent.config.model
    st.sidebar.markdown(f"**LLM:** {provider} `{model}`")
    st.sidebar.markdown(f"**DB:** SQLite `bi_dashboard.db`")
    
    # ============================================================
    # Main Content
    # ============================================================
    st.markdown('<div class="main-header">🧠 GenAI-Powered BI Dashboard</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Ask questions in plain English. '
        'The AI generates SQL, queries your database, and visualizes results instantly.</div>',
        unsafe_allow_html=True
    )
    
    # Quick suggestion chips
    st.markdown("**Try asking:**")
    col1, col2, col3, col4 = st.columns(4)
    suggestions = [
        "Show total revenue by product category",
        "Who are the top 5 customers by total spending?",
        "What is the average order value per month?",
        "Which products have low stock and high sales?"
    ]
    
    selected_suggestion = None
    with col1:
        if st.button(suggestions[0], use_container_width=True):
            selected_suggestion = suggestions[0]
    with col2:
        if st.button(suggestions[1], use_container_width=True):
            selected_suggestion = suggestions[1]
    with col3:
        if st.button(suggestions[2], use_container_width=True):
            selected_suggestion = suggestions[2]
    with col4:
        if st.button(suggestions[3], use_container_width=True):
            selected_suggestion = suggestions[3]
    
    st.markdown("---")
    
    # ============================================================
    # Query Input
    # ============================================================
    default_value = selected_suggestion if selected_suggestion else ""
    
    user_question = st.text_input(
        "Ask your database a question in plain English",
        value=default_value,
        placeholder="e.g., What are the top 3 best-selling products by revenue?",
        key="user_query_input"
    )
    
    col_submit, col_clear = st.columns([1, 6])
    with col_submit:
        submit_clicked = st.button("🚀 Execute Query", type="primary", use_container_width=True)
    with col_clear:
        if st.button("🔄 Clear Results", use_container_width=False):
            st.session_state.last_query = None
            st.session_state.last_results = None
            st.rerun()
    
    # ============================================================
    # Query Execution Pipeline
    # ============================================================
    if submit_clicked and user_question.strip():
        with st.spinner("🧠 AI is analyzing your question and generating SQL..."):
            try:
                # Step 1: Get schema context
                schema_ddl = db_manager.get_schema_ddl()
                
                # Step 2: Generate SQL via LLM
                generated_sql = sql_agent.generate_sql(
                    question=user_question,
                    schema_ddl=schema_ddl,
                    dialect="SQLite"
                )
                
                # Step 3: Validate generated SQL
                validation = sql_agent.validate_sql_syntax(generated_sql)
                if not validation["valid"]:
                    st.warning(f"⚠️ SQL Validation Warning: {', '.join(validation['issues'])}")
                
                # Step 4: Execute query safely
                results_df = db_manager.execute_query(generated_sql)
                
                # Step 5: Store in session and history
                st.session_state.last_query = generated_sql
                st.session_state.last_results = results_df
                
                st.session_state.query_history.append({
                    "question": user_question,
                    "sql": generated_sql,
                    "rows": len(results_df)
                })
                
            except ValueError as ve:
                st.error(f"🚫 Security Block: {ve}")
                logger.warning(f"Security block for query: {user_question}")
                return
            except RuntimeError as re:
                st.error(f"❌ Execution Error: {re}")
                logger.error(f"Execution error: {re}")
                return
            except Exception as e:
                st.error(f"💥 Unexpected Error: {e}")
                logger.exception("Unexpected error in query pipeline")
                return
    
    # ============================================================
    # Results Display
    # ============================================================
    if st.session_state.last_query and st.session_state.last_results is not None:
        st.markdown("---")
        
        # Display generated SQL
        st.markdown("### 📝 Generated SQL Query")
        st.markdown(
            f'<div class="sql-banner"><code>{st.session_state.last_query}</code></div>',
            unsafe_allow_html=True
        )
        
        results_df = st.session_state.last_results
        
        # Metrics row
        st.markdown("### 📈 Query Results")
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Rows Returned", len(results_df))
        with m2:
            st.metric("Columns", len(results_df.columns))
        with m3:
            st.metric("Execution", "✅ Success")
        
        # Data table
        st.dataframe(
            results_df,
            use_container_width=True,
            hide_index=True,
            height=min(400, 35 + len(results_df) * 35)
        )
        
        # Download button
        csv = results_df.to_csv(index=False)
        st.download_button(
            label="📥 Download Results as CSV",
            data=csv,
            file_name="query_results.csv",
            mime="text/csv",
            use_container_width=False
        )
        
        # Auto-visualization
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


# ============================================================
# Entry Point
# ============================================================
if __name__ == "__main__":
    main()