<div align="center">

# 🧠 GenAI-Powered BI Dashboard

### Ask your database anything. In plain English.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://streamlit.io)
[![Groq](https://img.shields.io/badge/Groq-LLM%20API-F55036?style=for-the-badge)](https://groq.com)
[![SQLite](https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)
[![Plotly](https://img.shields.io/badge/Plotly-3F4F75?style=for-the-badge&logo=plotly&logoColor=white)](https://plotly.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

<br/>

> **Type a question. Get a SQL query. See the data. Visualized — instantly.**
>
> A full-stack AI data analyst that transforms natural language into SQL,
> executes it securely, and renders interactive charts — all in one click.

<br/>

![Dashboard Preview](https://placehold.co/900x450/1a1a2e/ffffff?text=GenAI+BI+Dashboard+Preview)

</div>

---

## 📌 Table of Contents

- [✨ Features](#-features)
- [🏗️ Architecture](#️-architecture)
- [🗃️ Database Schema](#️-database-schema)
- [⚙️ Tech Stack](#️-tech-stack)
- [🚀 Quick Start](#-quick-start)
- [☁️ Deploy on GitHub Codespaces](#️-deploy-on-github-codespaces)
- [🔐 Security Design](#-security-design)
- [📁 Project Structure](#-project-structure)
- [💡 Example Queries](#-example-queries)
- [🛠️ Configuration](#️-configuration)
- [📄 Documentation](#-documentation)

---

## ✨ Features

| Feature | Description |
|---|---|
| 🗣️ **Natural Language to SQL** | Ask questions in plain English — the AI generates optimized SQL automatically |
| 🤖 **LLM-Powered Agent** | Uses Groq API with `openai/gpt-oss-120b` for fast, accurate query generation |
| 📊 **Auto Visualization** | Intelligent chart selection (bar, scatter, line, histogram) based on query result shape |
| 🛡️ **Read-Only Security** | All queries pass through a strict blocklist filter — no DROP, DELETE, or ALTER ever executes |
| 🕐 **Query History** | Sidebar tracks your last 5 queries with their generated SQL and row counts |
| 📥 **CSV Export** | Download any query result as a CSV with one click |
| 🗺️ **Schema Explorer** | Sidebar shows live database schema — tables, columns, types, and primary keys |
| ⚡ **Groq-Speed Inference** | Sub-second LLM responses via Groq's hardware-accelerated inference API |
| 🐳 **Codespaces Ready** | One-click launch via `.devcontainer` — zero local setup required |
| 🔌 **Multi-DB Support** | Built for SQLite out of the box; architecture supports MySQL extension |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit Frontend (app.py)               │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │  User Input  │───▶│  SQL Agent   │───▶│  DB Manager   │  │
│  │ (Natural     │    │ (ai_agent.py)│    │(database.py)  │  │
│  │  Language)   │    │              │    │               │  │
│  └──────────────┘    └──────────────┘    └───────────────┘  │
│                             │                    │           │
│                    ┌────────▼───────┐   ┌────────▼────────┐ │
│                    │   Groq API     │   │  SQLite / MySQL │ │
│                    │ gpt-oss-120b   │   │  bi_dashboard   │ │
│                    └────────────────┘   └─────────────────┘ │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │           Auto-Visualization Engine (Plotly)          │   │
│  │  Bar Chart · Scatter Plot · Line Chart · Histogram   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**Request Flow:**
1. User types a question in plain English
2. `SQLAgent` builds a system prompt with the full database schema DDL
3. Groq API returns a raw SQL query
4. `_clean_sql_output()` strips markdown, backticks, and extracts the `SELECT` statement
5. `DatabaseManager._is_safe_query()` validates the query against the security blocklist
6. `pd.read_sql_query()` executes it and returns a DataFrame
7. `auto_visualize()` infers the best chart type and renders via Plotly

---

## 🗃️ Database Schema

The included sample database (`bi_dashboard.db`) models a simple e-commerce business with 3 tables and 30+ pre-seeded orders.

```sql
┌─────────────────────────────┐
│           users             │
├──────────────┬──────────────┤
│ id           │ PK, INTEGER  │
│ name         │ TEXT         │
│ email        │ UNIQUE TEXT  │
│ signup_date  │ DATE         │
└──────────────┴──────────────┘
         │
         │ user_id (FK)
         ▼
┌─────────────────────────────┐         ┌─────────────────────────────┐
│           orders            │         │          products            │
├──────────────┬──────────────┤         ├──────────────┬──────────────┤
│ id           │ PK, INTEGER  │         │ id           │ PK, INTEGER  │
│ user_id      │ FK → users   │         │ name         │ TEXT         │
│ product_id   │ FK → products│────────▶│ category     │ TEXT         │
│ order_date   │ DATE         │         │ price        │ DECIMAL      │
│ quantity     │ INTEGER      │         │ stock        │ INTEGER      │
│ total_amount │ DECIMAL      │         └──────────────┴──────────────┘
└──────────────┴──────────────┘
```

**Sample Data:**
- 👥 **10 Users** — realistic names and signup dates across 2023
- 📦 **10 Products** — spanning Electronics, Groceries, Home & Kitchen, Sports
- 🛒 **30 Orders** — distributed across all users and products with realistic amounts

---

## ⚙️ Tech Stack

```
Layer           Library/Tool            Purpose
──────────────────────────────────────────────────────────────
UI              Streamlit 1.28+         Web app framework
LLM             Groq API (gpt-oss-120b) Natural language → SQL
Visualization   Plotly Express          Interactive charts
Data            Pandas                  DataFrame operations
Database        SQLite (built-in)       Local persistent storage
Config          python-dotenv           Environment variable loading
Dev Container   GitHub Codespaces       Zero-setup cloud IDE
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- A free [Groq API key](https://console.groq.com)

### 1. Clone the repository

```bash
git clone https://github.com/your-username/ai-data-analyst.git
cd ai-data-analyst
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set your Groq API key

Create a `.env` file in the project root:

```env
GROQ_API_KEY=gsk_your_api_key_here
```

> **Get your free key** at [console.groq.com](https://console.groq.com) → API Keys → Create new key.

### 4. Run the app

```bash
streamlit run app.py
```

Open your browser at **http://localhost:8501** and start asking questions!

---

## ☁️ Deploy on GitHub Codespaces

This project includes a fully configured `.devcontainer` for instant cloud deployment with **zero local setup**.

1. Click **"Code" → "Codespaces" → "Create codespace on main"** on GitHub
2. Wait ~60 seconds for the environment to build and packages to install
3. The Streamlit app launches automatically on port `8501`
4. Add your Groq API key via **Codespace Secrets**:
   - Go to **Settings → Codespaces → Secrets** → `GROQ_API_KEY`

That's it. No Python installation, no pip, no local config.

---

## 🔐 Security Design

The `DatabaseManager` implements a **defense-in-depth** read-only enforcement layer:

```python
# Every query is checked before execution
BLOCKED_KEYWORDS = [
    "drop", "delete", "update", "alter", "truncate",
    "insert", "replace", "create", "grant", "revoke",
    "commit", "rollback", "exec", "execute", "call"
]

ALLOWED_PREFIXES = ["select", "with", "explain", "show", "describe"]
```

**Security guarantees:**
- ✅ Only `SELECT`, `WITH`, `EXPLAIN`, `SHOW`, `DESCRIBE` are allowed
- ✅ SQL comments (`--`, `/* */`) are stripped before keyword scanning
- ✅ Quoted string content is neutralized to prevent false positives (`WHERE name = 'drop table'`)
- ✅ Regex word-boundary matching prevents partial-word bypasses (`dropcolumn` ≠ `drop`)
- ✅ All blocked queries are logged with the offending keyword for auditing

---

## 📁 Project Structure

```
ai-data-analyst/
│
├── app.py                  # Main Streamlit application — UI, routing, visualization
├── ai_agent.py             # LLM integration — prompt engineering, SQL extraction, validation
├── database.py             # Database layer — connection, security enforcement, schema introspection
├── schema.sql              # Database DDL + seed data (users, products, orders)
├── bi_dashboard.db         # Pre-built SQLite database (auto-regenerated from schema.sql)
├── requirements.txt        # Python dependencies
│
├── .devcontainer/
│   └── devcontainer.json   # GitHub Codespaces configuration
│
├── Project-Documentation.pdf   # Full technical architecture document
└── README.md
```

---

## 💡 Example Queries

Try these in the dashboard to see the AI in action:

```
📊 "Show total revenue by product category"
   → GROUP BY with SUM aggregation, auto-renders as bar chart

👑 "Who are the top 5 customers by total spending?"
   → JOIN + ORDER BY + LIMIT, renders ranked bar chart

📅 "What is the average order value per month?"
   → DATE aggregation, renders as time-series line chart

⚠️  "Which products have low stock and high sales?"
   → JOIN + WHERE filtering across products and orders tables

📦 "How many orders were placed in Q4 2023?"
   → Date range filtering with COUNT aggregation

💰 "What is the revenue breakdown by category for orders above $50?"
   → Filtered aggregation with JOIN across 3 tables
```

---

## 🛠️ Configuration

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | ✅ Yes | Your Groq API key (`gsk_...`) |

### LLM Settings (`ai_agent.py`)

| Parameter | Default | Description |
|---|---|---|
| `model` | `openai/gpt-oss-120b` | Groq-hosted model for SQL generation |
| `temperature` | `0.0` | Deterministic output — same question always yields same SQL |
| `max_tokens` | `500` | Max SQL output length |

### Database Settings (`database.py`)

| Parameter | Default | Description |
|---|---|---|
| `db_type` | `sqlite` | Database type (`sqlite` or `mysql`) |
| `db_path` | `bi_dashboard.db` | Path to SQLite database file |

---

## 📄 Documentation

For the complete architectural deep-dive, data flow diagrams, and design decisions, see the full:

📎 **[Project Technical Documentation (PDF)](Project-Documentation.pdf)**

---

<div align="center">

**Built with 🧠 LLMs + ⚡ Groq + 🐍 Python**

*Turn your database into a conversation.*

</div>
