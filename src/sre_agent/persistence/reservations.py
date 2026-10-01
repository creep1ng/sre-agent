"""PostgreSQL adapter for metadata-only consumption reservations."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from sre_agent.persistence.models import ConsumptionReservationRow

MAX_BIGINT = 9_223_372_036_854_775_807


def _utc_month(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("period_start must be timezone-aware")
    value = value.astimezone(UTC)
    if value.day != 1 or value.time().isoformat() != "00:00:00":
        raise ValueError("period_start must be the first instant of a UTC month")
    return value


def _bounded_usd(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValueError("USD exposure must be a finite nonnegative Decimal or unknown")
    scale = max(0, -value.as_tuple().exponent)
    integer_digits = max(0, value.adjusted() + 1) if value else 0
    if scale > 36 or integer_digits > 20:
        raise ValueError("USD exposure exceeds the exact Numeric(56,36) bounds")
    return value


class ConsumptionReservationRepository:
    """Persist exposure before provider work; settlement remains a later transition."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        reservation_id: str,
        *,
        incident_id: str | None,
        period_start: datetime,
        policy_version: int,
        model: str,
        provider: str,
        token_exposure: int | None,
        usd_exposure: Decimal | None,
        created_at: datetime,
    ) -> ConsumptionReservationRow:
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        row = ConsumptionReservationRow(
            reservation_id=reservation_id,
            incident_id=incident_id,
            period_start=_utc_month(period_start),
            policy_version=policy_version,
            model=model,
            provider=provider,
            token_exposure=token_exposure,
            usd_exposure=_bounded_usd(usd_exposure),
            settled_tokens=None,
            settled_usd_cost=None,
            state="reserved",
            created_at=created_at.astimezone(UTC),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, reservation_id: str) -> ConsumptionReservationRow | None:
        return await self._session.get(ConsumptionReservationRow, reservation_id)
