from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_TEMPLATE_REGISTRY_PATH = (
    PROJECT_ROOT / "data" / "template_registry" / "template_registry.yaml"
)


class TemplateRegistryEntry(BaseModel):
    """
    One template entry from template_registry.yaml.

    Example:
        template_id: MT_ECM_PRE_BASEPLAN
        external_system: ECM
        aliases:
          - Prepaid Base Plan ECM request
    """

    template_id: str = Field(description="ACT_MEDIATION_TEMPLATE.TEMPLATE_ID")
    external_system: str = Field(description="External system name")
    aliases: list[str] = Field(default_factory=list)


class TemplateRegistry(BaseModel):
    """
    Full template registry loaded from YAML.
    """

    version: int
    description: str = ""
    templates: list[TemplateRegistryEntry]


def load_template_registry(
    registry_path: Path = DEFAULT_TEMPLATE_REGISTRY_PATH,
) -> TemplateRegistry:
    """
    Load template_registry.yaml from disk and validate its structure.

    This function reads:
        data/template_registry/template_registry.yaml

    It returns a typed TemplateRegistry object.
    """
    if not registry_path.exists():
        raise FileNotFoundError(
            f"Template registry file not found: {registry_path}"
        )

    raw_data: dict[str, Any] = yaml.safe_load(
        registry_path.read_text(encoding="utf-8")
    )

    if raw_data is None:
        raise ValueError(f"Template registry file is empty: {registry_path}")

    return TemplateRegistry.model_validate(raw_data)


@lru_cache(maxsize=1)
def get_template_registry() -> TemplateRegistry:
    """
    Cached registry loader.

    The YAML file does not need to be re-read every time a graph node runs.
    """
    return load_template_registry()


def get_template_ids() -> list[str]:
    """
    Return all template IDs from the registry.
    """
    registry = get_template_registry()
    return [entry.template_id for entry in registry.templates]


if __name__ == "__main__":
    registry = get_template_registry()

    print("Registry version:", registry.version)
    print("Template count:", len(registry.templates))

    for entry in registry.templates[:5]:
        print(
            f"- {entry.template_id} | system={entry.external_system} | aliases={entry.aliases}"
        )