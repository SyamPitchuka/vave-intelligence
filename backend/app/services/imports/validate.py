"""Row validation for Excel and CSV imports. Rules are explicit and do not infer missing fields."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.constants import IDEA_DEPARTMENTS, REJECTED_DEPARTMENTS
from app.services.imports.mapping import VOLUME_FIELDS
from app.services.rejection import StageStatusError, clean_optional, is_rejected, normalize_stage
from app.services.savings import combined_annual_saving, money

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y", "%d-%b-%Y", "%m/%d/%Y")
_KNOWN_BELONGED = {name.casefold() for name in IDEA_DEPARTMENTS}
_KNOWN_REJECTED = {name.casefold() for name in REJECTED_DEPARTMENTS}


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and value != value:
        return True
    text = str(value).strip()
    return text == "" or text.lower() in {"nan", "none", "null", "nat"}


def parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        serial = float(value)
        if 20000 <= serial <= 80000:
            return (datetime(1899, 12, 30) + timedelta(days=int(serial))).date()
    text = str(value).strip()
    if " " in text and ":" in text:
        text = text.split(" ")[0]
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(
        f"Could not parse date '{value}'. Use YYYY-MM-DD or DD/MM/YYYY. "
        "Slash dates are read day-first unless they are ISO dates."
    )


def parse_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise InvalidOperation
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace(",", "").replace("₹", "").replace("INR", "").strip()
    return Decimal(text)


def validate_mapped_row(
    mapped: dict[str, Any],
    *,
    row_number: int,
    seen_codes: set[str],
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []

    def add(severity: str, message: str, column: str | None = None, raw: Any = None) -> None:
        issues.append(
            {
                "row_number": row_number,
                "severity": severity,
                "message": message,
                "column_name": column,
                "raw_value": None if raw is None or is_blank(raw) else str(raw)[:500],
            }
        )

    code_raw = mapped.get("idea_code")
    if is_blank(code_raw):
        add("error", "Idea ID is required.", "idea_code", code_raw)
        code = ""
    else:
        code = str(code_raw).strip()
        folded = code.casefold()
        if folded in seen_codes:
            add("error", f"Idea ID '{code}' is repeated in this file.", "idea_code", code)
        seen_codes.add(folded)

    description = None if is_blank(mapped.get("description")) else str(mapped.get("description")).strip()
    if description is None:
        add("error", "Idea description is required.", "description", mapped.get("description"))

    department = clean_optional(None if is_blank(mapped.get("idea_belonged_department")) else str(mapped.get("idea_belonged_department")))
    if department is None:
        add("error", "Idea belonged department is required and is not inferred.", "idea_belonged_department")
    elif department.casefold() not in _KNOWN_BELONGED:
        add(
            "warning",
            f"Department '{department}' is not in the initial catalogue. The source value will be kept.",
            "idea_belonged_department",
            department,
        )

    rejected_department = clean_optional(
        None if is_blank(mapped.get("rejected_department")) else str(mapped.get("rejected_department"))
    )
    if rejected_department and rejected_department.casefold() not in _KNOWN_REJECTED:
        add(
            "warning",
            f"Rejected department '{rejected_department}' is not in the catalogue. The source value will be kept.",
            "rejected_department",
            rejected_department,
        )

    stage = None
    if not is_blank(mapped.get("stage_status")):
        try:
            stage = normalize_stage(str(mapped.get("stage_status")))
        except StageStatusError as exc:
            add("error", str(exc), "stage_status", mapped.get("stage_status"))

    generation_date = None
    if not is_blank(mapped.get("idea_generation_date")):
        try:
            generation_date = parse_date(mapped.get("idea_generation_date"))
        except ValueError as exc:
            add("error", str(exc), "idea_generation_date", mapped.get("idea_generation_date"))

    rejection_date = None
    if not is_blank(mapped.get("rejection_date")):
        try:
            rejection_date = parse_date(mapped.get("rejection_date"))
        except ValueError as exc:
            add("error", str(exc), "rejection_date", mapped.get("rejection_date"))
    if generation_date and rejection_date and rejection_date < generation_date:
        add(
            "warning",
            "Rejection date is earlier than the idea generation date. Both dates will be stored as supplied.",
            "rejection_date",
            mapped.get("rejection_date"),
        )

    category = clean_optional(None if is_blank(mapped.get("rejection_category")) else str(mapped.get("rejection_category")))
    reason = clean_optional(None if is_blank(mapped.get("rejection_reason")) else str(mapped.get("rejection_reason")))
    rejected = is_rejected(category)
    if reason and not rejected:
        add(
            "warning",
            "Rejection reason is populated but rejection category is blank. "
            "The idea will be stored as active / not rejected. "
            "Duplicate in the reason column is not treated as a stage status.",
            "rejection_reason",
            reason,
        )
    if rejected_department and not rejected:
        add(
            "warning",
            "Rejected department is populated but rejection category is blank. "
            "Rejection was not inferred from the department.",
            "rejected_department",
            rejected_department,
        )
    if rejected and not reason:
        add("warning", "Rejection category is set but rejection reason is blank.", "rejection_reason")

    saving = None
    if not is_blank(mapped.get("saving_per_vehicle")):
        try:
            saving = money(parse_decimal(mapped.get("saving_per_vehicle")))
        except (InvalidOperation, ValueError):
            add("error", "Saving per vehicle must be a number.", "saving_per_vehicle", mapped.get("saving_per_vehicle"))
        else:
            if saving < 0:
                add("error", "Saving per vehicle cannot be negative.", "saving_per_vehicle", saving)

    reported = None
    if not is_blank(mapped.get("reported_total_saving")):
        try:
            reported = money(parse_decimal(mapped.get("reported_total_saving")))
        except (InvalidOperation, ValueError):
            add(
                "error",
                "Total combined annual saving must be a number when it is present.",
                "reported_total_saving",
                mapped.get("reported_total_saving"),
            )

    volumes: list[tuple[str, str]] = []
    for field, family in VOLUME_FIELDS.items():
        raw_volume = mapped.get(field)
        if is_blank(raw_volume):
            continue
        try:
            volume = money(parse_decimal(raw_volume))
        except (InvalidOperation, ValueError):
            add("error", f"Annual volume for {family} must be a number.", field, raw_volume)
            continue
        if volume < 0:
            add("error", f"Annual volume for {family} cannot be negative.", field, raw_volume)
            continue
        volumes.append((family, str(volume)))

    computed, saving_warnings = combined_annual_saving(
        saving, [(family, Decimal(amount)) for family, amount in volumes]
    )
    for message in saving_warnings:
        if "missing" in message and saving is None and not any(item["column_name"] == "saving_per_vehicle" and item["severity"] == "error" for item in issues):
            add("warning", message, "saving_per_vehicle")
    mismatch = False
    if computed is not None and reported is not None and abs(computed - reported) > Decimal("0.50"):
        mismatch = True
        add(
            "warning",
            f"Workbook total {reported} does not match the calculated total {computed}. "
            "The calculated total will be stored. The workbook figure is kept as the reported value.",
            "reported_total_saving",
            reported,
        )

    if any(issue["severity"] == "error" for issue in issues):
        return None, issues

    payload = {
        "idea_code": code,
        "component": clean_optional(None if is_blank(mapped.get("component")) else str(mapped.get("component"))),
        "description": description,
        "current_design": _text(mapped.get("current_design")),
        "proposed_change": _text(mapped.get("proposed_change")),
        "engineering_rationale": _text(mapped.get("engineering_rationale")),
        "expected_benefit": _text(mapped.get("expected_benefit")),
        "constraints": _text(mapped.get("constraints")),
        "idea_generation_date": generation_date.isoformat() if generation_date else None,
        "rejection_date": rejection_date.isoformat() if rejection_date else None,
        "idea_belonged_department": department,
        "rejected_department": rejected_department,
        "stage_status": stage,
        "rejection_category": category,
        "rejection_reason": reason,
        "idea_type": _text(mapped.get("idea_type")),
        "idea_disposition": _text(mapped.get("idea_disposition")),
        "applicable_vehicle_details": _text(mapped.get("applicable_vehicle_details")),
        "saving_per_vehicle": str(saving) if saving is not None else None,
        "reported_total_saving": str(reported) if reported is not None else None,
        "computed_total": str(computed) if computed is not None else None,
        "savings_mismatch": mismatch,
        "is_rejected": rejected,
        "volumes": volumes,
    }
    return payload, issues


def _text(value: Any) -> str | None:
    if is_blank(value):
        return None
    return str(value).strip()
