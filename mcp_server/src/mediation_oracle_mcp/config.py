from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class OracleMCPSettings:
    """
    Application settings for the Oracle MCP server.

    frozen=True means once this object is created, its values should not change.
    That is useful for configuration objects.
    """

    oracle_user: str
    oracle_password: str
    oracle_dsn: str
    server_name: str
    transport: str


def get_settings() -> OracleMCPSettings:
    """
    Load required MCP + Oracle settings from .env.

    This function fails early if required Oracle settings are missing.
    That is better than failing later when the agent tries to call a DB tool.
    """
    oracle_user = os.getenv("ORACLE_USER", "").strip()
    oracle_password = os.getenv("ORACLE_PASSWORD", "").strip()
    oracle_dsn = os.getenv("ORACLE_DSN", "").strip()

    missing = []

    if not oracle_user:
        missing.append("ORACLE_USER")

    if not oracle_password:
        missing.append("ORACLE_PASSWORD")

    if not oracle_dsn:
        missing.append("ORACLE_DSN")

    if missing:
        raise RuntimeError(
            "Missing required Oracle environment variables: "
            + ", ".join(missing)
        )

    return OracleMCPSettings(
        oracle_user=oracle_user,
        oracle_password=oracle_password,
        oracle_dsn=oracle_dsn,
        server_name=os.getenv(
            "MCP_ORACLE_SERVER_NAME",
            "Activiti Mediation Oracle MCP",
        ).strip(),
        transport=os.getenv("MCP_ORACLE_TRANSPORT", "stdio").strip(),
    )