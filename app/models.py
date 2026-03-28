from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

class Extractedfield(BaseModel):
    value:str
    confidence:float

class Extraction(BaseModel):
    shipment_id:Extractedfield
    ship_date:Extractedfield
    recipient_name:Extractedfield
    commodity_code:Optional[Extractedfield] = None
    commodity_desc:Optional[Extractedfield] = None

class ProcessingInstructions(BaseModel):
    workflow:str
    confidence_threshold:float
    hitl_on_failure:bool

class Envelope(BaseModel):
    envelope_id: str
    schema_version: str
    tenant: dict
    document: dict
    extraction: Extraction
    processing_instructions: ProcessingInstructions
    validation_results: Optional[dict] = None
    matching_results: Optional[dict] = None
    decision: Optional[dict] = None
    audit: list = []

class MatchResult(BaseModel):
    matched_code: Optional[str] = None
    match_confidence: float
    rationale: str
    fallback_used: bool
    source: Literal["catalog_exact", "llm_match", "no_match"]