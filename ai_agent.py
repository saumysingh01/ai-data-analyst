"""
ai_agent.py
LLM integration layer for natural language to SQL translation.
Uses Groq API with Qwen model.
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
    GenAI-powered SQL agent. Extracts clean SELECT statements
    from Qwen's noisy output (think blocks, markdown, reasoning).
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
        Extracts exactly one SELECT...; statement.
        Discards everything else: think blocks, markdown, reasoning, filler.
        """
        if not raw_output:
            return ""

        text = raw_output

        # 1. Remove ENTIRE <think>...</think> blocks (including unclosed ones)
        text = re.sub(r'<think>.*?(?:</think>|$)', '', text, flags=re.DOTALL | re.IGNORECASE)

        # 2. Remove markdown code fences
        text = re.sub(r"```sql\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"```\s*", "", text)

        # 3. Remove backticks and stray XML tags
        text = text.replace("`", "")
        text = re.sub(r"<[^>]+>", "", text)

        # 4. Find SQL: from first SELECT to first semicolon
        select_match = re.search(r'\bSELECT\b', text, re.IGNORECASE)
        if not select_match:
            logger.error(f"No SELECT found. Raw: {text[:200]}")
            return ""

        sql_fragment = text[select_match.start():]
        semi_pos = sql_fragment.find(';')

        if semi_pos != -1:
            sql = sql_fragment[:semi_pos + 1]
        else:
            # No semicolon: cut at first explanation word, then add ;
            sql = sql_fragment
            cut = re.search(
                r'\s+(?:Here|Note|Explanation|This|That|The|Now|Let|I\s|You\s|Query|Output|SQL|Refining|Aliases|Columns|Constraints|Final|Self|If|Because|Since|However|Therefore|Thus|So|Wait|Actually|First|Second|Third|Next|Then|Finally|Sure|Okay|I need|I will|I can)\b',
                sql, re.IGNORECASE
            )
            if cut:
                sql = sql[:cut.start()]
            sql = sql.strip() + ';'

        # Collapse whitespace
        sql = re.sub(r'\s+', ' ', sql).strip()

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