import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
import httpx

from app.main import app
from app.models import Envelope, MatchResult
from app.validator import validate_envelope
from app.matcher import match_commodity


client = TestClient(app)

@pytest.mark.asyncio
async def test_happy_path_auto_approve(make_envelope):
    envelope = make_envelope()
    
    result = await validate_envelope(envelope)
    
    assert result.decision["route"] == "auto_approve"
    assert result.validation_results is not None
    assert result.validation_results["status"] == "passed"
    assert result.validation_results["checks"]["schema"]["passed"] is True
    assert result.validation_results["checks"]["confidence"]["passed"] is True
    assert result.validation_results["checks"]["date_rules"]["passed"] is True
    assert len(result.audit) == 1
    assert result.audit[0]["service"] == "validation-service"
    assert result.matching_results is None


@pytest.mark.asyncio
async def test_low_confidence_triggers_hitl(make_envelope):
    envelope = make_envelope(recipient_name_confidence=0.45)
    
    result = await validate_envelope(envelope)
    
    assert result.decision["route"] == "hitl_review"
    assert result.validation_results["status"] == "failed"
    assert result.validation_results["checks"]["confidence"]["passed"] is False
    
    confidence_failures = result.validation_results["checks"]["confidence"]["failures"]
    recipient_failures = [f for f in confidence_failures if f["field"] == "recipient_name"]
    assert len(recipient_failures) > 0
    
    assert result.matching_results is None


@pytest.mark.asyncio
async def test_llm_matching_triggered(make_envelope):
    envelope = make_envelope(commodity_code_confidence=0.55)
    
    with patch("app.matcher.call_groq", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = '{"matched_code": "8471.30.0100", "match_confidence": 0.92, "rationale": "matched laptop"}'
        
        result = await validate_envelope(envelope)
        assert result.validation_results["status"] == "passed"
        
        result = await match_commodity(result)
    
    assert result.decision["route"] == "auto_approve"
    assert result.matching_results is not None
    assert result.matching_results["source"] == "llm_match"
    assert result.matching_results["matched_code"] == "8471.30.0100"
    assert result.matching_results["match_confidence"] >= 0.70
    
    assert len(result.audit) == 2
    assert result.audit[0]["service"] == "validation-service"
    assert result.audit[1]["service"] == "matching-service"


@pytest.mark.asyncio
async def test_invalid_envelope_returns_422():
    invalid_payload = {
        "envelope_id": "env_test_002",
        "schema_version": "envelope-v1",
        "tenant": {"id": "t1", "name": "Test Co"},
        "document": {"type": "shipping_manifest", "filename": "test.pdf", "page_count": 1},
        "extraction": {
            "ship_date": {"value": "2026-02-01", "confidence": 0.90},
            "recipient_name": {"value": "Acme Ltd", "confidence": 0.92},
            "commodity_code": {"value": "8471.30.0100", "confidence": 0.85},
            "commodity_desc": {"value": "portable laptop computer", "confidence": 0.91}
        },
        "processing_instructions": {
            "workflow": "manifest-v1",
            "confidence_threshold": 0.80,
            "hitl_on_failure": True
        },
        "validation_results": None,
        "matching_results": None,
        "decision": None,
        "audit": []
    }
    
    response = client.post("/process", json=invalid_payload)
    
    assert response.status_code == 422
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_llm_failure_graceful_degradation(make_envelope):
    envelope = make_envelope(commodity_code_confidence=0.55)
    
    result = await validate_envelope(envelope)
    assert result.validation_results["status"] == "passed"
    
    with patch("app.matcher.call_groq", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = httpx.TimeoutException("LLM timed out")
        result = await match_commodity(result)
    
    assert result.decision["route"] == "hitl_review"
    assert result.matching_results is not None
    assert result.matching_results["source"] == "no_match"
    assert result.matching_results["fallback_used"] is False
    assert result.matching_results["match_confidence"] == 0.0
    
    matching_audit = [a for a in result.audit if a["service"] == "matching-service"]
    assert len(matching_audit) > 0
    assert matching_audit[-1]["result"] == "failed"
    assert "failed" in matching_audit[-1]["details"]["error"].lower() or \
           "timed out" in matching_audit[-1]["details"]["error"].lower()


@pytest.mark.asyncio
async def test_full_pipeline_via_http(make_envelope):
    envelope = make_envelope()
    
    with patch("app.matcher.call_groq", new_callable=AsyncMock):
        response = client.post("/process", json=envelope.model_dump())
    
    assert response.status_code == 200
    data = response.json()
    assert "envelope_id" in data
    assert "decision" in data
    assert "audit" in data
    assert len(data["audit"]) >= 1
