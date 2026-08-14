"""
database.py
Production-grade database handler for the GenAI Text-to-SQL BI Dashboard.
Supports SQLite (default) and MySQL with read-only safety enforcement.
"""

import os
import re
import sqlite3
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass

import pandas as pd

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
logger = logging.getLogger("database")


@dataclass
class DBConfig:
    """Database configuration dataclass."""
    db_type: str = "sqlite"  # "sqlite" or "mysql"
    db_path: str = "bi_dashboard.db"  # For SQLite
    host: str = "localhost"  # For MySQL
    port: int = 3306
    user: str = ""
    password: str = ""
    database: str = "bi_dashboard"


class DatabaseManager:
    """
    Production-grade database manager with security enforcement.
    Blocks all destructive SQL operations. Supports SQLite and MySQL.
    """
    
    # Destructive SQL keywords that are strictly blocked
    BLOCKED_KEYWORDS: List[str] = [
        "drop", "delete", "update", "alter", "truncate",
        "insert", "replace", "create", "grant", "revoke",
        "commit", "rollback", "exec", "execute", "call"
    ]
    
    # Allowed query starters for read-only operations
    ALLOWED_PREFIXES: List[str] = ["select", "with", "explain", "show", "describe"]
    
    def __init__(self, config: Optional[DBConfig] = None):
        """
        Initialize the DatabaseManager with configuration.
        
        Args:
            config: DBConfig instance. Defaults to SQLite local file.
        """
        self.config = config or DBConfig()
        self._connection: Optional[Any] = None
        self._schema_cache: Optional[str] = None
        self._tables_info: Optional[Dict[str, List[Dict[str, Any]]]] = None
        
        logger.info(f"DatabaseManager initialized with db_type={self.config.db_type}")
    
    def _get_connection(self) -> Any:
        """
        Establish and return a database connection.
        
        Returns:
            Database connection object.
            
        Raises:
            RuntimeError: If connection fails.
        """
        if self._connection is not None:
            return self._connection
            
        try:
            if self.config.db_type.lower() == "sqlite":
                self._connection = sqlite3.connect(
                    self.config.db_path, 
                    check_same_thread=False
                )
                # Enable foreign keys for SQLite
                self._connection.execute("PRAGMA foreign_keys = ON")
                logger.info(f"Connected to SQLite database: {self.config.db_path}")
                
            elif self.config.db_type.lower() == "mysql":
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
                    logger.info(f"Connected to MySQL database: {self.config.database}")
                except ImportError:
                    raise RuntimeError(
                        "mysql-connector-python is not installed. "
                        "Run: pip install mysql-connector-python"
                    )
            else:
                raise ValueError(f"Unsupported database type: {self.config.db_type}")
                
            return self._connection
            
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise RuntimeError(f"Database connection failed: {e}")
    
    def initialize_from_schema(self, schema_path: Union[str, Path]) -> None:
        """
        Read and execute a schema SQL file to initialize the database.
        
        Args:
            schema_path: Path to the .sql schema file.
            
        Raises:
            FileNotFoundError: If schema file doesn't exist.
            RuntimeError: If schema execution fails.
        """
        schema_path = Path(schema_path)
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")
        
        try:
            conn = self._get_connection()
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_sql = f.read()
            
            # Execute schema script
            if self.config.db_type.lower() == "sqlite":
                conn.executescript(schema_sql)
            else:
                # MySQL needs statement-by-statement execution
                for statement in schema_sql.split(";"):
                    stmt = statement.strip()
                    if stmt:
                        cursor = conn.cursor()
                        cursor.execute(stmt + ";")
                        cursor.close()
                conn.commit()
            
            logger.info(f"Database initialized from schema: {schema_path}")
            self._invalidate_cache()
            
        except Exception as e:
            logger.error(f"Schema initialization failed: {e}")
            raise RuntimeError(f"Failed to initialize database schema: {e}")
    
    def _invalidate_cache(self) -> None:
        """Invalidate cached schema information."""
        self._schema_cache = None
        self._tables_info = None
    
    def _is_safe_query(self, query: str) -> bool:
        """
        Security validator: checks if a query is safe (read-only).
        
        Args:
            query: SQL query string to validate.
            
        Returns:
            True if query is safe, False otherwise.
        """
        if not query or not query.strip():
            return False
            
        # Normalize: remove comments, extra whitespace
        cleaned = re.sub(r"--.*", " ", query)  # Remove single-line comments
        cleaned = re.sub(r"/\*.*?\*/", " ", cleaned, flags=re.DOTALL)  # Remove multi-line comments
        cleaned = cleaned.strip().lower()
        
        # Must start with an allowed prefix
        first_word = cleaned.split()[0] if cleaned.split() else ""
        if first_word not in self.ALLOWED_PREFIXES:
            logger.warning(f"Query rejected: starts with forbidden keyword '{first_word}'")
            return False
        
        # Check for any blocked keywords anywhere in the query
        # Use word boundaries to avoid false positives (e.g., "selection" contains "select")
        for keyword in self.BLOCKED_KEYWORDS:
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, cleaned):
                logger.warning(f"Query rejected: contains blocked keyword '{keyword}'")
                return False
        
        return True
    
    def execute_query(self, query: str) -> pd.DataFrame:
        """
        Execute a read-only SELECT query and return results as a DataFrame.
        
        Args:
            query: SQL SELECT query string.
            
        Returns:
            pandas.DataFrame with query results.
            
        Raises:
            ValueError: If query fails security validation.
            RuntimeError: If query execution fails.
        """
        # Security check
        if not self._is_safe_query(query):
            raise ValueError(
                "Query blocked by security policy. Only read-only SELECT queries are allowed. "
                "Blocked operations: DROP, DELETE, UPDATE, ALTER, TRUNCATE, INSERT, etc."
            )
        
        try:
            conn = self._get_connection()
            logger.info(f"Executing query: {query[:100]}...")
            
            df = pd.read_sql_query(query, conn)
            logger.info(f"Query returned {len(df)} rows, {len(df.columns)} columns")
            return df
            
        except pd.io.sql.DatabaseError as e:
            logger.error(f"SQL execution error: {e}")
            raise RuntimeError(f"SQL execution failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error during query execution: {e}")
            raise RuntimeError(f"Query execution failed: {e}")
    
    def get_schema_ddl(self) -> str:
        """
        Retrieve the database schema as CREATE TABLE DDL statements.
        Used for LLM context building.
        
        Returns:
            String containing schema DDL.
        """
        if self._schema_cache is not None:
            return self._schema_cache
        
        try:
            conn = self._get_connection()
            schema_parts = []
            
            if self.config.db_type.lower() == "sqlite":
                # Get all table names
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
                tables = [row[0] for row in cursor.fetchall()]
                
                for table in tables:
                    # Get CREATE TABLE statement
                    cursor = conn.execute(f"SELECT sql FROM sqlite_master WHERE name='{table}'")
                    ddl = cursor.fetchone()[0]
                    schema_parts.append(ddl + ";")
                    
                    # Get column info
                    cursor = conn.execute(f"PRAGMA table_info({table})")
                    columns = cursor.fetchall()
                    col_info = ", ".join([f"{col[1]} ({col[2]})" for col in columns])
                    schema_parts.append(f"-- Columns: {col_info}\n")
                    
                    # Get foreign keys
                    cursor = conn.execute(f"PRAGMA foreign_key_list({table})")
                    fks = cursor.fetchall()
                    for fk in fks:
                        schema_parts.append(
                            f"-- FK: {table}.{fk[3]} -> {fk[2]}.{fk[4]}\n"
                        )
            
            else:
                # MySQL schema retrieval
                cursor = conn.cursor()
                cursor.execute("SHOW TABLES")
                tables = [row[0] for row in cursor.fetchall()]
                
                for table in tables:
                    cursor.execute(f"SHOW CREATE TABLE {table}")
                    ddl = cursor.fetchone()[1]
                    schema_parts.append(ddl + ";")
                    
                    # Get column info
                    cursor.execute(f"DESCRIBE {table}")
                    columns = cursor.fetchall()
                    col_info = ", ".join([f"{col[0]} ({col[1]})" for col in columns])
                    schema_parts.append(f"-- Columns: {col_info}\n")
            
            self._schema_cache = "\n".join(schema_parts)
            return self._schema_cache
            
        except Exception as e:
            logger.error(f"Failed to retrieve schema: {e}")
            raise RuntimeError(f"Schema retrieval failed: {e}")
    
    def get_tables_metadata(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get structured metadata about all tables and columns.
        Used for UI schema visualization.
        
        Returns:
            Dictionary mapping table names to lists of column metadata.
        """
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
            logger.error(f"Failed to retrieve table metadata: {e}")
            raise RuntimeError(f"Metadata retrieval failed: {e}")
    
    def close(self) -> None:
        """Close the database connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            logger.info("Database connection closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        self.close()