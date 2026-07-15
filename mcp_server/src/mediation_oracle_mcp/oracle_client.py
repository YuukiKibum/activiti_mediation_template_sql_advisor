from datetime import date, datetime
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any

import oracledb

from mediation_oracle_mcp.config import OracleMCPSettings, get_settings
from mediation_oracle_mcp.guards import (
    clamp_limit,
    clean_attribute_name,
    clean_search_keyword,
    normalize_template_id,
)


class OracleMediationRepository:
    """
    Read-only Oracle repository for ACT_MEDIATION_TEMPLATE
    and ACT_MEDIATION_PARAMETER.

    Important:
    This class intentionally exposes SELECT operations only.

    Do not add:
        - INSERT
        - UPDATE
        - DELETE
        - MERGE
        - ALTER
        - DROP
        - TRUNCATE
        - generic execute_sql(sql)
    """

    def __init__(self, settings: OracleMCPSettings | None = None) -> None:
        self.settings = settings or get_settings()
        self._pool: oracledb.ConnectionPool | None = None

    def _get_pool(self) -> oracledb.ConnectionPool:
        if self._pool is None:
            self._pool = oracledb.create_pool(
                user=self.settings.oracle_user,
                password=self.settings.oracle_password,
                dsn=self.settings.oracle_dsn,
                min=1,
                max=4,
                increment=1,
            )

        return self._pool

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None

    def _connect(self) -> oracledb.Connection:
        """
        Borrow a pooled Oracle connection for one repository operation.
        """
        return self._get_pool().acquire()

    def _release(self, connection: oracledb.Connection) -> None:
        self._get_pool().release(connection)

    @contextmanager
    def _borrow_connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            self._release(connection)

    @staticmethod
    def _convert_value(value: Any) -> Any:
        """
        Convert Oracle/Python values into MCP-friendly values.

        Why:
        - CLOB values need to be read into normal strings.
        - datetime/date values should become strings.
        - Decimal values should become int/float where possible.
        """
        if isinstance(value, oracledb.LOB):
            return value.read()

        if isinstance(value, datetime):
            return value.isoformat(sep=" ")

        if isinstance(value, date):
            return value.isoformat()

        if isinstance(value, Decimal):
            if value == value.to_integral_value():
                return int(value)
            return float(value)

        return value

    @classmethod
    def _rows_to_dicts(cls, cursor: oracledb.Cursor) -> list[dict[str, Any]]:
        """
        Convert Oracle cursor rows into list of dictionaries.

        Example output:
            [
                {
                    "template_id": "MT_ECM_PRE_BASEPLAN",
                    "template_description": "..."
                }
            ]
        """
        columns = [column[0].lower() for column in cursor.description or []]

        rows: list[dict[str, Any]] = []

        for row in cursor.fetchall():
            row_dict = {
                column: cls._convert_value(value)
                for column, value in zip(columns, row)
            }
            rows.append(row_dict)

        return rows

    def get_table_counts(self) -> dict[str, int]:
        """
        Return row counts for both mediation tables.
        """
        sql = """
            SELECT 'ACT_MEDIATION_TEMPLATE' AS table_name, COUNT(*) AS row_count
            FROM ACT_MEDIATION_TEMPLATE
            UNION ALL
            SELECT 'ACT_MEDIATION_PARAMETER' AS table_name, COUNT(*) AS row_count
            FROM ACT_MEDIATION_PARAMETER
        """

        with self._borrow_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql)
                rows = self._rows_to_dicts(cursor)

        return {
            row["table_name"]: int(row["row_count"])
            for row in rows
        }

    def template_exists(self, template_id: str) -> dict[str, Any]:
        """
        Check whether a TEMPLATE_ID exists.
        """
        template_id = normalize_template_id(template_id)

        sql = """
            SELECT COUNT(*) AS template_count
            FROM ACT_MEDIATION_TEMPLATE
            WHERE TEMPLATE_ID = :template_id
        """

        with self._borrow_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, {"template_id": template_id})
                count = cursor.fetchone()[0]

        return {
            "template_id": template_id,
            "exists": int(count) > 0,
            "count": int(count),
        }

    def get_template(self, template_id: str) -> dict[str, Any] | None:
        """
        Fetch one row from ACT_MEDIATION_TEMPLATE by TEMPLATE_ID.
        """
        template_id = normalize_template_id(template_id)

        sql = """
            SELECT
                TEMPLATE_ID,
                TEMPLATE_DESCRIPTION,
                CREATED_USER_ID,
                MODIFIED_USER_ID,
                CREATED_DATE,
                MODIFIED_DATE
            FROM ACT_MEDIATION_TEMPLATE
            WHERE TEMPLATE_ID = :template_id
        """

        with self._borrow_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, {"template_id": template_id})
                rows = self._rows_to_dicts(cursor)

        return rows[0] if rows else None

    def list_parameters_for_template(
        self,
        template_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        List ACT_MEDIATION_PARAMETER rows for one TEMPLATE_ID.
        """
        template_id = normalize_template_id(template_id)
        safe_limit = clamp_limit(limit)

        sql = f"""
            SELECT
                PARAM_ID,
                TEMPLATE_ID,
                ATTRIBUTE_NAME,
                CREATED_USER_ID,
                MODIFIED_USER_ID,
                CREATED_DATE,
                MODIFIED_DATE,
                ATTRIBUTE_VALUE
            FROM ACT_MEDIATION_PARAMETER
            WHERE TEMPLATE_ID = :template_id
            ORDER BY ATTRIBUTE_NAME
            FETCH FIRST {safe_limit} ROWS ONLY
        """

        with self._borrow_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, {"template_id": template_id})
                return self._rows_to_dicts(cursor)

    def get_parameter(
        self,
        template_id: str,
        attribute_name: str,
    ) -> dict[str, Any] | None:
        """
        Fetch one ACT_MEDIATION_PARAMETER row by TEMPLATE_ID and ATTRIBUTE_NAME.
        """
        template_id = normalize_template_id(template_id)
        attribute_name = clean_attribute_name(attribute_name)

        sql = """
            SELECT
                PARAM_ID,
                TEMPLATE_ID,
                ATTRIBUTE_NAME,
                CREATED_USER_ID,
                MODIFIED_USER_ID,
                CREATED_DATE,
                MODIFIED_DATE,
                ATTRIBUTE_VALUE
            FROM ACT_MEDIATION_PARAMETER
            WHERE TEMPLATE_ID = :template_id
              AND ATTRIBUTE_NAME = :attribute_name
        """

        with self._borrow_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql,
                    {
                        "template_id": template_id,
                        "attribute_name": attribute_name,
                    },
                )
                rows = self._rows_to_dicts(cursor)

        return rows[0] if rows else None

    def search_templates(
        self,
        keyword: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Search ACT_MEDIATION_TEMPLATE by TEMPLATE_ID or TEMPLATE_DESCRIPTION.
        """
        keyword = clean_search_keyword(keyword)
        safe_limit = clamp_limit(limit, maximum=50)

        sql = f"""
            SELECT
                TEMPLATE_ID,
                TEMPLATE_DESCRIPTION,
                CREATED_USER_ID,
                MODIFIED_USER_ID,
                CREATED_DATE,
                MODIFIED_DATE
            FROM ACT_MEDIATION_TEMPLATE
            WHERE UPPER(TEMPLATE_ID) LIKE '%' || :keyword || '%'
               OR UPPER(TEMPLATE_DESCRIPTION) LIKE '%' || :keyword || '%'
            ORDER BY TEMPLATE_ID
            FETCH FIRST {safe_limit} ROWS ONLY
        """

        with self._borrow_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, {"keyword": keyword})
                return self._rows_to_dicts(cursor)

    def search_parameters(
        self,
        keyword: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Search ACT_MEDIATION_PARAMETER by TEMPLATE_ID, ATTRIBUTE_NAME,
        or ATTRIBUTE_VALUE preview.

        ATTRIBUTE_VALUE is a CLOB, so we use DBMS_LOB.SUBSTR for searching.
        """
        keyword = clean_search_keyword(keyword)
        safe_limit = clamp_limit(limit, maximum=50)

        sql = f"""
            SELECT
                PARAM_ID,
                TEMPLATE_ID,
                ATTRIBUTE_NAME,
                CREATED_USER_ID,
                MODIFIED_USER_ID,
                CREATED_DATE,
                MODIFIED_DATE,
                ATTRIBUTE_VALUE
            FROM ACT_MEDIATION_PARAMETER
            WHERE UPPER(TEMPLATE_ID) LIKE '%' || :keyword || '%'
               OR UPPER(ATTRIBUTE_NAME) LIKE '%' || :keyword || '%'
               OR UPPER(DBMS_LOB.SUBSTR(ATTRIBUTE_VALUE, 4000, 1)) LIKE '%' || :keyword || '%'
            ORDER BY TEMPLATE_ID, ATTRIBUTE_NAME
            FETCH FIRST {safe_limit} ROWS ONLY
        """

        with self._borrow_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, {"keyword": keyword})
                return self._rows_to_dicts(cursor)

    def count_parameters_for_template(self, template_id: str) -> int:
        template_id = normalize_template_id(template_id)

        sql = """
            SELECT COUNT(*) AS parameter_count
            FROM ACT_MEDIATION_PARAMETER
            WHERE TEMPLATE_ID = :template_id
        """

        with self._borrow_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, {"template_id": template_id})
                count = cursor.fetchone()[0]

        return int(count)

    def list_dsl_sample_parameters_for_template(
        self,
        template_id: str,
        focus_attribute_name: str = "",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Return a small set of parameter rows for DSL syntax hints.

        Uses ATTRIBUTE_VALUE previews only (no full CLOB reads) so the advisor
        can pattern-match cheaply while rollback still uses get_parameter().
        """
        template_id = normalize_template_id(template_id)
        safe_limit = clamp_limit(limit, maximum=30)
        bind_focus = (
            clean_attribute_name(focus_attribute_name)
            if focus_attribute_name
            else None
        )

        sql = f"""
            SELECT
                PARAM_ID,
                TEMPLATE_ID,
                ATTRIBUTE_NAME,
                CREATED_USER_ID,
                MODIFIED_USER_ID,
                CREATED_DATE,
                MODIFIED_DATE,
                DBMS_LOB.SUBSTR(ATTRIBUTE_VALUE, 800, 1) AS ATTRIBUTE_VALUE
            FROM ACT_MEDIATION_PARAMETER
            WHERE TEMPLATE_ID = :template_id
            ORDER BY
                CASE
                    WHEN :focus_attribute_name IS NOT NULL
                     AND ATTRIBUTE_NAME = :focus_attribute_name
                    THEN 0
                    ELSE 1
                END,
                CASE
                    WHEN DBMS_LOB.SUBSTR(ATTRIBUTE_VALUE, 4000, 1) LIKE '%VAL_%'
                      OR DBMS_LOB.SUBSTR(ATTRIBUTE_VALUE, 4000, 1) LIKE '%#%'
                      OR DBMS_LOB.SUBSTR(ATTRIBUTE_VALUE, 4000, 1) LIKE '%|%'
                      OR DBMS_LOB.SUBSTR(ATTRIBUTE_VALUE, 4000, 1) LIKE '%$%'
                      OR DBMS_LOB.SUBSTR(ATTRIBUTE_VALUE, 4000, 1) LIKE '%;%'
                    THEN 0
                    ELSE 1
                END,
                ATTRIBUTE_NAME
            FETCH FIRST {safe_limit} ROWS ONLY
        """

        with self._borrow_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    sql,
                    {
                        "template_id": template_id,
                        "focus_attribute_name": bind_focus,
                    },
                )
                return self._rows_to_dicts(cursor)

    def inspect_template_for_advisor(
        self,
        template_id: str,
        attribute_name: str = "",
        target_attribute_name: str = "",
        focus_attribute_name: str = "",
        sample_limit: int = 20,
    ) -> dict[str, Any]:
        """
        Fetch advisor inspection context in parallel using the connection pool.

        Full ATTRIBUTE_VALUE is returned only for target parameter rows needed
        for rollback SQL. DSL sample rows use preview-only values.
        """
        template_id = normalize_template_id(template_id)
        attribute_name = clean_attribute_name(attribute_name) if attribute_name else ""
        target_attribute_name = (
            clean_attribute_name(target_attribute_name)
            if target_attribute_name
            else ""
        )
        focus_attribute_name = (
            clean_attribute_name(focus_attribute_name)
            if focus_attribute_name
            else attribute_name
        )

        tasks: dict[str, Any] = {
            "template_row": lambda: self.get_template(template_id),
            "sample_parameters": lambda: self.list_dsl_sample_parameters_for_template(
                template_id=template_id,
                focus_attribute_name=focus_attribute_name,
                limit=sample_limit,
            ),
            "parameter_count": lambda: self.count_parameters_for_template(template_id),
        }

        if attribute_name:
            tasks["parameter_row"] = lambda: self.get_parameter(
                template_id,
                attribute_name,
            )

        if target_attribute_name and target_attribute_name != attribute_name:
            tasks["target_parameter_row"] = lambda: self.get_parameter(
                template_id,
                target_attribute_name,
            )

        results: dict[str, Any] = {}

        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            futures = {
                executor.submit(task): key
                for key, task in tasks.items()
            }

            for future in futures:
                key = futures[future]
                results[key] = future.result()

        template_row = results.get("template_row")
        parameter_row = results.get("parameter_row")
        target_parameter_row = results.get("target_parameter_row")

        if (
            target_attribute_name
            and target_attribute_name == attribute_name
            and parameter_row is not None
        ):
            target_parameter_row = parameter_row

        return {
            "template_id": template_id,
            "template_exists": template_row is not None,
            "template_row": template_row,
            "parameter_row": parameter_row,
            "target_parameter_row": target_parameter_row,
            "sample_parameters": results.get("sample_parameters", []),
            "all_parameter_count": int(results.get("parameter_count", 0)),
        }