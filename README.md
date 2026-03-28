# Document Intelligence Microservice

A FastAPI-based microservice for intelligent document validation and commodity classification using LLM-assisted matching.

## Quick Start (3 commands)

```bash
python -m venv env
env\Scripts\activate && pip install -r requirements.txt
pytest -v && uvicorn app.main:app --reload
```

## What It Does

**Validation Service** (`/validate`)
- Schema validation: Ensures shipment_id and recipient_name exist
- Confidence thresholds: Flags fields below 80% confidence
- Date range checks: Validates shipment dates are within reasonable bounds
- Routes to either auto-approval or human review

**LLM Matching Service** (`/match`)
- Triggered when commodity_code confidence is below threshold
- Uses Groq API with llama-3.3-70b-versatile model
- Returns matched HS code with confidence score
- Gracefully degrades if LLM fails (network timeout, parsing errors)

**End-to-End Pipeline** (`/process`)
- Chains validation → conditional LLM matching
- Enriches envelope with audit trail
- Single endpoint for complete document processing

## Design Notes

### Architecture Decisions

1. **Confidence-based routing**: Optional fields (commodity_code, commodity_desc) with low confidence trigger LLM enrichment rather than rejection. This minimizes false negatives while keeping validation strict on required fields.

2. **Mockable LLM layer**: The `call_groq()` function is designed to be easily mocked in tests and swappable for other providers. Uses `asyncio.to_thread()` to prevent blocking the async event loop during synchronous API calls.

3. **Envelope-based audit logging**: Every processing step appends to an audit trail with timestamps and decision context. Correlation IDs enable end-to-end request tracing in production logs.

4. **Optional vs Required fields**:
   - Required: `shipment_id`, `recipient_name`, at least one of `commodity_code`/`commodity_desc`
   - Optional: `commodity_code`, `commodity_desc` (with confidence scores)
   - Confidence checks only fail on required fields; optional fields with low confidence trigger enrichment instead

5. **Graceful degradation**: All LLM failures (timeout, JSON parse error, network issue) route to HITL review with detailed error context preserved in audit trail.

### Data Model

```
Envelope
├── extraction (required)
│   ├── shipment_id (required, with confidence)
│   ├── recipient_name (required, with confidence)
│   ├── commodity_code (optional, with confidence)
│   └── commodity_desc (optional, with confidence)
├── processing_instructions
│   ├── confidence_threshold (0.80 default)
│   ├── hitl_on_failure (route to human if validation fails)
│   └── workflow (manifest-v1)
├── validation_results (enriched on /validate)
├── matching_results (enriched on /match, if triggered)
├── decision (routing: auto_approve | hitl_review)
└── audit (immutable trace of all operations)
```

### Testing Strategy

6 test cases covering:
- **Happy path**: All fields above threshold → auto approval
- **Low confidence on required field**: Triggers HITL review
- **LLM matching triggered**: Low commodity_code confidence → LLM call → high-confidence match → auto approval
- **Invalid input**: Missing required field → 422 validation error
- **LLM failure handling**: Network timeout gracefully degrades to HITL review
- **HTTP integration**: Full pipeline via REST endpoint with mocked LLM

All tests mock the Groq API to avoid rate limits and ensure reproducibility.

### API Endpoints

| Method | Endpoint | Purpose | Returns |
|--------|----------|---------|---------|
| POST | `/validate` | Validation only | Envelope + validation_results |
| POST | `/match` | LLM matching only | Envelope + matching_results |
| POST | `/process` | Full pipeline | Envelope + all enrichments |

### Environment Setup

- **Python**: 3.11+
- **Dependencies**: FastAPI, Uvicorn, Pydantic v2, Groq SDK, pytest-asyncio
- **LLM**: Groq API (free tier, llama-3.3-70b-versatile model)
- **Required**: Set `GROQ_API_KEY` in `.env`

### Known Limitations

- Commodity matching depends on Groq API availability (free tier may have rate limits)
- Confidence thresholds are hardcoded (0.80 for validation, 0.70 for match acceptance)
- No database persistence—envelope state exists only during request lifecycle
- No authentication/authorization layer (add before production)

## Running Tests

```bash
pytest -v                 # Run all tests with verbose output
pytest -v --tb=short      # Shorter traceback format
```

All 6 tests should pass with mocked LLM calls (no actual API usage during tests).

## Deployment Considerations

- Add API key rotation and secret management (AWS Secrets Manager, HashiCorp Vault)
- Implement request id/correlation tracing across services
- Add structured JSON logging for log aggregation (ELK, CloudWatch)
- Rate limit LLM calls to avoid quota exhaustion
- Cache commodity catalog in Redis for high-throughput scenarios
- Monitor LLM response times and graceful degradation triggers
