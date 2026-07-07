import os
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.documents import Document
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore


load_dotenv()


PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
PINECONE_NAMESPACE = os.getenv("PINECONE_NAMESPACE", "activiti-mediation-template-docs")
OPENAI_CHAT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-nano")

if not PINECONE_INDEX_NAME:
    raise RuntimeError("PINECONE_INDEX_NAME is not configured in .env")


embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    show_progress_bar=False,
)

vectorstore = PineconeVectorStore(
    index_name=PINECONE_INDEX_NAME,
    embedding=embeddings,
    namespace=PINECONE_NAMESPACE,
)


def _source_name(doc: Document) -> str:
    """
    Returns a readable source name for display.
    """
    source_file = doc.metadata.get("source_file")

    if source_file:
        return str(source_file)

    source = doc.metadata.get("source", "Unknown")

    try:
        return Path(str(source)).name
    except Exception:
        return str(source)


def _document_to_context_item(
    doc: Document,
    score: float | None = None,
) -> Dict[str, Any]:
    """
    Converts a LangChain Document into a clean dictionary that our LangGraph
    nodes can use directly.
    """
    return {
        "content": doc.page_content,
        "source": _source_name(doc),
        "score": score,
        "metadata": dict(doc.metadata or {}),
    }


def retrieve_documents(
    query: str,
    top_k: int = 1,
) -> List[Document]:
    """
    Retrieve raw LangChain Document objects from Pinecone.

    Use this when another LangChain/LangGraph component wants the original
    Document objects.
    """
    if not query or not query.strip():
        return []

    retriever = vectorstore.as_retriever(
        search_kwargs={
            "k": top_k,
        }
    )

    return retriever.invoke(query)


def retrieve_documents_with_scores(
    query: str,
    top_k: int = 5,
) -> List[tuple[Document, float]]:
    """
    Retrieve LangChain Document objects with similarity scores.

    This is useful for debugging and for final answer traceability.
    """
    if not query or not query.strip():
        return []

    return vectorstore.similarity_search_with_score(
        query=query,
        k=top_k,
    )


def retrieve_context(
    query: str,
    top_k: int = 5,
    include_scores: bool = True,
) -> List[Dict[str, Any]]:
    """
    Main retrieval function for the Activiti Mediation SQL Advisor.

    This is the function our LangGraph RAG node should call.

    Returns:
        [
            {
                "content": "...",
                "source": "The Activiti Mediation Expression.docx",
                "score": 0.87,
                "metadata": {...}
            }
        ]
    """
    if include_scores:
        docs_with_scores = retrieve_documents_with_scores(query=query, top_k=top_k)

        return [
            _document_to_context_item(doc, score=score)
            for doc, score in docs_with_scores
        ]

    docs = retrieve_documents(query=query, top_k=top_k)

    return [
        _document_to_context_item(doc)
        for doc in docs
    ]


def format_context_for_prompt(context_items: List[Dict[str, Any]]) -> str:
    """
    Converts retrieved context items into readable text for an LLM prompt.
    """
    if not context_items:
        return "No relevant Activiti mediation documentation was retrieved."

    formatted_parts: List[str] = []

    for index, item in enumerate(context_items, start=1):
        source = item.get("source", "Unknown")
        metadata = item.get("metadata") or {}
        doc_category = metadata.get("doc_category", "unknown")
        chunk_index = metadata.get("chunk_index", "unknown")
        content = item.get("content", "")

        formatted_parts.append(
            "\n".join(
                [
                    f"[Context {index}]",
                    f"Source: {source}",
                    f"Category: {doc_category}",
                    f"Chunk Index: {chunk_index}",
                    "Content:",
                    content,
                ]
            )
        )

    return "\n\n---\n\n".join(formatted_parts)


@tool(response_format="content_and_artifact")
def retrieve_activiti_context(query: str):
    """
    Retrieve relevant Activiti mediation documentation.

    Use this to answer questions about:
    - Activiti mediation expression language
    - ATTRIBUTE_VALUE syntax
    - ACT_MEDIATION_TEMPLATE
    - ACT_MEDIATION_PARAMETER
    - SQL change requirements
    - expression parsing rules
    """
    context_items = retrieve_context(query=query, top_k=5, include_scores=True)

    serialized = format_context_for_prompt(context_items)

    return serialized, context_items


def run_llm(query: str) -> Dict[str, Any]:
    """
    Optional test function.

    This creates a small retrieval-enabled agent that answers questions using
    the Activiti mediation documents from Pinecone.

    This is not the final LangGraph workflow. It is only useful for checking
    whether retrieval works.
    """
    model = init_chat_model(
        OPENAI_CHAT_MODEL,
        model_provider="openai",
    )

    system_prompt = """
You are an Activiti Mediation documentation assistant.

You answer questions using the retrieved Activiti mediation documents.

You have access to a retrieval tool that searches:
- The Activiti Mediation Expression guide
- The Objective document
- Any other indexed mediation SQL/template documents

Rules:
1. Use the retrieval tool before answering.
2. Answer only from retrieved context.
3. If the retrieved context does not contain the answer, say that the indexed documents do not contain enough information.
4. When explaining ATTRIBUTE_VALUE expressions, clearly mention the source attribute, mapping rule, output value, and expression syntax.
5. Do not generate SQL unless the user explicitly asks for SQL.
"""

    agent = create_agent(
        model,
        tools=[retrieve_activiti_context],
        system_prompt=system_prompt,
    )

    messages = [
        {
            "role": "user",
            "content": query,
        }
    ]

    response = agent.invoke({"messages": messages})

    answer = response["messages"][-1].content

    context_items: List[Dict[str, Any]] = []

    for message in response["messages"]:
        if isinstance(message, ToolMessage) and getattr(message, "artifact", None):
            if isinstance(message.artifact, list):
                context_items.extend(message.artifact)

    return {
        "answer": answer,
        "context": context_items,
    }


if __name__ == "__main__":
    result = run_llm(
        query=(
            "How should the expression addToBill#false|false,true|true "
            "be understood?"
        )
    )

    print("ANSWER:")
    print(result["answer"])

    print("\nRETRIEVED CONTEXT:")
    for item in result["context"]:
        print("-" * 80)
        print(f"Source: {item.get('source')}")
        print(f"Score: {item.get('score')}")
        print((item.get("content") or "")[:500])