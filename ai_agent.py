"""
ai_agent.py
LLM integration layer for natural language to SQL translation.
Uses Groq API with openai/gpt-oss-120b (clean text model).
"""

import os
import re
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
logger = logging.getLogger("ai_agent")


@dataclass
class LLMConfig:
    provider: str = "groq"
    model: str = "openai/gpt-oss-120b"
    api_key: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 500


class SQLAgent:
    """
    GenAI-powered SQL agent. Translates natural language to clean SQL.
    Designed for non-thinking models that follow output instructions precisely.
    """

    SYSTEM_PROMPT_TEMPLATE = """You are an expert SQL query generator for a Business Intelligence dashboard.
Your task is to translate natural language questions into clean, executable SQL queries.

DATABASE SCHEMA:
{schema}

RULES:
1. Output ONLY the raw SQL query. No markdown formatting, no backticks (```), no explanations.
2. Use standard SQL compatible with {dialect}.
3. Use table aliases for readability (e.g., u for users, p for products, o for orders).
4. For aggregations, use clear column aliases.
5. When filtering dates, use proper date comparisons.
6. For joins, always specify the join condition explicitly.
7. If the question is ambiguous, make reasonable assumptions and write the most likely query.
8. Never output multiple queries. Only one SELECT statement.
9. Do NOT include any comments in the SQL output.
10. Ensure all column references are qualified with table names or aliases when joining.

OUTPUT FORMAT:
Return ONLY the SQL query as plain text. Nothing else."""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self._client = None
        self._setup_client()
        logger.info(f"SQLAgent: {self.config.provider}/{self.config.model}")

    def _setup_client(self) -> None:
        try:
            from groq import Groq
            api_key = self.config.api_key or os.environ.get("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY missing.")
            api_key = api_key.strip().strip('"').strip("'")
            self._client = Groq(api_key=api_key)
        except ImportError:
            raise ImportError("pip install groq")

    def _build_system_prompt(self, schema_ddl: str, dialect: str = "SQLite") -> str:
        return self.SYSTEM_PROMPT_TEMPLATE.format(schema=schema_ddl, dialect=dialect)

    def _clean_sql_output(self, raw_output: str) -> str:
        """
        Clean LLM output: remove markdown, backticks, and conversational filler.
        Extracts the first SELECT statement.
        """
        if not raw_output:
            return ""

        text = raw_output

        # Remove markdown code blocks
        text = re.sub(r"```sql\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"```\s*", "", text)

        # Remove single backticks
        text = text.replace("`", "")

        # Find first SELECT
        select_match = re.search(r'\bSELECT\b', text, re.IGNORECASE)
        if not select_match:
            logger.error(f"No SELECT found. Raw: {text[:200]}")
            return ""

        sql = text[select_match.start():]

        # Find semicolon that ends the statement
        semi_pos = sql.find(';')
        if semi_pos != -1:
            sql = sql[:semi_pos + 1]

        # Collapse whitespace
        sql = re.sub(r'\s+', ' ', sql).strip()

        if not sql.endswith(';'):
            sql += ';'

        logger.info(f"Extracted SQL: {sql[:120]}...")
        return sql

    def generate_sql(self, question: str, schema_ddl: str, dialect: str = "SQLite") -> str:
        system_prompt = self._build_system_prompt(schema_ddl, dialect)

        try:
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question}
                ],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens
            )

            raw_output = response.choices[0].message.content
            if not raw_output:
                raise ValueError("Empty LLM response")

            cleaned_sql = self._clean_sql_output(raw_output)

            if not cleaned_sql:
                logger.error(f"Extraction failed. Raw: {raw_output[:300]}")
                raise ValueError("Could not extract SQL from model output.")

            return cleaned_sql

        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise RuntimeError(f"SQL generation failed: {e}")

    def validate_sql_syntax(self, sql: str) -> Dict[str, Any]:
        issues = []
        sql_upper = sql.upper().strip()

        if not sql_upper.startswith("SELECT"):
            issues.append("Query does not start with SELECT")
        if sql.count("(") != sql.count(")"):
            issues.append("Unbalanced parentheses")
        if "FROM" not in sql_upper:
            issues.append("Missing FROM clause")

        return {"valid": len(issues) == 0, "issues": issues}