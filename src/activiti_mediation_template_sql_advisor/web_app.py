from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from activiti_mediation_template_sql_advisor.graph.builder import run_advisor


app = FastAPI(
    title="Activiti Mediation Template SQL Advisor",
    version="0.1.0",
)


class AdvisorRequest(BaseModel):
    requirement: str


def _preview(value: str, max_length: int = 900) -> str:
    value = value or ""

    if len(value) <= max_length:
        return value

    return value[:max_length] + "..."


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    return HTML_PAGE


@app.post("/api/advisor")
async def advisor(request: AdvisorRequest) -> dict[str, Any]:
    final_state = await run_advisor(request.requirement)

    current_parameter = final_state.get("current_parameter") or {}
    current_template = final_state.get("current_template") or {}

    attribute_value = str(current_parameter.get("attribute_value") or "")

    return {
        "requirement": final_state.get("user_requirement", ""),
        "operation_type": final_state.get("operation_type", "unknown"),
        "template_id": final_state.get("template_id", ""),
        "template_external_system": final_state.get("template_external_system", ""),
        "template_resolution_match_type": final_state.get(
            "template_resolution_match_type", ""
        ),
        "template_resolution_matched_text": final_state.get(
            "template_resolution_matched_text", ""
        ),
        "template_resolution_score": final_state.get(
            "template_resolution_score", 0.0
        ),
        "template_resolution_reason": final_state.get(
            "template_resolution_reason", ""
        ),
        "attribute_name": final_state.get("attribute_name", ""),
        "new_attribute_name": final_state.get("new_attribute_name", ""),
        "new_attribute_value": final_state.get("new_attribute_value", ""),
        "value_to_append": final_state.get("value_to_append", ""),
        "expression_compilation_did_compile": final_state.get(
            "expression_compilation_did_compile", False
        ),
        "expression_compilation_confidence": final_state.get(
            "expression_compilation_confidence", 0.0
        ),
        "expression_compilation_reason": final_state.get(
            "expression_compilation_reason", ""
        ),
        "expression_compilation_warnings": final_state.get(
            "expression_compilation_warnings", []
        ),
        "current_template": current_template,
        "current_parameter": {
            "param_id": current_parameter.get("param_id"),
            "template_id": current_parameter.get("template_id"),
            "attribute_name": current_parameter.get("attribute_name"),
            "attribute_value_preview": _preview(attribute_value),
        }
        if current_parameter
        else None,
        "rag_sources": [
            {
                "source": item.get("source", "Unknown"),
                "score": item.get("score"),
                "content_preview": _preview(str(item.get("content") or ""), 500),
            }
            for item in final_state.get("rag_context", [])
        ],
        "generated_sql": final_state.get("generated_sql", []),
        "rollback_sql": final_state.get("rollback_sql", []),
        "warnings": final_state.get("warnings", []),
        "validation_errors": final_state.get("validation_errors", []),
        "final_answer": final_state.get("final_answer", ""),
    }


HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Activiti Mediation Template SQL Advisor</title>

    <style>
        :root {
            --bg: #f4f7fb;
            --card: #ffffff;
            --text: #172033;
            --muted: #697386;
            --border: #dbe3ef;
            --primary: #b00020;
            --primary-dark: #7f0017;
            --soft-primary: #fff1f3;
            --green: #0f766e;
            --amber: #b45309;
            --red: #b91c1c;
            --blue: #1d4ed8;
            --code-bg: #101827;
            --code-text: #e5eefc;
            --shadow: 0 18px 45px rgba(15, 23, 42, 0.08);
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            font-family: Arial, Helvetica, sans-serif;
            background:
                radial-gradient(circle at top left, rgba(176, 0, 32, 0.08), transparent 32%),
                linear-gradient(135deg, #f8fbff 0%, var(--bg) 100%);
            color: var(--text);
        }

        .page {
            max-width: 1280px;
            margin: 0 auto;
            padding: 32px;
        }

        .hero {
            background: linear-gradient(135deg, #111827 0%, #3a0b15 55%, var(--primary-dark) 100%);
            color: white;
            border-radius: 28px;
            padding: 34px;
            box-shadow: var(--shadow);
            position: relative;
            overflow: hidden;
        }

        .hero::after {
            content: "";
            position: absolute;
            right: -80px;
            top: -80px;
            width: 260px;
            height: 260px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.09);
        }

        .eyebrow {
            font-size: 13px;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            opacity: 0.8;
            margin-bottom: 12px;
        }

        h1 {
            margin: 0;
            font-size: 36px;
            line-height: 1.08;
        }

        .hero p {
            max-width: 820px;
            color: rgba(255, 255, 255, 0.82);
            font-size: 16px;
            line-height: 1.6;
        }

        .status-row {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 22px;
        }

        .status-pill {
            border: 1px solid rgba(255, 255, 255, 0.24);
            background: rgba(255, 255, 255, 0.1);
            color: white;
            border-radius: 999px;
            padding: 9px 13px;
            font-size: 13px;
            font-weight: 700;
        }

        .grid {
            display: grid;
            grid-template-columns: 420px 1fr;
            gap: 22px;
            margin-top: 24px;
            align-items: start;
        }

        .card {
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 24px;
            padding: 22px;
            box-shadow: var(--shadow);
        }

        .card h2 {
            margin: 0 0 14px;
            font-size: 18px;
        }

        .label {
            font-size: 13px;
            font-weight: 700;
            color: var(--muted);
            margin-bottom: 8px;
        }

        textarea {
            width: 100%;
            min-height: 190px;
            resize: vertical;
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 15px;
            font-size: 14px;
            line-height: 1.5;
            outline: none;
            color: var(--text);
            background: #fbfdff;
        }

        textarea:focus {
            border-color: var(--primary);
            box-shadow: 0 0 0 4px rgba(176, 0, 32, 0.08);
        }

        .button-row {
            display: flex;
            gap: 10px;
            margin-top: 14px;
        }

        button {
            border: 0;
            border-radius: 14px;
            padding: 12px 16px;
            font-weight: 700;
            cursor: pointer;
            transition: transform 0.12s ease, opacity 0.12s ease;
        }

        button:hover {
            transform: translateY(-1px);
        }

        .primary-button {
            background: var(--primary);
            color: white;
            flex: 1;
        }

        .secondary-button {
            background: #eef2f7;
            color: var(--text);
        }

        .examples {
            margin-top: 18px;
            display: grid;
            gap: 10px;
        }

        .example {
            text-align: left;
            background: #fbfdff;
            border: 1px solid var(--border);
            color: var(--text);
            font-weight: 700;
            border-radius: 16px;
            padding: 12px;
        }

        .example small {
            display: block;
            margin-top: 4px;
            color: var(--muted);
            font-weight: 600;
            line-height: 1.35;
        }

        .result-stack {
            display: grid;
            gap: 18px;
        }

        .empty-state {
            text-align: center;
            padding: 70px 24px;
            color: var(--muted);
        }

        .summary-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 14px;
        }

        .mini-card {
            background: #fbfdff;
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 15px;
        }

        .mini-label {
            color: var(--muted);
            font-size: 12px;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 8px;
        }

        .mini-value {
            font-size: 15px;
            font-weight: 800;
            overflow-wrap: anywhere;
        }

        .badge {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 6px 10px;
            font-size: 12px;
            font-weight: 800;
            background: var(--soft-primary);
            color: var(--primary);
            border: 1px solid rgba(176, 0, 32, 0.16);
            white-space: nowrap;
        }

        .badge.green {
            background: #ecfdf5;
            color: var(--green);
            border-color: #99f6e4;
        }

        .badge.amber {
            background: #fffbeb;
            color: var(--amber);
            border-color: #fde68a;
        }

        .badge.red {
            background: #fef2f2;
            color: var(--red);
            border-color: #fecaca;
        }

        .badge.blue {
            background: #eff6ff;
            color: var(--blue);
            border-color: #bfdbfe;
        }

        .section-title-row {
            display: flex;
            justify-content: space-between;
            gap: 12px;
            align-items: center;
            margin-bottom: 12px;
        }

        .kv {
            display: grid;
            grid-template-columns: 190px 1fr;
            gap: 8px 14px;
            font-size: 14px;
        }

        .kv-key {
            color: var(--muted);
            font-weight: 800;
        }

        .kv-value {
            overflow-wrap: anywhere;
        }

        .source-list {
            display: grid;
            gap: 10px;
        }

        .source-item {
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 13px;
            background: #fbfdff;
        }

        .source-title {
            font-weight: 800;
            margin-bottom: 6px;
            display: flex;
            gap: 8px;
            align-items: center;
            flex-wrap: wrap;
        }

        .source-preview {
            color: var(--muted);
            font-size: 13px;
            line-height: 1.45;
        }

        pre {
            margin: 0;
            background: var(--code-bg);
            color: var(--code-text);
            padding: 18px;
            border-radius: 18px;
            overflow-x: auto;
            white-space: pre-wrap;
            line-height: 1.5;
            font-size: 13px;
        }

        .message-list {
            display: grid;
            gap: 10px;
        }

        .message {
            border-radius: 14px;
            padding: 12px;
            font-size: 14px;
            line-height: 1.45;
        }

        .message.warning {
            background: #fffbeb;
            color: #92400e;
            border: 1px solid #fde68a;
        }

        .message.error {
            background: #fef2f2;
            color: #991b1b;
            border: 1px solid #fecaca;
        }

        .loading {
            display: none;
            margin-top: 14px;
            color: var(--muted);
            font-size: 14px;
            line-height: 1.45;
        }

        .loading.active {
            display: block;
        }

        .spinner {
            display: inline-block;
            width: 13px;
            height: 13px;
            border: 2px solid #cbd5e1;
            border-top-color: var(--primary);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            vertical-align: -2px;
            margin-right: 6px;
        }

        .footer-note {
            color: var(--muted);
            font-size: 12px;
            line-height: 1.45;
            margin-top: 14px;
        }

        @keyframes spin {
            to {
                transform: rotate(360deg);
            }
        }

        @media (max-width: 980px) {
            .grid {
                grid-template-columns: 1fr;
            }

            .summary-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }

        @media (max-width: 620px) {
            .page {
                padding: 16px;
            }

            h1 {
                font-size: 28px;
            }

            .summary-grid {
                grid-template-columns: 1fr;
            }

            .kv {
                grid-template-columns: 1fr;
            }

            .button-row {
                flex-direction: column;
            }
        }
    </style>
</head>

<body>
    <main class="page">
        <section class="hero">
            <div class="eyebrow">AI Configuration Advisor</div>
            <h1>Activiti Mediation Template SQL Advisor</h1>
            <p>
                Converts natural-language mediation template changes into safe advisory SQL,
                using template registry resolution, RAG documentation, expression compilation,
                Oracle inspection through MCP, deterministic SQL generation, and rollback SQL.
            </p>

            <div class="status-row">
                <span class="status-pill">LangGraph Workflow</span>
                <span class="status-pill">Template Registry</span>
                <span class="status-pill">Expression Compiler</span>
                <span class="status-pill">Pinecone RAG</span>
                <span class="status-pill">Oracle MCP Inspection</span>
                <span class="status-pill">Rollback SQL</span>
            </div>
        </section>

        <section class="grid">
            <aside class="card">
                <h2>Requirement</h2>
                <div class="label">Enter a mediation template change request</div>

                <textarea id="requirement">For prepaid base plan rtf template, add a new attribute gundu with value 123</textarea>

                <div class="button-row">
                    <button class="primary-button" onclick="runAdvisor()">
                        Generate SQL Advisory
                    </button>
                    <button class="secondary-button" onclick="clearResults()">
                        Clear
                    </button>
                </div>

                <div id="loading" class="loading">
                    <span class="spinner"></span>
                    Running planner, template registry resolver, RAG retrieval,
                    expression compiler, Oracle MCP inspection, and SQL generator...
                </div>

                <div class="examples">
                    <button class="example" onclick="setExample(1)">
                        Rename attribute
                        <small>Business phrase → exact ECM template → rename SQL</small>
                    </button>

                    <button class="example" onclick="setExample(2)">
                        Add static value
                        <small>Plain value 123 → Activiti expression VAL_123</small>
                    </button>

                    <button class="example" onclick="setExample(3)">
                        Duplicate prevention
                        <small>Existing AddToBillFlag should block INSERT</small>
                    </button>

                    <button class="example" onclick="setExample(4)">
                        Update static value
                        <small>Base Plan → VAL_Base Plan</small>
                    </button>

                    <button class="example" onclick="setExample(5)">
                        Missing template guardrail
                        <small>Unknown XYZ template should not be guessed</small>
                    </button>
                </div>

                <div class="footer-note">
                    This demo generates advisory SQL only. It does not execute DML against Oracle.
                </div>
            </aside>

            <section id="results" class="result-stack">
                <div class="card empty-state">
                    <h2>Ready for demo</h2>
                    <p>
                        Submit a requirement to see planner output, template resolution,
                        expression compilation, Oracle inspection, generated SQL,
                        rollback SQL, warnings, and RAG sources.
                    </p>
                </div>
            </section>
        </section>
    </main>

    <script>
        const examples = {
            1: "For Prepaid Base Plan ECM request, rename existing attribute poAttributes to poAttributeList.",
            2: "For prepaid base plan rtf template, add a new attribute gundu with value 123",
            3: "For Prepaid Base Plan RTF request, add AddToBillFlag. If addToBill is false set false, otherwise true.",
            4: "For Prepaid STK Notify Store request, change POType from Add-on to Base Plan.",
            5: "For Prepaid Base Plan XYZ request, add AddToBillFlagCopy with addToBill false as false and true as true."
        };

        function setExample(number) {
            document.getElementById("requirement").value = examples[number];
        }

        function clearResults() {
            document.getElementById("results").innerHTML = `
                <div class="card empty-state">
                    <h2>Ready for demo</h2>
                    <p>
                        Submit a requirement to see planner output, template resolution,
                        expression compilation, Oracle inspection, generated SQL,
                        rollback SQL, warnings, and RAG sources.
                    </p>
                </div>
            `;
        }

        function escapeHtml(value) {
            return String(value ?? "")
                .replaceAll("&", "&amp;")
                .replaceAll("<", "&lt;")
                .replaceAll(">", "&gt;")
                .replaceAll('"', "&quot;")
                .replaceAll("'", "&#039;");
        }

        function formatSql(statements) {
            if (!statements || statements.length === 0) {
                return "No SQL generated.";
            }

            return statements.join("\\n\\n");
        }

        function badgeClassForMatch(matchType) {
            if (matchType === "template_id_exact" || matchType === "alias_exact") {
                return "badge green";
            }

            if (matchType === "alias_fuzzy") {
                return "badge amber";
            }

            return "badge red";
        }

        function renderMessages(title, messages, type) {
            if (!messages || messages.length === 0) {
                return "";
            }

            return `
                <div class="card">
                    <div class="section-title-row">
                        <h2>${escapeHtml(title)}</h2>
                    </div>
                    <div class="message-list">
                        ${messages.map(message => `
                            <div class="message ${type}">
                                ${escapeHtml(message)}
                            </div>
                        `).join("")}
                    </div>
                </div>
            `;
        }

        function renderSources(sources) {
            if (!sources || sources.length === 0) {
                return `
                    <div class="source-item">
                        <div class="source-title">No RAG sources retrieved</div>
                    </div>
                `;
            }

            return sources.map(source => `
                <div class="source-item">
                    <div class="source-title">
                        ${escapeHtml(source.source)}
                        ${source.score !== null && source.score !== undefined
                            ? `<span class="badge blue">score ${escapeHtml(source.score)}</span>`
                            : ""}
                    </div>
                    <div class="source-preview">${escapeHtml(source.content_preview)}</div>
                </div>
            `).join("");
        }

        function renderCurrentOracleConfig(data) {
            if (data.current_parameter) {
                return `
                    <div class="kv">
                        <div class="kv-key">PARAM_ID</div>
                        <div class="kv-value">${escapeHtml(data.current_parameter.param_id)}</div>

                        <div class="kv-key">TEMPLATE_ID</div>
                        <div class="kv-value">${escapeHtml(data.current_parameter.template_id)}</div>

                        <div class="kv-key">ATTRIBUTE_NAME</div>
                        <div class="kv-value">${escapeHtml(data.current_parameter.attribute_name)}</div>
                    </div>

                    <br />

                    <pre>${escapeHtml(data.current_parameter.attribute_value_preview)}</pre>
                `;
            }

            if (data.operation_type === "add_attribute" && !data.validation_errors?.length) {
                return `
                    <p style="color: var(--muted);">
                        No current parameter row found. This is expected for a new attribute insert.
                    </p>
                `;
            }

            return `
                <p style="color: var(--muted);">
                    No current parameter row found.
                </p>
            `;
        }

        function compiledValue(data) {
            if (data.operation_type === "append_attribute_value") {
                return data.value_to_append || "Not applicable";
            }

            if (data.operation_type === "add_attribute" || data.operation_type === "update_attribute_value") {
                return data.new_attribute_value || "Not applicable";
            }

            return "Not applicable";
        }

        function renderResults(data) {
            const matchBadgeClass = badgeClassForMatch(data.template_resolution_match_type);
            const hasErrors = data.validation_errors && data.validation_errors.length > 0;

            const expressionBadgeClass = data.expression_compilation_did_compile
                ? "badge green"
                : "badge amber";

            const expressionBadgeText = data.expression_compilation_did_compile
                ? "compiled"
                : "not required";

            document.getElementById("results").innerHTML = `
                <div class="card">
                    <div class="section-title-row">
                        <h2>Advisor Summary</h2>
                        <span class="${hasErrors ? "badge red" : "badge green"}">
                            ${hasErrors ? "Validation blocked" : "SQL advisory generated"}
                        </span>
                    </div>

                    <div class="summary-grid">
                        <div class="mini-card">
                            <div class="mini-label">Operation</div>
                            <div class="mini-value">${escapeHtml(data.operation_type)}</div>
                        </div>

                        <div class="mini-card">
                            <div class="mini-label">Template ID</div>
                            <div class="mini-value">${escapeHtml(data.template_id || "Not resolved")}</div>
                        </div>

                        <div class="mini-card">
                            <div class="mini-label">External system</div>
                            <div class="mini-value">${escapeHtml(data.template_external_system || "Unknown")}</div>
                        </div>

                        <div class="mini-card">
                            <div class="mini-label">Attribute</div>
                            <div class="mini-value">${escapeHtml(data.attribute_name || "Not found")}</div>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <div class="section-title-row">
                        <h2>Template Registry Resolution</h2>
                        <span class="${matchBadgeClass}">
                            ${escapeHtml(data.template_resolution_match_type || "not_found")}
                        </span>
                    </div>

                    <div class="kv">
                        <div class="kv-key">Matched text</div>
                        <div class="kv-value">${escapeHtml(data.template_resolution_matched_text || "None")}</div>

                        <div class="kv-key">Score</div>
                        <div class="kv-value">${escapeHtml(data.template_resolution_score)}</div>

                        <div class="kv-key">Reason</div>
                        <div class="kv-value">${escapeHtml(data.template_resolution_reason || "None")}</div>

                        <div class="kv-key">New attribute name</div>
                        <div class="kv-value">${escapeHtml(data.new_attribute_name || "Not applicable")}</div>
                    </div>
                </div>

                <div class="card">
                    <div class="section-title-row">
                        <h2>Expression Compilation</h2>
                        <span class="${expressionBadgeClass}">
                            ${expressionBadgeText}
                        </span>
                    </div>

                    <div class="kv">
                        <div class="kv-key">Compiled value</div>
                        <div class="kv-value">${escapeHtml(compiledValue(data))}</div>

                        <div class="kv-key">Confidence</div>
                        <div class="kv-value">${escapeHtml(data.expression_compilation_confidence)}</div>

                        <div class="kv-key">Reason</div>
                        <div class="kv-value">${escapeHtml(data.expression_compilation_reason || "Not applicable")}</div>
                    </div>
                </div>

                ${renderMessages("Expression Warnings", data.expression_compilation_warnings, "warning")}

                ${renderMessages("Validation Errors", data.validation_errors, "error")}

                <div class="card">
                    <h2>Current Oracle Configuration</h2>
                    ${renderCurrentOracleConfig(data)}
                </div>

                <div class="card">
                    <div class="section-title-row">
                        <h2>Recommended SQL</h2>
                        <button class="secondary-button" onclick="copyText('generated-sql')">Copy SQL</button>
                    </div>

                    <pre id="generated-sql">${escapeHtml(formatSql(data.generated_sql))}</pre>
                </div>

                <div class="card">
                    <div class="section-title-row">
                        <h2>Rollback SQL</h2>
                        <button class="secondary-button" onclick="copyText('rollback-sql')">Copy Rollback</button>
                    </div>

                    <pre id="rollback-sql">${escapeHtml(formatSql(data.rollback_sql))}</pre>
                </div>

                ${renderMessages("Warnings", data.warnings, "warning")}

                <div class="card">
                    <h2>RAG Documentation Sources</h2>
                    <div class="source-list">
                        ${renderSources(data.rag_sources)}
                    </div>
                </div>
            `;
        }

        async function copyText(elementId) {
            const text = document.getElementById(elementId).innerText;
            await navigator.clipboard.writeText(text);
        }

        async function runAdvisor() {
            const requirement = document.getElementById("requirement").value.trim();
            const loading = document.getElementById("loading");

            if (!requirement) {
                alert("Please enter a requirement.");
                return;
            }

            loading.classList.add("active");

            try {
                const response = await fetch("/api/advisor", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({ requirement })
                });

                if (!response.ok) {
                    throw new Error(`Request failed with status ${response.status}`);
                }

                const data = await response.json();
                renderResults(data);
            } catch (error) {
                document.getElementById("results").innerHTML = `
                    <div class="card">
                        <h2>Application Error</h2>
                        <div class="message error">${escapeHtml(error.message)}</div>
                    </div>
                `;
            } finally {
                loading.classList.remove("active");
            }
        }
    </script>
</body>
</html>
"""