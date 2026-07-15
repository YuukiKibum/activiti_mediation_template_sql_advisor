from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

from activiti_mediation_template_sql_advisor.graph.state import AdvisorState


NodeFn = Callable[[AdvisorState], Any]


def _merge_timing(
    state: AdvisorState,
    *,
    node_name: str,
    elapsed_ms: float,
    status: str,
    error_type: str = "",
) -> dict[str, Any]:
    debug = dict(state.get("debug") or {})
    timings = list(debug.get("timings") or [])
    failures = list(debug.get("failures") or [])

    timings.append(
        {
            "node": node_name,
            "elapsed_ms": round(elapsed_ms, 2),
            "status": status,
        }
    )

    if status == "error" and error_type:
        failures.append({"node": node_name, "error_type": error_type})

    debug["timings"] = timings
    if failures:
        debug["failures"] = failures

    return debug


def timed_node(node_name: str, node_fn: NodeFn) -> NodeFn:
    """Wrap a graph node to record per-node timing and failure telemetry."""

    if asyncio.iscoroutinefunction(node_fn):

        async def async_wrapped(state: AdvisorState) -> dict[str, Any]:
            started = time.perf_counter()
            try:
                result = await node_fn(state)
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - started) * 1000
                debug = _merge_timing(
                    state,
                    node_name=node_name,
                    elapsed_ms=elapsed_ms,
                    status="error",
                    error_type=type(exc).__name__,
                )
                raise

            elapsed_ms = (time.perf_counter() - started) * 1000
            updates = dict(result or {})
            debug = _merge_timing(
                state,
                node_name=node_name,
                elapsed_ms=elapsed_ms,
                status="ok",
            )
            existing_debug = dict(updates.get("debug") or {})
            existing_debug.update(debug)
            updates["debug"] = existing_debug
            return updates

        return async_wrapped

    def sync_wrapped(state: AdvisorState) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            result = node_fn(state)
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            _merge_timing(
                state,
                node_name=node_name,
                elapsed_ms=elapsed_ms,
                status="error",
                error_type=type(exc).__name__,
            )
            raise

        elapsed_ms = (time.perf_counter() - started) * 1000
        updates = dict(result or {})
        debug = _merge_timing(
            state,
            node_name=node_name,
            elapsed_ms=elapsed_ms,
            status="ok",
        )
        existing_debug = dict(updates.get("debug") or {})
        existing_debug.update(debug)
        updates["debug"] = existing_debug
        return updates

    return sync_wrapped
