from datetime import date, datetime, timedelta, timezone
from typing import Any
import logging

logger = logging.getLogger(__name__)


def _get_extraction_fields(extraction: Any) -> dict:
    fields = {}
    for field_name in ["shipment_id", "ship_date", "recipient_name", "commodity_code", "commodity_desc"]:
        value = getattr(extraction, field_name, None)
        if value is not None:
            fields[field_name] = value
    return fields


def _check_schema(extraction: Any, envelope_id: str) -> list[dict]:
    failed = []

    if not extraction.shipment_id or not extraction.shipment_id.value:
        logger.warning(f"[{envelope_id}] Schema validation failed: shipment_id is missing or null")
        failed.append({
            "field": "shipment_id",
            "reason": "Field is required but missing or null",
        })

    if not extraction.recipient_name or not extraction.recipient_name.value:
        logger.warning(f"[{envelope_id}] Schema validation failed: recipient_name is missing or null")
        failed.append({
            "field": "recipient_name",
            "reason": "Field is required but missing or null",
        })

    has_commodity = (
        (extraction.commodity_code and extraction.commodity_code.value) or
        (extraction.commodity_desc and extraction.commodity_desc.value)
    )
    if not has_commodity:
        logger.warning(f"[{envelope_id}] Schema validation failed: commodity_code and commodity_desc both missing")
        failed.append({
            "field": "commodity_code / commodity_desc",
            "reason": "At least one of commodity_code or commodity_desc is required",
        })

    return failed


def _check_confidence(extraction: Any, threshold: float, envelope_id: str) -> list[dict]:
    failed = []
    required_fields = ["shipment_id", "recipient_name"]
    
    for field_name in required_fields:
        field = getattr(extraction, field_name, None)
        if field and field.confidence < threshold:
            logger.warning(
                f"[{envelope_id}] Confidence check failed for {field_name}: "
                f"{field.confidence:.2f} < {threshold:.2f}"
            )
            failed.append({
                "field": field_name,
                "reason": (
                    f"Confidence {field.confidence:.2f} is below threshold {threshold:.2f}"
                ),
            })

    return failed


def _check_ship_date(extraction: Any, envelope_id: str) -> list[dict]:
    failed = []

    if not extraction.ship_date or not extraction.ship_date.value:
        return failed

    try:
        ship_date = date.fromisoformat(extraction.ship_date.value)
    except ValueError:
        logger.warning(f"[{envelope_id}] Invalid ship_date format: '{extraction.ship_date.value}'")
        failed.append({
            "field": "ship_date",
            "reason": f"Invalid date format '{extraction.ship_date.value}'. Expected YYYY-MM-DD",
        })
        return failed

    today = date.today()

    if ship_date > today:
        logger.warning(f"[{envelope_id}] ship_date is in the future: {ship_date}")
        failed.append({
            "field": "ship_date",
            "reason": f"Date {ship_date} is in the future (today is {today})",
        })

    if ship_date < today - timedelta(days=365):
        logger.warning(f"[{envelope_id}] ship_date is older than 365 days: {ship_date}")
        failed.append({
            "field": "ship_date",
            "reason": f"Date {ship_date} is older than 365 days from today ({today})",
        })

    return failed


def _decide_route(failed_fields: list[dict], hitl_on_failure: bool) -> str:
    if not failed_fields:
        return "auto_approve"
    return "hitl_review" if hitl_on_failure else "rejected"


def _build_audit_entry(
    envelope_id: str,
    route: str,
    failed_fields: list[dict],
) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "validation-service",
        "action": "validate",
        "envelope_id": envelope_id,
        "result": route,
        "details": {
            "failed_fields": failed_fields,
            "total_failures": len(failed_fields),
        },
    }


async def validate_envelope(envelope: Any) -> Any:
    envelope_id = envelope.envelope_id
    logger.info(f"[{envelope_id}] Starting validation")
    
    extraction = envelope.extraction
    instructions = envelope.processing_instructions
    threshold = instructions.confidence_threshold
    hitl_on_failure = instructions.hitl_on_failure

    schema_failures = _check_schema(extraction, envelope_id)
    confidence_failures = _check_confidence(extraction, threshold, envelope_id)
    date_failures = _check_ship_date(extraction, envelope_id)

    all_failures = schema_failures + confidence_failures + date_failures

    route = _decide_route(all_failures, hitl_on_failure)
    logger.info(f"[{envelope_id}] Route decided: {route} (total_failures={len(all_failures)})")

    validation_results = {
        "status": "passed" if not all_failures else "failed",
        "threshold_used": threshold,
        "checks": {
            "schema": {
                "passed": len(schema_failures) == 0,
                "failures": schema_failures,
            },
            "confidence": {
                "passed": len(confidence_failures) == 0,
                "failures": confidence_failures,
            },
            "date_rules": {
                "passed": len(date_failures) == 0,
                "failures": date_failures,
            },
        },
        "total_failures": len(all_failures),
    }

    audit_entry = _build_audit_entry(envelope_id, route, all_failures)

    envelope.validation_results = validation_results
    envelope.decision = {"route": route}
    envelope.audit = list(envelope.audit) + [audit_entry]

    return envelope