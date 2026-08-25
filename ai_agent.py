"""
ai_agent.py
LLM integration layer for natural language to SQL translation.
Uses the Groq API with Qwen.
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
    model: str = "qwen/qwen3.6-27b"
    api_key: Optional[str] = None
    temperature: float = 0.0
    max_tokens: int = 500


class SQLAgent:
    """
    GenAI-powered SQL agent. Surgically isolates SELECT statements
    from Qwen's noisy output (reasoning, markdown, XML tags).
    """

    SYSTEM_PROMPT_TEMPLATE = """You are a SQL generator. Output ONE raw SQL query only.

SCHEMA:
{schema}

RULES:
- Start with SELECT. End with ;
- No markdown. No backticks. No explanations. No numbering.
- No reasoning. No aliases list. No self-correction.
- {dialect} syntax. Use short aliases (u,p,o).

OUTPUT:"""

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
        Brutally isolates the first SELECT...; statement.
        Discards everything else: reasoning, markdown, XML, filler.
        """
        if not raw_output:
            return ""

        text = raw_output

        # Strip markdown & special tokens
        text = re.sub(r"```sql\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"```\s*", "", text)
        text = text.replace("`", "")
        text = re.sub(r"<[^>]+>", "", text)

        # Find first SELECT
        select_match = re.search(r'\bSELECT\b', text, re.IGNORECASE)
        if not select_match:
            return ""

        remaining = text[select_match.start():]

        # Extract line-by-line until SQL clearly ends
        lines = remaining.splitlines()
        sql_lines = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                break

            # Stop at explanation / reasoning lines
            if re.match(
                r'^(?:\d+\.|Note|Explanation|Here|Sure|Okay|This|That|It|The|Query|SQL|Output|Refining|Aliases|Columns|Constraints|Final|Self|If|Because|Since|However|Therefore|Thus|So|Wait|Actually|Let me|First|Second|Third|Next|Then|Finally)\b',
                stripped,
                re.IGNORECASE
            ):
                break

            sql_lines.append(stripped)

            # Semicolon = end of SQL
            if stripped.endswith(';'):
                break

        if not sql_lines:
            return ""

        sql = " ".join(sql_lines)
        sql = re.sub(r'\s+', ' ', sql).strip()

        # Second-pass: cut inline explanation text that leaked in
        inline_cut = re.search(
            r'\s+(?:Note|Explanation|Here|Sure|Okay|Refining|Aliases|Columns|Constraints|Final|Self|If|Because|Since|However|Therefore|Thus|So|Wait|Actually)\b',
            sql,
            re.IGNORECASE
        )
        if inline_cut:
            sql = sql[:inline_cut.start()].strip()

        if not sql.endswith(';'):
            sql += ';'

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
                logger.error(f"SQL extraction failed. Raw: {raw_output[:300]}")
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