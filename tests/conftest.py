import pytest
from app.models import Envelope, Extraction, Extractedfield, ProcessingInstructions


@pytest.fixture
def base_envelope():
    return {
        "envelope_id": "env_test_001",
        "schema_version": "envelope-v1",
        "tenant": {"id": "t1", "name": "Test Co"},
        "document": {"type": "shipping_manifest", "filename": "test.pdf", "page_count": 1},
        "extraction": {
            "shipment_id": {"value": "SHP-001", "confidence": 0.95},
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


@pytest.fixture
def make_envelope(base_envelope):
    def _make_envelope(**overrides):
        data = {
            "envelope_id": base_envelope["envelope_id"],
            "schema_version": base_envelope["schema_version"],
            "tenant": base_envelope["tenant"],
            "document": base_envelope["document"],
            "extraction": {
                "shipment_id": base_envelope["extraction"]["shipment_id"].copy(),
                "ship_date": base_envelope["extraction"]["ship_date"].copy(),
                "recipient_name": base_envelope["extraction"]["recipient_name"].copy(),
                "commodity_code": base_envelope["extraction"]["commodity_code"].copy(),
                "commodity_desc": base_envelope["extraction"]["commodity_desc"].copy(),
            },
            "processing_instructions": base_envelope["processing_instructions"].copy(),
            "validation_results": base_envelope["validation_results"],
            "matching_results": base_envelope["matching_results"],
            "decision": base_envelope["decision"],
            "audit": base_envelope["audit"].copy()
        }
        
        if "shipment_id_confidence" in overrides:
            data["extraction"]["shipment_id"]["confidence"] = overrides["shipment_id_confidence"]
        if "ship_date_confidence" in overrides:
            data["extraction"]["ship_date"]["confidence"] = overrides["ship_date_confidence"]
        if "recipient_name_confidence" in overrides:
            data["extraction"]["recipient_name"]["confidence"] = overrides["recipient_name_confidence"]
        if "commodity_code_confidence" in overrides:
            data["extraction"]["commodity_code"]["confidence"] = overrides["commodity_code_confidence"]
        if "commodity_desc_confidence" in overrides:
            data["extraction"]["commodity_desc"]["confidence"] = overrides["commodity_desc_confidence"]
        if "commodity_code_value" in overrides:
            data["extraction"]["commodity_code"]["value"] = overrides["commodity_code_value"]
        if "commodity_desc_value" in overrides:
            data["extraction"]["commodity_desc"]["value"] = overrides["commodity_desc_value"]
        if "threshold" in overrides:
            data["processing_instructions"]["confidence_threshold"] = overrides["threshold"]
        if "envelope_id" in overrides:
            data["envelope_id"] = overrides["envelope_id"]
        
        if overrides.get("remove_commodity_code", False):
            data["extraction"].pop("commodity_code", None)
        if overrides.get("remove_shipment_id", False):
            data["extraction"].pop("shipment_id", None)
        
        return Envelope(**data)
    
    return _make_envelope
