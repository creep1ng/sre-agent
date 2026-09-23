"""Evidence provider backed by recordings, labeled `source: fixture` (ADR-007).

The recordings come from the `paymentUnreachable` failure measured in the #186 demo
environment. They stand in for governed MCP reads until #187 exposes them, and are never
presented as the result of a real query.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import JsonValue

from sre_agent.investigator.ports import EvidenceUnavailable, ToolResult

RECORDED = {
    "query_prometheus": ToolResult(
        source="fixture",
        datasource_uid="webstore-metrics",
        query=(
            "sum by (service_name) (increase(traces_span_metrics_calls_total"
            '{status_code="STATUS_CODE_ERROR", '
            'service_name=~"frontend-proxy|frontend|checkout|payment"}[2m]))'
        ),
        time_window="2m",
        summary=(
            "Recorded with paymentUnreachable on: error calls in two minutes were checkout 12, "
            "frontend 24, frontend-proxy 12 and payment 0. Inside checkout they split evenly "
            "between oteldemo.CheckoutService/PlaceOrder and oteldemo.PaymentService/Charge."
        ),
    ),
    "query_elasticsearch": ToolResult(
        source="fixture",
        datasource_uid="webstore-logs",
        query="resource.service.name:checkout",
        time_window="2m",
        summary=(
            "Recorded with paymentUnreachable on: checkout logged 4 orders at [PlaceOrder] and "
            "none reached 'payment went through' or 'order placed'. Checkout writes no error "
            "log for the failed charge."
        ),
    ),
}


class FixtureEvidenceProvider:
    """Serves one recording per tool and ignores the arguments."""

    def __init__(self, recordings: Mapping[str, ToolResult] = RECORDED) -> None:
        self._recordings = dict(recordings)

    async def collect(self, tool: str, arguments: Mapping[str, JsonValue]) -> ToolResult:
        try:
            return self._recordings[tool]
        except KeyError:
            raise EvidenceUnavailable(f"no recording for {tool}") from None
