from fastapi import FastAPI, HTTPException
from app.models import Envelope
from app.validator import validate_envelope
from app.matcher import match_commodity

app = FastAPI()


@app.post("/validate")
async def validate(envelope: Envelope):
    try:
        return await validate_envelope(envelope)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/match")
async def match(envelope: Envelope):
    return await match_commodity(envelope)


@app.post("/process")
async def process(envelope: Envelope):
    envelope = await validate_envelope(envelope)
    commodity_code = envelope.extraction.commodity_code
    threshold = envelope.processing_instructions.confidence_threshold
    if not commodity_code or commodity_code.confidence < threshold:
        envelope = await match_commodity(envelope)
    return envelope