"""omkit.cost — provider cost telemetry.

Records a Prometheus counter ``cost_units_total`` with a fixed
low-cardinality label set so VictoriaMetrics scrape stays cheap:

- ``service``       — emitting service name.
- ``provider``      — backend identifier (``local``, ``voyage``, ``openai``, …).
- ``op``            — operation name (``embed``, ``parse_pages``,
                      ``rerank``, ``stt_seconds``, ``tts_chars``).
- ``tenant_bucket`` — coarse tenant grouping (``system`` / ``trial`` /
                      ``paid``); never the raw tenant_id (cardinality).

The ``units`` argument is the billable count for the operation
(``tokens``, ``pages``, ``audio_seconds``, …). Dollar projection lives
out of scope — a static price-table joins counter values in Grafana.
"""

from __future__ import annotations

from typing import Final, Literal

from prometheus_client import Counter

TenantBucket = Literal["system", "trial", "paid"]

_VALID_BUCKETS: Final[frozenset[str]] = frozenset({"system", "trial", "paid"})

COST_UNITS_TOTAL: Final[Counter] = Counter(
    "cost_units_total",
    "Billable units emitted by a provider call (tokens, pages, seconds, chars).",
    labelnames=("service", "provider", "op", "tenant_bucket"),
)


def record_cost(
    *,
    service: str,
    provider: str,
    op: str,
    units: float,
    tenant_bucket: TenantBucket | str,
) -> None:
    """Increment ``cost_units_total`` for one provider call.

    Args:
        service: Emitting service name.
        provider: Backend identifier (``local``, ``voyage``, ``openai``, …).
        op: Operation name (``embed``, ``parse_pages``, ``rerank``,
            ``stt_seconds``, ``tts_chars``).
        units: Billable count for the operation (tokens, pages,
            audio_seconds, character_count). Non-positive values are a
            no-op — counters cannot decrease and a non-positive input is
            always a caller bug.
        tenant_bucket: Coarse tenant grouping. Unknown values are
            normalised to ``trial`` so an instrumentation typo does not
            silently inflate the ``paid`` bucket.

    Returns:
        None — emission is best-effort. Failure to record never raises;
        the caller is on a hot path and a metric blip must not break it.
    """

    if units <= 0:
        return
    bucket = tenant_bucket if tenant_bucket in _VALID_BUCKETS else "trial"
    try:
        COST_UNITS_TOTAL.labels(
            service=service,
            provider=provider,
            op=op,
            tenant_bucket=bucket,
        ).inc(units)
    except Exception:
        # Counter emission is best-effort — never propagate.
        return


__all__ = ["COST_UNITS_TOTAL", "TenantBucket", "record_cost"]
