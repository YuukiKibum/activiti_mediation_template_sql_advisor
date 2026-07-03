# Activiti Mediation Template SQL Advisor

This project is an AI-assisted SQL recommendation agent for Activiti mediation template configuration.

The agent accepts natural-language requirements and generates SQL scripts for human review only.

It does not execute DML operations such as `INSERT`, `UPDATE`, or `DELETE`.

## Main Goals

- Resolve `TEMPLATE_ID` from a controlled template registry.
- Fetch existing template and parameter details from Oracle using an MCP server.
- Understand Activiti mediation expression language.
- Convert natural-language mapping requirements into valid Activiti expression syntax.
- Generate pre-check SQL, change SQL, and rollback SQL.
- Keep all SQL execution manual and human-reviewed.

## Main Tables

- `ACT_MEDIATION_TEMPLATE`
- `ACT_MEDIATION_PARAMETER`

## Planned Architecture

```text
User requirement
    ↓
LangGraph workflow
    ↓
Template registry
    ↓
MCP Oracle read-only tools
    ↓
RAG expression reference
    ↓
Expression compiler and validator
    ↓
SQL builder and validator
    ↓
Final SQL recommendation
```

## Safety Rule

The agent only recommends SQL. It must never directly execute production changes.