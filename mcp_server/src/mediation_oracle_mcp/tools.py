from typing import Any

from mcp.server.fastmcp import FastMCP

from mediation_oracle_mcp.oracle_client import OracleMediationRepository


repo = OracleMediationRepository()


def register_tools(mcp: FastMCP) -> None:
    """
    Register read-only Oracle tools with the MCP server.

    Important:
    These tools only call SELECT-based repository methods.
    They do not perform INSERT, UPDATE, DELETE, MERGE, DROP, ALTER, or TRUNCATE.
    """

    @mcp.tool()
    def get_table_counts() -> dict[str, int]:
        """
        Return row counts for ACT_MEDIATION_TEMPLATE and ACT_MEDIATION_PARAMETER.

        Use this to verify that the MCP server can connect to Oracle
        and see the expected mediation tables.

        This is a read-only SELECT operation.
        """
        return repo.get_table_counts()

    @mcp.tool()
    def template_exists(template_id: str) -> dict[str, Any]:
        """
        Check whether a TEMPLATE_ID exists in ACT_MEDIATION_TEMPLATE.

        Args:
            template_id: Example: MT_ECM_PRE_BASEPLAN

        This is a read-only SELECT operation.
        """
        return repo.template_exists(template_id)

    @mcp.tool()
    def get_template(template_id: str) -> dict[str, Any] | None:
        """
        Fetch one row from ACT_MEDIATION_TEMPLATE by TEMPLATE_ID.

        Args:
            template_id: Example: MT_ECM_PRE_BASEPLAN

        This is a read-only SELECT operation.
        """
        return repo.get_template(template_id)

    @mcp.tool()
    def list_parameters_for_template(
        template_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        List ACT_MEDIATION_PARAMETER rows for a TEMPLATE_ID.

        Args:
            template_id: Example: MT_ECM_PRE_BASEPLAN
            limit: Maximum number of rows to return.

        This is useful when the agent needs to inspect all attributes
        configured for one template.

        This is a read-only SELECT operation.
        """
        return repo.list_parameters_for_template(
            template_id=template_id,
            limit=limit,
        )

    @mcp.tool()
    def get_parameter(
        template_id: str,
        attribute_name: str,
    ) -> dict[str, Any] | None:
        """
        Fetch one ACT_MEDIATION_PARAMETER row by TEMPLATE_ID and ATTRIBUTE_NAME.

        Args:
            template_id: Example: MT_ECM_PRE_BASEPLAN
            attribute_name: Example: poAttributes

        This is useful when the agent needs to inspect the current value
        before recommending an UPDATE statement.

        This is a read-only SELECT operation.
        """
        return repo.get_parameter(
            template_id=template_id,
            attribute_name=attribute_name,
        )

    @mcp.tool()
    def search_templates(
        keyword: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Search ACT_MEDIATION_TEMPLATE by TEMPLATE_ID or TEMPLATE_DESCRIPTION.

        Args:
            keyword: Search text, example: BASEPLAN
            limit: Maximum number of rows to return.

        This is useful when the user gives a vague product/system name
        and the agent needs to find possible TEMPLATE_ID values.

        This is a read-only SELECT operation.
        """
        return repo.search_templates(
            keyword=keyword,
            limit=limit,
        )

    @mcp.tool()
    def search_parameters(
        keyword: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Search ACT_MEDIATION_PARAMETER by TEMPLATE_ID, ATTRIBUTE_NAME,
        or ATTRIBUTE_VALUE preview.

        Args:
            keyword: Search text, example: addToBill or poAttributes
            limit: Maximum number of rows to return.

        This is useful when the agent needs to find where a certain
        attribute or expression appears.

        This is a read-only SELECT operation.
        """
        return repo.search_parameters(
            keyword=keyword,
            limit=limit,
        )

    @mcp.tool()
    def inspect_template_for_advisor(
        template_id: str,
        attribute_name: str = "",
        target_attribute_name: str = "",
        focus_attribute_name: str = "",
        sample_limit: int = 20,
    ) -> dict[str, Any]:
        """
        Fetch advisor inspection context in one pooled, parallelized read.

        Returns template metadata, full target parameter rows for rollback,
        and preview-only DSL sample rows.
        """
        return repo.inspect_template_for_advisor(
            template_id=template_id,
            attribute_name=attribute_name,
            target_attribute_name=target_attribute_name,
            focus_attribute_name=focus_attribute_name,
            sample_limit=sample_limit,
        )