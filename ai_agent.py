"""
ai_agent.py
LLM integration layer for natural language to SQL translation.
Uses Groq API with Qwen model. Robust against <think> blocks and reasoning noise.
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
    GenAI-powered SQL agent. Extracts clean SELECT/WITH statements
    from Qwen's noisy output regardless of <think> tags, markdown, or reasoning.
    """

    SYSTEM_PROMPT_TEMPLATE = """You are a SQL generator. Output ONE raw SQL query only.

SCHEMA:
{schema}

RULES:
- Start with SELECT or WITH. End with ;
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
        Extracts the first valid SQL query (SELECT or WITH) from anywhere in the text.
        Handles <think> blocks, markdown, reasoning, and unclosed tags.
        """
        if not raw_output:
            return ""

        text = raw_output

        # 1. Remove markdown code fences
        text = re.sub(r"```sql\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"```\s*", "", text)
        text = text.replace("`", "")

        # Helper: try to extract SQL from a given string
        def extract(source: str) -> Optional[str]:
            # Find first SELECT or WITH
            match = re.search(r'\b(?:SELECT|WITH)\b', source, re.IGNORECASE)
            if not match:
                return None

            fragment = source[match.start():]

            # Find semicolon that ends the statement
            semi_pos = fragment.find(';')
            if semi_pos != -1:
                sql = fragment[:semi_pos + 1]
            else:
                sql = fragment
                # No semicolon: cut at explanation / reasoning patterns
                cut_patterns = [
                    r'\s+\d+\.\s+',                    # "9. ", "10. "
                    r'\s+Refining\s*:', 
                    r'\s+Aliases\s*:',
                    r'\s+Columns\s*:',
                    r'\s+Constraints\s*:',
                    r'\s+Final Check\s*:',
                    r'\s+Self-Correction\s*:',
                    r'\s+Query Construction\s*:',
                    r'\s+Explanation\s*:',
                    r'\s+Note\s*:',
                    r'\s+Here is\s*:',
                    r'\s+Output format\s*:',
                    r'\s+Sure[,\s]',
                    r'\s+I need',
                    r'\s+I will',
                    r'\s+I can',
                    r'\s+The user',
                    r'\s+This query',
                    r'\s+Now[,\s]',
                    r'\n\s*\*\s+',                     # Markdown bullet "* "
                    r'\n\s*-\s+',                      # Dash bullet "- "
                ]
                for pattern in cut_patterns:
                    cut = re.search(pattern, sql, re.IGNORECASE)
                    if cut:
                        sql = sql[:cut.start()]
                        break
                sql = sql.strip()
                if not sql.endswith(';'):
                    sql += ';'

            sql = re.sub(r'\s+', ' ', sql).strip()

            # Validate it actually starts with SQL keyword
            if re.match(r'^(SELECT|WITH)\b', sql, re.IGNORECASE):
                return sql
            return None

        # Strategy 1: Remove <think> blocks and extract (preferred — cleanest)
        # Use non-greedy but handle unclosed tags by stopping at </think> or end
        no_think = re.sub(r'<think>.*?(?:</think>|$)', '', text, flags=re.DOTALL | re.IGNORECASE)
        result = extract(no_think)
        if result:
            return result

        # Strategy 2: Search original text (SQL might be inside think block)
        result = extract(text)
        if result:
            return result

        # Strategy 3: Brute force — find "SELECT" and take until newline or ;
        idx = text.upper().find('SELECT')
        if idx != -1:
            fragment = text[idx:]
            # Take until semicolon, newline, or explanation word
            end = len(fragment)
            for delim in [';', '\n', 'Here', 'Note', 'Explanation', 'Sure', 'I need', 'The user']:
                pos = fragment.find(delim)
                if pos != -1 and pos < end:
                    end = pos
            sql = fragment[:end].strip()
            if sql:
                if not sql.endswith(';'):
                    sql += ';'
                sql = re.sub(r'\s+', ' ', sql).strip()
                if re.match(r'^SELECT\b', sql, re.IGNORECASE):
                    return sql

        logger.error(f"SQL extraction failed. Raw preview: {repr(text[:500])}")
        return ""

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
                # CRITICAL: Show raw output in error so user can debug
                preview = raw_output[:400].replace('\n', ' ')
                raise ValueError(
                    f"Could not extract SQL from model output. "
                    f"Raw model response: '{preview}...' "
                    f"Please try rephrasing your question."
                )

            return cleaned_sql

        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise RuntimeError(f"SQL generation failed: {e}")

    def validate_sql_syntax(self, sql: str) -> Dict[str, Any]:
        issues = []
        sql_upper = sql.upper().strip()

        if not sql_upper.startswith(("SELECT", "WITH")):
            issues.append("Query does not start with SELECT or WITH")
        if sql.count("(") != sql.count(")"):
            issues.append("Unbalanced parentheses")
        if "FROM" not in sql_upper:
            issues.append("Missing FROM clause")

        return {"valid": len(issues) == 0, "issues": issues}