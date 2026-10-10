"""Authoritative savings calculation.

Total combined annual saving (INR) =
    saving per vehicle (INR) × sum of annual volumes across unique vehicle families.

A repeated vehicle family is counted once, using the first volume. The spreadsheet
figure is never the source of truth.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

MONEY = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def combined_annual_saving(
    saving_per_vehicle: Decimal | None,
    volumes: list[tuple[str, Decimal]],
) -> tuple[Decimal | None, list[str]]:
    """Return (total, warnings).

    `volumes` is an ordered list of (family key, annual volume). The same family
    key is not added twice. A missing saving does not become zero.
    """
    warnings: list[str] = []
    seen: dict[str, Decimal] = {}
    for key, volume in volumes:
        if key in seen:
            warnings.append(
                f"Vehicle family '{key}' was repeated. Its volume was counted once "
                "so the annual total is not double-counted."
            )
            continue
        seen[key] = volume

    if saving_per_vehicle is None:
        warnings.append("Saving per vehicle is missing, so no annual total was calculated.")
        return None, warnings

    total_volume = sum(seen.values(), start=Decimal("0"))
    return money(saving_per_vehicle * total_volume), warnings
