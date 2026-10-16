"""Database adapters that normalize source engines at the extraction boundary."""
from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
import base64
import hashlib
import json
from typing import Any, Iterable

from app.core.config import get_settings
from app.models.entities import MigrationColumn, MigrationObject, MigrationSource


SUPPORTED_ENGINES = ("SQLSERVER", "POSTGRESQL", "MYSQL", "ORACLE")
DEFAULT_PORTS = {"SQLSERVER": 1433, "POSTGRESQL": 5432, "MYSQL": 3306, "ORACLE": 1521}
DEFAULT_SCHEMAS = {"POSTGRESQL": "public"}


def normalize_engine(value: str | None) -> str:
    aliases = {"POSTGRES": "POSTGRESQL", "MARIADB": "MYSQL", "MSSQL": "SQLSERVER"}
    engine = aliases.get(str(value or "SQLSERVER").strip().upper(), str(value or "SQLSERVER").strip().upper())
    if engine not in SUPPORTED_ENGINES:
        raise ValueError(f"Unsupported source engine: {value}")
    return engine


def encrypt_password(password: str | None) -> str | None:
    if not password:
        return None
    try:
        from cryptography.fernet import Fernet
    except Exception as exc:
        raise RuntimeError("cryptography is required to store source credentials") from exc
    secret = get_settings().jwt_secret.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key).encrypt(password.encode("utf-8")).decode("ascii")


def decrypt_password(value: str | None) -> str | None:
    if not value:
        return None
    from cryptography.fernet import Fernet, InvalidToken
    secret = get_settings().jwt_secret.encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    try:
        return Fernet(key).decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("Stored source credential cannot be decrypted with the current JWT secret") from exc


def source_options(source: MigrationSource) -> dict[str, Any]:
    try:
        return json.loads(source.options_json or "{}")
    except Exception:
        return {}


@dataclass(frozen=True)
class WatermarkCandidate:
    name: str
    data_type: str
    nullable: bool


class BaseDatabaseAdapter(ABC):
    engine: str

    def __init__(self, source: MigrationSource):
        self.source = source
        self.options = source_options(source)

    @abstractmethod
    def test_connection(self) -> dict[str, Any]: ...

    @abstractmethod
    def discover_catalog(self) -> dict[str, Any]: ...

    @abstractmethod
    def open_table_cursor(self, table: MigrationObject, columns: list[MigrationColumn], *, batch_size: int, offset: int = 0, max_rows: int | None = None): ...

    @abstractmethod
    def open_delta_cursor(self, table: MigrationObject, columns: list[MigrationColumn], watermark_col: str, watermark_val: Any, *, batch_size: int, max_rows: int | None = None): ...

    def extract_table_batch(self, table_name: str, schema: str, batch_size: int, offset: int = 0) -> Iterable[list[tuple]]:
        table = MigrationObject(schema_name=schema, object_name=table_name)
        with self.open_table_cursor(table, [], batch_size=batch_size, offset=offset) as cursor:
            while batch := cursor.fetchmany(batch_size):
                yield [tuple(row) for row in batch]

    def extract_delta_batch(self, table_name: str, schema: str, watermark_col: str, watermark_val: Any, batch_size: int) -> Iterable[list[tuple]]:
        table = MigrationObject(schema_name=schema, object_name=table_name)
        with self.open_delta_cursor(table, [], watermark_col, watermark_val, batch_size=batch_size) as cursor:
            while batch := cursor.fetchmany(batch_size):
                yield [tuple(row) for row in batch]

    def get_watermark_candidates(self, table_name: str, schema: str) -> list[WatermarkCandidate]:
        snapshot = self.discover_catalog()
        for item in snapshot.get("objects", []):
            if item.get("type") == "TABLE" and item.get("name") == table_name and item.get("schema") == schema:
                return [WatermarkCandidate(c["name"], c["type"], bool(c.get("nullable", True))) for c in item.get("columns", [])]
        return []

    def count_rows(self, table: MigrationObject) -> int:
        with self._cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {self.qualified(table.schema_name, table.object_name)}")
            return int(cursor.fetchone()[0])

    @abstractmethod
    def qualified(self, schema: str, name: str) -> str: ...

    @abstractmethod
    def quote_identifier(self, value: str) -> str: ...


class DBAPIAdapter(BaseDatabaseAdapter):
    placeholder = "%s"
    limit_style = "LIMIT"

    @abstractmethod
    def connect(self): ...

    @contextmanager
    def _cursor(self):
        connection = self.connect()
        try:
            cursor = connection.cursor()
            try:
                yield cursor
            finally:
                cursor.close()
        finally:
            connection.close()

    def _projection(self, columns: list[MigrationColumn]) -> str:
        return ",".join(self.quote_identifier(c.column_name) for c in columns) if columns else "*"

    def _limited_sql(self, projection: str, table: MigrationObject, max_rows: int | None, offset: int = 0) -> str:
        sql = f"SELECT {projection} FROM {self.qualified(table.schema_name, table.object_name)}"
        if max_rows:
            sql += f" LIMIT {int(max_rows)}"
        if offset:
            sql += f" OFFSET {int(offset)}"
        return sql

    def _append_delta_limit(self, sql: str, max_rows: int | None) -> str:
        return sql + (f" LIMIT {int(max_rows)}" if max_rows else "")

    @contextmanager
    def open_table_cursor(self, table, columns, *, batch_size, offset=0, max_rows=None):
        with self._cursor() as cursor:
            cursor.execute(self._limited_sql(self._projection(columns), table, max_rows, offset))
            yield cursor

    @contextmanager
    def open_delta_cursor(self, table, columns, watermark_col, watermark_val, *, batch_size, max_rows=None):
        projection = self._projection(columns)
        wm = self.quote_identifier(watermark_col)
        sql = f"SELECT {projection} FROM {self.qualified(table.schema_name, table.object_name)}"
        params: list[Any] = []
        if watermark_val is not None and str(watermark_val).strip():
            sql += f" WHERE {wm} > {self.placeholder}"
            params.append(watermark_val)
        sql += f" ORDER BY {wm} ASC"
        sql = self._append_delta_limit(sql, max_rows)
        cursor_context = self._cursor()
        with cursor_context as cursor:
            cursor.execute(sql, params)
            yield cursor

    def _rows(self, cursor) -> list[dict[str, Any]]:
        names = [str(item[0]).lower() for item in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]


class SQLServerAdapter(BaseDatabaseAdapter):
    engine = "SQLSERVER"

    def connection_string(self) -> str:
        cfg = get_settings()
        options = self.options
        driver = str(options.get("driver") or cfg.sqlserver_driver).replace("{", "").replace("}", "")
        username = self.source.username or cfg.sqlserver_username
        password = decrypt_password(self.source.credential_ciphertext) or cfg.sqlserver_password or ""
        port = f",{self.source.port}" if self.source.port and "\\" not in self.source.server_name else ""
        base = f"DRIVER={{{driver}}};SERVER={self.source.server_name}{port};DATABASE={self.source.database_name};"
        if username:
            return base + f"UID={username};PWD={password};TrustServerCertificate=yes;"
        return base + "Trusted_Connection=yes;TrustServerCertificate=yes;"

    def test_connection(self):
        from app.services.discovery import test_sqlserver_connection
        return {**test_sqlserver_connection(self.connection_string()), "engine": self.engine}

    def discover_catalog(self):
        from app.services.discovery import discover_sqlserver
        return {**discover_sqlserver(self.connection_string()), "engine": self.engine}

    def quote_identifier(self, value):
        return "[" + str(value).replace("]", "]]" ) + "]"

    def qualified(self, schema, name):
        return f"{self.quote_identifier(schema)}.{self.quote_identifier(name)}"

    @contextmanager
    def _cursor(self):
        import pyodbc
        with pyodbc.connect(self.connection_string(), timeout=45) as connection:
            cursor = connection.cursor()
            try:
                yield cursor
            finally:
                cursor.close()

    def _projection(self, columns):
        if not columns:
            return "*"
        from app.services.type_compatibility import source_select_expression
        return ",".join(source_select_expression(column) for column in columns)

    @contextmanager
    def open_table_cursor(self, table, columns, *, batch_size, offset=0, max_rows=None):
        top = f"TOP ({int(max_rows)}) " if max_rows else ""
        sql = f"SELECT {top}{self._projection(columns)} FROM {self.qualified(table.schema_name, table.object_name)}"
        if offset:
            sql += f" ORDER BY (SELECT NULL) OFFSET {int(offset)} ROWS"
        with self._cursor() as cursor:
            cursor.execute(sql)
            yield cursor

    @contextmanager
    def open_delta_cursor(self, table, columns, watermark_col, watermark_val, *, batch_size, max_rows=None):
        top = f"TOP ({int(max_rows or batch_size)}) "
        wm = self.quote_identifier(watermark_col)
        sql = f"SELECT {top}{self._projection(columns)} FROM {self.qualified(table.schema_name, table.object_name)}"
        params = []
        if watermark_val is not None and str(watermark_val).strip():
            sql += f" WHERE {wm} > ?"
            params.append(watermark_val)
        sql += f" ORDER BY {wm} ASC"
        with self._cursor() as cursor:
            cursor.execute(sql, params) if params else cursor.execute(sql)
            yield cursor


class PostgreSQLAdapter(DBAPIAdapter):
    engine = "POSTGRESQL"

    def connect(self):
        import psycopg2
        cfg = get_settings()
        return psycopg2.connect(host=self.source.server_name, port=self.source.port or 5432,
                                dbname=self.source.database_name, user=self.source.username or cfg.postgres_username,
                                password=decrypt_password(self.source.credential_ciphertext) or cfg.postgres_password,
                                sslmode=self.options.get("ssl_mode") or cfg.postgres_ssl_mode,
                                connect_timeout=10)

    def quote_identifier(self, value): return '"' + str(value).replace('"', '""') + '"'
    def qualified(self, schema, name): return f"{self.quote_identifier(schema)}.{self.quote_identifier(name)}"

    def test_connection(self):
        with self._cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user, version()")
            database, user, version = cursor.fetchone()
        return {"ok": True, "engine": self.engine, "database": database, "user": user, "product_version": version}

    def discover_catalog(self):
        schema = self.source.schema_name or "public"
        with self._cursor() as cursor:
            cursor.execute("""SELECT table_schema AS schema_name, table_name AS object_name,
                CASE table_type WHEN 'BASE TABLE' THEN 'TABLE' ELSE 'VIEW' END AS object_type
                FROM information_schema.tables WHERE table_schema=%s ORDER BY table_name""", (schema,))
            objects = self._rows(cursor)
            cursor.execute("""SELECT table_schema AS schema_name, table_name AS object_name, column_name,
                ordinal_position AS ordinal, data_type, character_maximum_length AS max_length,
                numeric_precision AS "precision", numeric_scale AS "scale", is_nullable, column_default
                FROM information_schema.columns WHERE table_schema=%s ORDER BY table_name, ordinal_position""", (schema,))
            columns = self._rows(cursor)
            cursor.execute("""SELECT tc.table_schema AS schema_name, tc.table_name AS object_name, tc.constraint_name AS constraint_name,
                tc.constraint_type AS constraint_type, kcu.column_name AS column_name, kcu.ordinal_position AS ordinal
                FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema
                WHERE tc.table_schema=%s AND tc.constraint_type IN ('PRIMARY KEY','UNIQUE')""", (schema,))
            constraints = self._rows(cursor)
        return _canonical_snapshot(self.source.database_name, objects, columns, constraints, self.engine)


class MySQLAdapter(DBAPIAdapter):
    engine = "MYSQL"

    def connect(self):
        import pymysql
        cfg = get_settings()
        return pymysql.connect(host=self.source.server_name, port=self.source.port or 3306,
                               database=self.source.database_name, user=self.source.username or cfg.mysql_username,
                               password=decrypt_password(self.source.credential_ciphertext) or cfg.mysql_password,
                               charset=self.options.get("charset") or cfg.mysql_charset,
                               cursorclass=pymysql.cursors.SSCursor,
                               connect_timeout=10)

    def quote_identifier(self, value): return "`" + str(value).replace("`", "``") + "`"
    def qualified(self, schema, name): return f"{self.quote_identifier(schema or self.source.database_name)}.{self.quote_identifier(name)}"

    def test_connection(self):
        with self._cursor() as cursor:
            cursor.execute("SELECT DATABASE(), CURRENT_USER(), VERSION()")
            database, user, version = cursor.fetchone()
        return {"ok": True, "engine": self.engine, "database": database, "user": user, "product_version": version}

    def discover_catalog(self):
        database = self.source.database_name
        with self._cursor() as cursor:
            cursor.execute("""SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS object_name,
                CASE TABLE_TYPE WHEN 'BASE TABLE' THEN 'TABLE' ELSE 'VIEW' END AS object_type
                FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME""", (database,))
            objects = self._rows(cursor)
            cursor.execute("""SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS object_name, COLUMN_NAME AS column_name,
                ORDINAL_POSITION AS `ordinal`, DATA_TYPE AS data_type, CHARACTER_MAXIMUM_LENGTH AS max_length,
                NUMERIC_PRECISION AS `precision`, NUMERIC_SCALE AS `scale`, IS_NULLABLE AS is_nullable, COLUMN_DEFAULT AS column_default,
                COLUMN_KEY AS column_key, EXTRA AS extra FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s
                ORDER BY TABLE_NAME, ORDINAL_POSITION""", (database,))
            columns = self._rows(cursor)
            cursor.execute("""SELECT TABLE_SCHEMA AS schema_name, TABLE_NAME AS object_name, CONSTRAINT_NAME AS constraint_name,
                'PRIMARY KEY' AS constraint_type, COLUMN_NAME AS column_name, ORDINAL_POSITION AS `ordinal`
                FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=%s AND CONSTRAINT_NAME='PRIMARY'""", (database,))
            constraints = self._rows(cursor)
        return _canonical_snapshot(database, objects, columns, constraints, self.engine)


class OracleAdapter(DBAPIAdapter):
    engine = "ORACLE"
    placeholder = ":1"

    def connect(self):
        import oracledb
        cfg = get_settings()
        sid = self.options.get("sid")
        service = self.options.get("service_name") or cfg.oracle_service_name or self.source.database_name
        dsn = oracledb.makedsn(self.source.server_name, self.source.port or 1521,
                               sid=sid) if sid else oracledb.makedsn(
                                   self.source.server_name, self.source.port or 1521, service_name=service)
        mode = oracledb.AUTH_MODE_SYSDBA if str(self.options.get("auth_mode", "NORMAL")).upper() == "SYSDBA" else None
        kwargs = {"user": self.source.username or cfg.oracle_username or self.source.schema_name,
                  "password": decrypt_password(self.source.credential_ciphertext) or cfg.oracle_password,
                  "dsn": dsn}
        if mode is not None:
            kwargs["mode"] = mode
        return oracledb.connect(**kwargs)

    def quote_identifier(self, value): return '"' + str(value).replace('"', '""').upper() + '"'
    def qualified(self, schema, name): return f"{self.quote_identifier(schema)}.{self.quote_identifier(name)}"

    def _limited_sql(self, projection, table, max_rows, offset=0):
        sql = f"SELECT {projection} FROM {self.qualified(table.schema_name, table.object_name)}"
        if offset:
            sql += f" OFFSET {int(offset)} ROWS"
        if max_rows:
            sql += f" FETCH FIRST {int(max_rows)} ROWS ONLY"
        return sql

    def _append_delta_limit(self, sql, max_rows):
        return sql + (f" FETCH FIRST {int(max_rows)} ROWS ONLY" if max_rows else "")

    def test_connection(self):
        with self._cursor() as cursor:
            cursor.execute("SELECT SYS_CONTEXT('USERENV','DB_NAME'), USER FROM dual")
            database, user = cursor.fetchone()
        return {"ok": True, "engine": self.engine, "database": database, "user": user, "product_version": "Oracle"}

    def discover_catalog(self):
        schema = (self.source.schema_name or self.source.username or "").upper()
        with self._cursor() as cursor:
            cursor.execute("""SELECT OWNER schema_name, TABLE_NAME object_name, 'TABLE' object_type
                FROM ALL_TABLES WHERE OWNER=:schema UNION ALL SELECT OWNER, VIEW_NAME, 'VIEW'
                FROM ALL_VIEWS WHERE OWNER=:schema ORDER BY 2""", {"schema": schema})
            objects = self._rows(cursor)
            cursor.execute("""SELECT OWNER AS schema_name, TABLE_NAME AS object_name, COLUMN_NAME AS column_name,
                COLUMN_ID AS ordinal, DATA_TYPE AS data_type, DATA_LENGTH AS max_length, DATA_PRECISION AS "precision",
                DATA_SCALE AS "scale", NULLABLE AS is_nullable, DATA_DEFAULT AS column_default
                FROM ALL_TAB_COLUMNS WHERE OWNER=:schema ORDER BY TABLE_NAME, COLUMN_ID""", {"schema": schema})
            columns = self._rows(cursor)
            cursor.execute("""SELECT c.OWNER schema_name, c.TABLE_NAME object_name, c.CONSTRAINT_NAME constraint_name,
                CASE c.CONSTRAINT_TYPE WHEN 'P' THEN 'PRIMARY KEY' ELSE 'UNIQUE' END constraint_type,
                cc.COLUMN_NAME column_name, cc.POSITION ordinal FROM ALL_CONSTRAINTS c
                JOIN ALL_CONS_COLUMNS cc ON c.OWNER=cc.OWNER AND c.CONSTRAINT_NAME=cc.CONSTRAINT_NAME
                WHERE c.OWNER=:schema AND c.CONSTRAINT_TYPE IN ('P','U')""", {"schema": schema})
            constraints = self._rows(cursor)
        return _canonical_snapshot(self.source.database_name, objects, columns, constraints, self.engine)


def _canonical_snapshot(database: str, objects: list[dict], columns: list[dict], constraints: list[dict], engine: str) -> dict[str, Any]:
    by_object: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for column in columns:
        key = (str(column["schema_name"]), str(column["object_name"]))
        data_type = str(column.get("data_type") or "").lower()
        if engine in {"POSTGRESQL", "MYSQL", "ORACLE"} and data_type.startswith("timestamp"):
            data_type = "datetime"
        default = column.get("column_default")
        by_object.setdefault(key, []).append({
            "name": str(column["column_name"]), "ordinal": int(column.get("ordinal") or 0),
            "type": data_type, "declared_type": data_type, "system_type": data_type,
            "max_length": column.get("max_length"), "precision": column.get("precision"),
            "scale": column.get("scale"), "nullable": str(column.get("is_nullable", "YES")).upper() in {"YES", "Y", "TRUE", "1"},
            "identity": "nextval" in str(default or "").lower() or "auto_increment" in str(column.get("extra") or "").lower(),
            "computed": False, "default": None if default is None else str(default),
        })
    grouped: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for item in constraints:
        key = (str(item["schema_name"]), str(item["object_name"]))
        name = str(item["constraint_name"])
        target = grouped.setdefault(key, {}).setdefault(name, {"name": name, "type": str(item["constraint_type"]).replace(" ", "_"), "columns": []})
        target["columns"].append(str(item["column_name"]))
    return {"database": database, "objects": [{
        "database": database, "schema": str(obj["schema_name"]), "name": str(obj["object_name"]),
        "type": str(obj["object_type"]).upper(), "definition": None,
        "columns": by_object.get((str(obj["schema_name"]), str(obj["object_name"])), []),
        "dependencies": [], "parameters": [],
        "constraints": list(grouped.get((str(obj["schema_name"]), str(obj["object_name"])), {}).values()),
        "approx_row_count": None,
    } for obj in objects]}


def adapter_for_source(source: MigrationSource) -> BaseDatabaseAdapter:
    adapter = {"SQLSERVER": SQLServerAdapter, "POSTGRESQL": PostgreSQLAdapter,
               "MYSQL": MySQLAdapter, "ORACLE": OracleAdapter}[normalize_engine(source.engine)]
    return adapter(source)
