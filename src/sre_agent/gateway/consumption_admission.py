"""Atomic pre-provider admission with durable metadata-only reservations."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text

from sre_agent.gateway.consumption_affordability import (
    AffordabilityDenied,
    calculate_affordability,
)
from sre_agent.gateway.endpoint_catalog import EndpointCatalogUnavailable
from sre_agent.persistence.models import ConsumptionReservationRow
from sre_agent.persistence.reservations import ConsumptionReservationRepository


@dataclass(frozen=True, slots=True)
class AdmissionResult:
    allowed: bool
    max_output_tokens: int | None
    policy_version: int
    reservation_id: str | None
    denial_reason: str | None
    retryable: bool


def _month_bounds(now: datetime) -> tuple[datetime, datetime]:
    period = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if period.month == 12:
        return period, period.replace(year=period.year + 1, month=1)
    return period, period.replace(month=period.month + 1)


class ConsumptionAdmissionService:
    """Reserve capacity atomically before provider contact; settle exact usage later."""

    def __init__(self, sessions: object) -> None:
        self._sessions = sessions  # type: ignore[assignment]

    async def admit(
        self,
        *,
        incident_id: str | None,
        model: str,
        provider: str,
        catalog: object,
        now: datetime,
        request_id: UUID | None = None,
    ) -> AdmissionResult:
        if now.tzinfo is None or now.utcoffset() is None:
            return AdmissionResult(False, None, 0, None, "consumption_bounds_unavailable", False)
        now = now.astimezone(UTC)
        period, following = _month_bounds(now)
        async with self._sessions() as session:  # type: ignore[operator]
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext('consumption-month:' || :p))"),
                {"p": period.isoformat()},
            )
            if incident_id is not None:
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext('consumption-incident:' || :i))"),
                    {"i": incident_id},
                )
            policy = (
                await session.execute(
                    text(
                        "SELECT version, incident_token_limit, monthly_usd_limit "
                        "FROM consumption_limit_policies WHERE policy_id = 1"
                    )
                )
            ).one_or_none()
            if policy is None:
                return AdmissionResult(False, None, 0, None, "policy_unavailable", True)
            version, incident_limit, monthly_limit = policy
            if incident_limit is None and monthly_limit is None:
                return AdmissionResult(True, None, int(version), None, None, False)
            try:
                # An active limit needs endpoint bounds, so an unconfigured or
                # unusable catalog must fail closed here instead of letting the
                # caller reach the provider with no reservation.
                fetch = catalog.fetch  # type: ignore[attr-defined]
                snapshot = await fetch(model)
                # The catalog is fetched after the admission clock is read, so a
                # live snapshot is observed slightly later than `now`. Judge
                # freshness at the later of the two; an expired `valid_until`
                # still fails closed inside select().
                observed_at = snapshot.observed_at
                if not isinstance(observed_at, datetime):
                    raise TypeError("snapshot observation must be a datetime")
                check_at = observed_at if observed_at > now else now
                endpoint = snapshot.select(provider, now=check_at)
            except (EndpointCatalogUnavailable, AttributeError, TypeError, ValueError):
                return AdmissionResult(
                    False,
                    None,
                    int(version),
                    None,
                    "consumption_bounds_unavailable",
                    False,
                )
            incident_remaining = await self._incident_remaining(
                session, incident_id, incident_limit, period
            )
            monthly_remaining = await self._monthly_remaining(
                session, monthly_limit, period, following
            )
            if monthly_limit is not None and (
                endpoint.prompt_price is None
                or endpoint.completion_price is None
                or endpoint.request_price is None
            ):
                return AdmissionResult(
                    False,
                    None,
                    int(version),
                    None,
                    "consumption_bounds_unavailable",
                    False,
                )
            try:
                envelope = calculate_affordability(
                    snapshot,
                    provider=provider,
                    incident_tokens_remaining=incident_remaining,
                    monthly_usd_remaining=monthly_remaining,
                    now=check_at,
                )
            except AffordabilityDenied:
                return AdmissionResult(
                    False,
                    None,
                    int(version),
                    None,
                    self._deny_reason(incident_remaining, monthly_remaining),
                    False,
                )
            token_exposure = envelope.conservative_input_tokens + envelope.max_output_tokens
            usd_exposure = (
                (envelope.conservative_input_cost_usd or Decimal(0))
                + (envelope.request_fee_usd or Decimal(0))
                + Decimal(envelope.max_output_tokens) * (endpoint.completion_price or Decimal(0))
            )
            # Share the server-generated request identity with audit, without
            # adding a second correlation field or changing historical rows.
            reservation_id = str(request_id) if request_id is not None else uuid4().hex
            await ConsumptionReservationRepository(session).create(
                reservation_id,
                incident_id=incident_id,
                period_start=period,
                policy_version=int(version),
                model=model,
                provider=provider,
                token_exposure=token_exposure if incident_limit is not None else None,
                usd_exposure=usd_exposure if monthly_limit is not None else None,
                created_at=now,
            )
            await session.commit()
            return AdmissionResult(
                True,
                envelope.max_output_tokens,
                int(version),
                reservation_id,
                None,
                False,
            )

    async def settle(
        self, *, reservation_id: str, tokens: int, usd_cost: Decimal | None
    ) -> ConsumptionReservationRow:
        async with self._sessions() as session:  # type: ignore[operator]
            row = await session.get(ConsumptionReservationRow, reservation_id)
            if row is None:
                raise ValueError("unknown reservation")
            if row.state == "settled":
                return row
            if tokens < 0:
                raise ValueError("settled tokens must be nonnegative")
            row.settled_tokens = tokens
            row.settled_usd_cost = usd_cost
            row.state = "settled"
            await session.flush()
            await session.commit()
            return row

    def _deny_reason(
        self, incident_remaining: int | None, monthly_remaining: Decimal | None
    ) -> str:
        if incident_remaining is not None and monthly_remaining is None:
            return "incident_limit_exceeded"
        if monthly_remaining is not None and incident_remaining is None:
            return "monthly_limit_exceeded"
        if monthly_remaining is not None and monthly_remaining <= 0:
            return "monthly_limit_exceeded"
        if incident_remaining is not None:
            return "incident_limit_exceeded"
        return "monthly_limit_exceeded"

    async def _incident_remaining(
        self,
        session: object,
        incident_id: str | None,
        limit: int | None,
        period: datetime,
    ) -> int | None:
        if limit is None or incident_id is None:
            return None
        settled = await self._incident_sum(session, "settled_tokens", incident_id, period, True)
        outstanding = await self._incident_sum(
            session, "token_exposure", incident_id, period, False
        )
        return int(limit) - int(settled) - int(outstanding)

    async def _monthly_remaining(
        self, session: object, limit: object, period: datetime, following: datetime
    ) -> Decimal | None:
        if limit is None:
            return None
        _, legacy_usd = await self._legacy_usage(session, period, following)
        # The monthly allowance belongs to the workspace, not to one incident.
        # Exposure booked against any incident is already spent from this month,
        # so summing only the incident-less rows would let a second incident
        # admit against money the first one had already reserved.
        settled = await self._period_sum(session, "settled_usd_cost", period, True)
        outstanding = await self._period_sum(session, "usd_exposure", period, False)
        return Decimal(str(limit)) - legacy_usd - _decimal(settled) - _decimal(outstanding)

    async def _incident_sum(
        self, session: object, column: str, incident_id: str, period: datetime, settled: bool
    ) -> object:
        return await self._sum(
            session,
            f"SELECT COALESCE(SUM({column}), 0) FROM consumption_reservations "
            "WHERE incident_id = :incident AND period_start = :period AND state = :state",
            {
                "incident": incident_id,
                "period": period,
                "state": _reservation_state(settled),
            },
        )

    async def _period_sum(
        self, session: object, column: str, period: datetime, settled: bool
    ) -> object:
        return await self._sum(
            session,
            f"SELECT COALESCE(SUM({column}), 0) FROM consumption_reservations "
            "WHERE period_start = :period AND state = :state",
            {"period": period, "state": _reservation_state(settled)},
        )

    async def _sum(self, session: object, statement: str, parameters: dict) -> object:
        rows = await session.execute(text(statement), parameters)  # type: ignore[union-attr]
        return rows.scalar()

    async def _legacy_usage(
        self, session: object, period: datetime, following: datetime
    ) -> tuple[int, Decimal]:
        # Monetary reservations own their usage, including uncertain settlement.
        # Audit remains the fallback when no reservation accounts for the USD.
        # Do not constrain the match by month: a response may cross its boundary.
        result = await session.execute(  # type: ignore[union-attr]
            text(
                "SELECT COALESCE(SUM((c->>'total_tokens')::bigint), 0), "
                "COALESCE(SUM((c->>'billed_usd')::numeric), 0) FROM ("
                "SELECT DISTINCT ON (correlation->>'request_id') consumption AS c "
                "FROM audit_events WHERE operation = 'responses.create' "
                "AND stage = 'response' AND outcome = 'success' "
                "AND occurred_at >= :start AND occurred_at < :end "
                "AND (consumption->>'availability') = 'complete' "
                "AND NOT EXISTS (SELECT 1 FROM consumption_reservations r "
                "WHERE r.reservation_id = audit_events.correlation->>'request_id' "
                "AND ((r.state = 'reserved' AND r.usd_exposure IS NOT NULL) "
                "OR (r.state = 'settled' AND r.settled_usd_cost IS NOT NULL))) "
                "ORDER BY correlation->>'request_id', occurred_at DESC) t"
            ),
            {"start": period, "end": following},
        )
        tokens, usd = result.all()[0]
        return int(tokens), Decimal(str(usd))


def _reservation_state(settled: bool) -> str:
    return "settled" if settled else "reserved"


def _decimal(value: object) -> Decimal:
    return Decimal(str(value or 0))
