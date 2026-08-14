"""
ai_agent.py
LLM integration layer for natural language to SQL translation.
Uses the Groq API with Llama 3.3 70B for ultra-fast, zero-cost inference.
"""

import os
import re
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
logger = logging.getLogger("ai_agent")


@dataclass
class LLMConfig:
    """Configuration for LLM provider."""
    provider: str = "groq"
    model: str = "llama-3.3-70b-versatile"
    api_key: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 500


class SQLAgent:
    """
    GenAI-powered SQL agent that translates natural language questions
    into executable, safe SQL queries using Groq's Llama 3.3 70B.
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
        """
        Initialize the SQL Agent with Groq LLM configuration.

        Args:
            config: LLMConfig instance. Defaults to Groq with Llama 3.3 70B.
        """
        self.config = config or LLMConfig()
        self._client: Optional[Any] = None
        self._setup_client()

        logger.info(
            f"SQLAgent initialized with provider={self.config.provider}, "
            f"model={self.config.model}"
        )

    def _setup_client(self) -> None:
        """Initialize the Groq client with explicit key validation."""
        try:
            from groq import Groq

            # Priority: 1) explicit config, 2) environment variable
            api_key = self.config.api_key or os.environ.get("GROQ_API_KEY")

            if not api_key:
                raise ValueError(
                    "Groq API key is missing.\n"
                    "Set it before starting Streamlit:\n"
                    "  export GROQ_API_KEY='gsk_...'\n"
                    "Or pass it directly via LLMConfig(api_key='...')."
                )

            # Defensive strip in case the user accidentally included whitespace/quotes
            api_key = api_key.strip().strip('"').strip("'")

            if not api_key.startswith("gsk_"):
                logger.warning("Groq API key does not start with 'gsk_'. This may be invalid.")

            self._client = Groq(api_key=api_key)
            logger.info("Groq client initialized successfully")

        except ImportError:
            raise ImportError(
                "Groq SDK not installed. Run: pip install groq"
            )

    def _build_system_prompt(self, schema_ddl: str, dialect: str = "SQLite") -> str:
        """
        Build the system prompt with schema context.

        Args:
            schema_ddl: Database schema DDL string.
            dialect: SQL dialect (SQLite or MySQL).

        Returns:
            Formatted system prompt string.
        """
        return self.SYSTEM_PROMPT_TEMPLATE.format(
            schema=schema_ddl,
            dialect=dialect
        )

    def _clean_sql_output(self, raw_output: str) -> str:
        """
        Clean LLM output to extract pure SQL query.
        Removes markdown code blocks, backticks, and extra text.

        Args:
            raw_output: Raw string from LLM.

        Returns:
            Clean SQL query string.
        """
        # Remove markdown code blocks
        cleaned = re.sub(r"```sql\s*", "", raw_output, flags=re.IGNORECASE)
        cleaned = re.sub(r"```\s*", "", cleaned)

        # Remove single backticks
        cleaned = cleaned.replace("`", "")

        # Strip whitespace and newlines
        cleaned = cleaned.strip()

        # Extract only valid SQL lines, skip conversational prefixes
        lines = cleaned.split("\n")
        sql_lines = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.lower().startswith(
                ("here is", "the query", "sql:", "query:", "sure", "okay")
            ):
                continue
            sql_lines.append(stripped)

        cleaned = " ".join(sql_lines)

        # Ensure it ends with semicolon for consistency
        if cleaned and not cleaned.endswith(";"):
            cleaned += ";"

        logger.debug(f"Cleaned SQL: {cleaned[:100]}...")
        return cleaned

    def generate_sql(
        self,
        question: str,
        schema_ddl: str,
        dialect: str = "SQLite"
    ) -> str:
        """
        Generate SQL query from natural language question via Groq.

        Args:
            question: Natural language question from user.
            schema_ddl: Database schema DDL for context.
            dialect: SQL dialect being used.

        Returns:
            Clean SQL query string.

        Raises:
            RuntimeError: If Groq API call fails or returns invalid output.
        """
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

            if not raw_output or not raw_output.strip():
                raise ValueError("Groq returned empty response")

            cleaned_sql = self._clean_sql_output(raw_output)
            logger.info(f"Generated SQL: {cleaned_sql[:100]}...")
            return cleaned_sql

        except Exception as e:
            logger.error(f"Groq query generation failed: {e}")
            raise RuntimeError(f"Failed to generate SQL from natural language: {e}")

    def validate_sql_syntax(self, sql: str) -> Dict[str, Any]:
        """
        Basic validation of generated SQL.

        Args:
            sql: SQL query string to validate.

        Returns:
            Dictionary with 'valid' boolean and 'issues' list.
        """
        issues = []
        sql_upper = sql.upper()

        # Must start with SELECT
        if not sql_upper.strip().startswith("SELECT"):
            issues.append("Query does not start with SELECT")

        # Check for balanced parentheses
        if sql.count("(") != sql.count(")"):
            issues.append("Unbalanced parentheses")

        # Check for basic structure
        if "FROM" not in sql_upper:
            issues.append("Missing FROM clause")

        return {
            "valid": len(issues) == 0,
            "issues": issues
        }