import os
import json
import logging
import asyncio
from datetime import datetime, timezone
from dotenv import load_dotenv
from groq import Groq

from app.models import Envelope, MatchResult
from app.catalog import COMMODITY_CATALOG

load_dotenv()

logger = logging.getLogger(__name__)

api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    logger.warning("GROQ_API_KEY not found in environment. LLM matching will fail.")
else:
    logger.info("Groq API configured successfully")


def _strip_markdown(text: str) -> str:
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


async def call_groq(prompt: str) -> str:
    def _groq_sync():
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.3,
            timeout=30.0
        )
        return response.choices[0].message.content
    
    return await asyncio.to_thread(_groq_sync)


async def match_commodity(envelope: Envelope) -> Envelope:
    envelope_id = envelope.envelope_id
    
    try:
        threshold = envelope.processing_instructions.confidence_threshold
        commodity_code = envelope.extraction.commodity_code
        
        if commodity_code and commodity_code.confidence >= threshold:
            logger.info(
                f"[{envelope_id}] Skipping LLM match: commodity_code confidence {commodity_code.confidence:.2f} >= threshold {threshold:.2f}"
            )
            return envelope
        
        if not envelope.extraction.commodity_desc or not envelope.extraction.commodity_desc.value:
            logger.info(
                f"[{envelope_id}] Skipping LLM match: commodity_desc is missing or empty"
            )
            return envelope
        
        commodity_desc = envelope.extraction.commodity_desc.value
        logger.info(f"[{envelope_id}] Triggering LLM matching for: '{commodity_desc}'")
        
        catalog_json = json.dumps(COMMODITY_CATALOG, indent=2)
        
        prompt = f"""You are a commodity classification expert. Given a commodity description, 
match it to the most appropriate HS code from the provided catalog.

COMMODITY DESCRIPTION:
{commodity_desc}

COMMODITY CATALOG:
{catalog_json}

Analyze the description and find the best matching HS code from the catalog. Consider:
1. Product type and functionality
2. Material composition
3. Weight and form factor (if mentioned)
4. Industry category

You MUST respond with ONLY a valid JSON object (no markdown, no explanation outside the JSON).
Do not include ```json or ``` markers.

Response format (raw JSON only):
{{
  "matched_code": "XXXXXXX.XX.XXXX" or null if no good match,
  "match_confidence": 0.0-1.0,
  "rationale": "explanation of why this code matches (or why no match was found)"
}}"""
        
        llm_response_text = await call_groq(prompt)
        logger.debug(f"[{envelope_id}] Raw LLM response: {llm_response_text[:100]}...")
        
        llm_response_text = _strip_markdown(llm_response_text)
        
        llm_result = json.loads(llm_response_text)
        
        match_result = MatchResult(
            matched_code=llm_result.get("matched_code"),
            match_confidence=float(llm_result.get("match_confidence", 0.0)),
            rationale=llm_result.get("rationale", ""),
            fallback_used=True,
            source="llm_match" if llm_result.get("matched_code") else "no_match"
        )
        
        logger.info(
            f"[{envelope_id}] LLM matching succeeded: matched_code={match_result.matched_code}, confidence={match_result.match_confidence:.2f}"
        )
        
        if match_result.match_confidence < 0.70:
            envelope.decision = {"route": "hitl_review"}
            logger.info(
                f"[{envelope_id}] Match confidence {match_result.match_confidence:.2f} < 0.70 threshold, routing to hitl_review"
            )
        
        envelope.matching_results = match_result.model_dump()
        
        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "matching-service",
            "action": "llm_match",
            "envelope_id": envelope_id,
            "result": match_result.source,
            "details": {
                "matched_code": match_result.matched_code,
                "match_confidence": match_result.match_confidence,
                "fallback_used": match_result.fallback_used
            }
        }
        envelope.audit = list(envelope.audit) + [audit_entry]
        
        return envelope
    
    except json.JSONDecodeError as e:
        error_msg = f"JSON decode error: {str(e)}"
        logger.error(f"[{envelope_id}] LLM matching failed: {error_msg}")
        
        match_result = MatchResult(
            matched_code=None,
            match_confidence=0.0,
            rationale=f"LLM matching failed: {error_msg}",
            fallback_used=False,
            source="no_match"
        )
        
        envelope.decision = {"route": "hitl_review"}
        envelope.matching_results = match_result.model_dump()
        
        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "matching-service",
            "action": "llm_match",
            "envelope_id": envelope_id,
            "result": "failed",
            "details": {
                "error": error_msg,
                "fallback_used": False
            }
        }
        envelope.audit = list(envelope.audit) + [audit_entry]
        
        return envelope
    
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        logger.error(f"[{envelope_id}] LLM matching failed: {error_msg}")
        
        match_result = MatchResult(
            matched_code=None,
            match_confidence=0.0,
            rationale=f"LLM matching failed: {error_msg}",
            fallback_used=False,
            source="no_match"
        )
        
        envelope.decision = {"route": "hitl_review"}
        envelope.matching_results = match_result.model_dump()
        
        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "matching-service",
            "action": "llm_match",
            "envelope_id": envelope_id,
            "result": "failed",
            "details": {
                "error": error_msg,
                "fallback_used": False
            }
        }
        envelope.audit = list(envelope.audit) + [audit_entry]
        
        return envelope
