from datetime import date, datetime
from decimal import Decimal
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

    def _connect(self) -> oracledb.Connection:
        """
        Create a new Oracle connection.

        For now, we open a connection per method call.
        This is simple and good for learning/testing.

        Later, if needed, we can improve this with connection pooling.
        """
        return oracledb.connect(
            user=self.settings.oracle_user,
            password=self.settings.oracle_password,
            dsn=self.settings.oracle_dsn,
        )

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

        with self._connect() as connection:
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

        with self._connect() as connection:
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

        with self._connect() as connection:
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

        with self._connect() as connection:
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

        with self._connect() as connection:
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

        with self._connect() as connection:
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

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, {"keyword": keyword})
                return self._rows_to_dicts(cursor)