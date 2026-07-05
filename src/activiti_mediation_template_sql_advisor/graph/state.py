from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage

from langgraph.graph.message import add_messages


OperationType = Literal[
    "rename_attribute",
    "append_attribute_value",
    "update_attribute_value",
    "add_attribute",
    "unknown",
]


class AdvisorState(TypedDict, total=False):
    """
    Shared LangGraph state for the Activiti Mediation Template SQL Advisor.

    Every graph node receives this state and returns partial updates to it.

    Example:
        planner_node reads:
            user_requirement

        planner_node writes:
            operation_type
            template_id
            attribute_name

        oracle_inspection_node reads:
            template_id
            attribute_name

        oracle_inspection_node writes:
            current_template
            current_parameter
    """

    # Optional conversation messages.
    # add_messages tells LangGraph how to append messages instead of replacing them.
    messages: Annotated[list[AnyMessage], add_messages]

    # Original user input.
    user_requirement: str

    # What kind of change the user is asking for.
    operation_type: OperationType

    # Template / parameter details extracted from the requirement.
    template_id: str
    attribute_name: str
    new_attribute_name: str
    new_attribute_value: str
    value_to_append: str

    # RAG information from Pinecone documentation retrieval.
    rag_query: str
    rag_context: list[dict[str, Any]]

    # Oracle/MCP inspection results.
    template_exists: bool
    current_template: dict[str, Any] | None
    current_parameter: dict[str, Any] | None
    related_parameters: list[dict[str, Any]]

    # SQL advisor output.
    generated_sql: list[str]
    rollback_sql: list[str]

    # Safety and validation output.
    validation_errors: list[str]
    warnings: list[str]

    # Final response to show the user.
    final_answer: str


def create_initial_state(user_requirement: str) -> AdvisorState:
    """
    Create the initial graph state from a raw user requirement.

    We keep default values explicit so later graph nodes can safely read fields
    without constantly checking whether keys exist.
    """
    return AdvisorState(
        messages=[],
        user_requirement=user_requirement,
        operation_type="unknown",
        template_id="",
        attribute_name="",
        new_attribute_name="",
        new_attribute_value="",
        value_to_append="",
        rag_query="",
        rag_context=[],
        template_exists=False,
        current_template=None,
        current_parameter=None,
        related_parameters=[],
        generated_sql=[],
        rollback_sql=[],
        validation_errors=[],
        warnings=[],
        final_answer="",
    )