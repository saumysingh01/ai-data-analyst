"""
database.py
Production-grade database handler with read-only security enforcement.
"""

import os
import re
import sqlite3
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
logger = logging.getLogger("database")


@dataclass
class DBConfig:
    db_type: str = "sqlite"
    db_path: str = "bi_dashboard.db"
    host: str = "localhost"
    port: int = 3306
    user: str = ""
    password: str = ""
    database: str = "bi_dashboard"


class DatabaseManager:
    BLOCKED_KEYWORDS: List[str] = [
        "drop", "delete", "update", "alter", "truncate",
        "insert", "replace", "create", "grant", "revoke",
        "commit", "rollback", "exec", "execute", "call"
    ]
    ALLOWED_PREFIXES: List[str] = ["select", "with", "explain", "show", "describe"]

    def __init__(self, config: Optional[DBConfig] = None):
        self.config = config or DBConfig()
        self._connection: Optional[Any] = None
        self._schema_cache: Optional[str] = None
        self._tables_info: Optional[Dict[str, List[Dict[str, Any]]]] = None
        logger.info(f"DatabaseManager initialized: db_type={self.config.db_type}")

    def _get_connection(self) -> Any:
        if self._connection is not None:
            return self._connection

        try:
            if self.config.db_type.lower() == "sqlite":
                self._connection = sqlite3.connect(
                    self.config.db_path,
                    check_same_thread=False
                )
                self._connection.execute("PRAGMA foreign_keys = ON")
                logger.info(f"Connected to SQLite: {self.config.db_path}")
            else:
                try:
                    import mysql.connector
                    self._connection = mysql.connector.connect(
                        host=self.config.host,
                        port=self.config.port,
                        user=self.config.user,
                        password=self.config.password,
                        database=self.config.database,
                        autocommit=False
                    )
                    logger.info(f"Connected to MySQL: {self.config.database}")
                except ImportError:
                    raise RuntimeError("pip install mysql-connector-python")
            return self._connection
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise RuntimeError(f"Database connection failed: {e}")

    def initialize_from_schema(self, schema_path: Union[str, Path]) -> None:
        schema_path = Path(schema_path)
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        try:
            conn = self._get_connection()
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_sql = f.read()

            if self.config.db_type.lower() == "sqlite":
                conn.executescript(schema_sql)
            else:
                for statement in schema_sql.split(";"):
                    stmt = statement.strip()
                    if stmt:
                        cursor = conn.cursor()
                        cursor.execute(stmt + ";")
                        cursor.close()
                conn.commit()

            logger.info(f"Database initialized from: {schema_path}")
            self._invalidate_cache()
        except Exception as e:
            logger.error(f"Schema initialization failed: {e}")
            raise RuntimeError(f"Failed to initialize schema: {e}")

    def _invalidate_cache(self) -> None:
        self._schema_cache = None
        self._tables_info = None

    def _is_safe_query(self, query: str) -> bool:
        if not query or not query.strip():
            return False

        # Remove comments
        cleaned = re.sub(r"--.*", " ", query)
        cleaned = re.sub(r"/\*.*?\*/", " ", cleaned, flags=re.DOTALL)

        # CRITICAL FIX: Strip quoted strings to avoid false positives
        # e.g., WHERE name = 'drop table' should NOT be blocked
        cleaned = re.sub(r"'[^']*'", "''", cleaned)
        cleaned = re.sub(r'"[^"]*"', '""', cleaned)

        cleaned = cleaned.strip().lower()
        first_word = cleaned.split()[0] if cleaned.split() else ""

        if first_word not in self.ALLOWED_PREFIXES:
            logger.warning(f"Query rejected: forbidden prefix '{first_word}'")
            return False

        for keyword in self.BLOCKED_KEYWORDS:
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, cleaned):
                logger.warning(f"Query rejected: blocked keyword '{keyword}'")
                return False

        return True

    def execute_query(self, query: str) -> pd.DataFrame:
        if not self._is_safe_query(query):
            raise ValueError(
                "Query blocked by security policy. Only read-only SELECT queries are allowed. "
                "Blocked operations: DROP, DELETE, UPDATE, ALTER, TRUNCATE, INSERT, etc."
            )

        try:
            conn = self._get_connection()
            logger.info(f"Executing: {query[:100]}...")
            df = pd.read_sql_query(query, conn)
            logger.info(f"Query returned {len(df)} rows, {len(df.columns)} columns")
            return df
        except pd.io.sql.DatabaseError as e:
            logger.error(f"SQL execution error: {e}")
            raise RuntimeError(f"SQL execution failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected query error: {e}")
            raise RuntimeError(f"Query execution failed: {e}")

    def get_schema_ddl(self) -> str:
        if self._schema_cache is not None:
            return self._schema_cache

        try:
            conn = self._get_connection()
            schema_parts = []

            if self.config.db_type.lower() == "sqlite":
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                tables = [row[0] for row in cursor.fetchall()]

                for table in tables:
                    cursor = conn.execute(f"SELECT sql FROM sqlite_master WHERE name='{table}'")
                    ddl = cursor.fetchone()[0]
                    schema_parts.append(ddl + ";")

                    cursor = conn.execute(f"PRAGMA table_info({table})")
                    columns = cursor.fetchall()
                    col_info = ", ".join([f"{col[1]} ({col[2]})" for col in columns])
                    schema_parts.append(f"-- Columns: {col_info}\n")

                    cursor = conn.execute(f"PRAGMA foreign_key_list({table})")
                    for fk in cursor.fetchall():
                        schema_parts.append(f"-- FK: {table}.{fk[3]} -> {fk[2]}.{fk[4]}\n")
            else:
                cursor = conn.cursor()
                cursor.execute("SHOW TABLES")
                tables = [row[0] for row in cursor.fetchall()]
                for table in tables:
                    cursor.execute(f"SHOW CREATE TABLE {table}")
                    ddl = cursor.fetchone()[1]
                    schema_parts.append(ddl + ";")
                    cursor.execute(f"DESCRIBE {table}")
                    columns = cursor.fetchall()
                    col_info = ", ".join([f"{col[0]} ({col[1]})" for col in columns])
                    schema_parts.append(f"-- Columns: {col_info}\n")

            self._schema_cache = "\n".join(schema_parts)
            return self._schema_cache
        except Exception as e:
            logger.error(f"Schema retrieval failed: {e}")
            raise RuntimeError(f"Schema retrieval failed: {e}")

    def get_tables_metadata(self) -> Dict[str, List[Dict[str, Any]]]:
        if self._tables_info is not None:
            return self._tables_info

        metadata = {}
        try:
            conn = self._get_connection()

            if self.config.db_type.lower() == "sqlite":
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                tables = [row[0] for row in cursor.fetchall()]

                for table in tables:
                    cursor = conn.execute(f"PRAGMA table_info({table})")
                    columns = []
                    for col in cursor.fetchall():
                        columns.append({
                            "name": col[1],
                            "type": col[2],
                            "nullable": not col[3],
                            "default": col[4],
                            "pk": bool(col[5])
                        })
                    metadata[table] = columns
            else:
                cursor = conn.cursor()
                cursor.execute("SHOW TABLES")
                tables = [row[0] for row in cursor.fetchall()]
                for table in tables:
                    cursor.execute(f"DESCRIBE {table}")
                    columns = []
                    for col in cursor.fetchall():
                        columns.append({
                            "name": col[0],
                            "type": col[1],
                            "nullable": col[2] == "YES",
                            "default": col[4],
                            "pk": col[3] == "PRI"
                        })
                    metadata[table] = columns

            self._tables_info = metadata
            return metadata
        except Exception as e:
            logger.error(f"Metadata retrieval failed: {e}")
            raise RuntimeError(f"Metadata retrieval failed: {e}")

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            logger.info("Database connection closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()