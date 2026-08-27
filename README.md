# edi-integration-pipeline

Python-based X12 EDI integration pipeline for parsing, validating, translating, and acknowledging EDI transactions without a third-party EDI library.

The project demonstrates two production-shaped workflows:

| Workflow | Input | Processing | Output |
|---|---|---|---|
| Inbound purchase order | X12 850 | Envelope validation, compliance validation, translation, acknowledgment generation | Purchase-order JSON and 997 acknowledgment |
| Outbound invoice | Invoice JSON | Business validation, X12 810 generation, round-trip validation | X12 810 invoice |

Both the command-line examples and the FastAPI service use the same processing functions. The entry point changes, but the EDI logic does not.

---

## Purpose

This project shows how Python can support practical EDI/B2B integration work:

- Validate X12 envelopes before transaction-level processing.
- Detect delimiters from the inbound ISA segment instead of assuming `*` and `~`.
- Validate selected 850 purchase-order rules before translation.
- Generate 997 acknowledgments for accepted and rejected 850 transactions.
- Translate valid 850 purchase orders into structured JSON.
- Translate invoice JSON into X12 810 invoice output.
- Re-parse generated outbound EDI to confirm structural correctness before writing the file.

The focus is not to replace enterprise EDI translators. The focus is to make the pipeline behavior visible, testable, and understandable in plain Python.

---

## Features

- Inbound X12 850 processing
- Outbound X12 810 generation
- 997 functional acknowledgment generation, with per-rule AK5/AK905 codes and first-seen-order deduplication when more than five errors apply
- ISA delimiter detection
- Envelope validation for ISA/GS/GE/IEA structure, split by acknowledgment tier
- Control-number validation
- Transaction-level validation for selected 850 rules
- Invoice JSON validation before 810 generation
- Generated-810 round-trip validation
- CLI-style sample file processing
- FastAPI endpoints for HTTP-based processing
- Pytest test suite covering both validation tiers, the 997 dedupe logic, and the FastAPI endpoints directly
- Fictional sample input files

---

## High-Level Processing Flow

### Inbound 850

```text
X12 850 input
   ↓
Parse EDI and detect delimiters
   ↓
Validate envelope structure
   ↓
Validate 850 compliance rules
   ↓
Generate 997 acknowledgment
   ↓
Translate accepted 850 to JSON
   ↓
Write output files / return API response
```

### Outbound 810

```text
Invoice JSON input
   ↓
Validate invoice payload
   ↓
Translate invoice JSON to X12 810
   ↓
Re-parse generated 810
   ↓
Validate generated EDI structure
   ↓
Write output file / return API response
```

For the detailed diagrams, call order, module responsibilities, validation rules, fixtures, and troubleshooting notes, see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Project Structure

```text
edi-integration-pipeline/
├── src/
│   ├── main.py
│   ├── edi_parser.py
│   ├── edi_exceptions.py
│   ├── edi_997.py
│   ├── validate_envelope.py
│   ├── validation/
│   │   ├── validation_shared.py
│   │   ├── validate_850.py
│   │   └── validate_810.py
│   └── translation/
│       ├── translate_850.py
│       └── translate_810.py
├── input/
│   ├── valid_850.txt
│   ├── invalid_850.txt
│   ├── valid_invoice.json
│   └── invalid_invoice.json
├── output/
│   ├── 997/
│   ├── 850_json/
│   └── 810/
├── tests/
├── docs/
│   └── ARCHITECTURE.md
├── README.md
├── requirements.txt
└── .gitignore
```

---

## Requirements

- Python 3.12+
- FastAPI
- Uvicorn
- pytest
- httpx (test dependency — powers FastAPI's `TestClient` for endpoint tests; not imported by the application itself)

Install dependencies from `requirements.txt`.

---

## Setup

```bash
git clone https://github.com/<your-username>/edi-integration-pipeline.git
cd edi-integration-pipeline

python3 -m venv .venv
source .venv/bin/activate

pip install -r requirements.txt
```

---

## Usage

### Run the sample file workflow

```bash
python src/main.py
```

This runs the sample inbound and outbound files and writes generated output to the `output/` folders.

### Run the API service

```bash
uvicorn main:app --app-dir src --reload
```

Interactive API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

### Submit an inbound 850 through the API

```bash
curl -X POST http://127.0.0.1:8000/edi/850 \
  -H "Content-Type: text/plain" \
  --data-binary @input/valid_850.txt
```

### Submit an outbound invoice payload through the API

Use the `/invoice/810` endpoint with one of the invoice JSON files in `input/`.

---

## Testing

Run the full test suite:

```bash
pytest
```

Run tests with verbose output:

```bash
pytest -v
```

The suite covers both envelope-validation tiers, transaction-level AK5 codes, the 997 dedupe/fold-to-5 logic, and the FastAPI endpoints directly via `TestClient` — not just the underlying functions.

---

## Example Outputs

The project generates three main output types:

| Output | Folder | Description |
|---|---|---|
| 997 acknowledgment | `output/997/` | Functional acknowledgment for accepted or rejected 850 transactions |
| Purchase-order JSON | `output/850_json/` | Translated JSON output for accepted 850 transactions |
| X12 810 invoice | `output/810/` | Generated outbound invoice EDI |

A valid inbound 850 produces both a 997 acknowledgment and purchase-order JSON. An 850 that fails transaction-level validation produces a rejected 997 and no purchase-order JSON.

Envelope-level failures split by acknowledgment tier. A group-tier failure (for example, a GS/GE control-number mismatch) still produces a rejected 997, since the functional group can be identified even though the transaction inside it was never evaluated — no purchase-order JSON is produced. An interchange-tier failure (ISA/IEA, or a missing GS) produces no 997 at all, because the interchange control information is not safe to reuse.

---

## Design Notes

The major design decisions are:

- Envelope validation is separate from transaction validation.
- Envelope validation is itself split by acknowledgment tier: interchange-tier failures (ISA/IEA, missing GS) are unacknowledgeable and halt with no 997; group-tier failures (GS/GE control-number or count mismatches) are acknowledgeable and produce a rejected 997 instead.
- Unparseable or structurally unsafe interchanges halt before 997 generation.
- Transaction-level compliance failures return a business rejection, not a transport failure.
- Validation runs before translation.
- Every transaction-level validation error carries a specific AK5 code, and `generate_997()` deduplicates repeated codes in first-seen order before slicing to the five AK502–AK506 slots, so a common error doesn't crowd out a more specific one.
- Generated outbound 810 files are re-parsed and validated before being written.
- Delimiters are detected from the inbound ISA and reused when generating acknowledgments.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full design rationale.

---

## Current Scope

### In scope

- X12 850 purchase-order parsing
- X12 850 compliance validation for selected rules, with accurate per-rule AK5 codes
- X12 850 to JSON translation
- 997 acknowledgment generation for accepted, transaction-rejected, and group-rejected outcomes
- Invoice JSON validation
- Invoice JSON to X12 810 translation
- Generated 810 validation
- CLI sample processing
- FastAPI endpoints, verified end-to-end (both HTTP status paths and response bodies) via automated tests and manual curl checks
- Automated tests

### Out of scope for now

- Automated invoice assembly (`build_invoice()`) from `output/850_json/` — in a real integration architecture, the ERP or accounting system owns invoice creation as part of order-to-cash; this pipeline validates and translates the invoice payload it's handed, it doesn't create that payload. Outbound invoices are supplied directly as JSON by design, not as a stand-in for missing functionality.
- Full X12 implementation-guide validation
- Partner-specific business rules
- AK3/AK4 segment-level detail in the 997
- Database persistence
- Authentication and authorization
- Production message transport such as AS2, SFTP, VAN, or MQ
- Warehouse loading and dbt models
- Multi-GS/multi-ST batch files — v1 assumes one GS and one ST/SE per interchange. Real batch feeds commonly nest multiple transactions inside one functional group, but extending the two-tier validation model and `generate_997()` to a repeating AK1/AK2/AK9 loop is real scope, not a one-line change; named v2 work. If pursued, multi-ST within a single GS is the priority case, since that's the common batching pattern; multi-GS is a stretch goal on top of it.

---

## Roadmap

- [x] Parse inbound X12 850 files
- [x] Validate envelope structure
- [x] Split envelope validation by acknowledgment tier (interchange vs. group)
- [x] Validate selected 850 compliance rules
- [x] Generate accepted and rejected 997 acknowledgments
- [x] Retrofit transaction-level validation to carry real AK5 codes, with first-seen-order deduplication in `generate_997()`
- [x] Translate valid 850 files to JSON
- [x] Generate outbound X12 810 invoices from JSON
- [x] Re-parse and validate generated 810 output
- [x] Close test-suite coverage gaps against the two-tier validation model (envelope, transaction, dedupe logic)
- [x] Verify FastAPI endpoints end-to-end, via `TestClient` and manual curl checks
- [ ] Add AK3/AK4 details to rejected 997 acknowledgments
- [ ] Add partner-specific validation rule examples
- [ ] Add batch-processing summary reports
- [ ] Add structured logging
- [ ] Support multi-GS/multi-ST batch files (v1 assumes one GS and one ST/SE per interchange)

---

## Data Safety

All EDI and invoice examples in this repository are fictional, generated, or sanitized.

Do not commit:

- Production EDI transactions
- Trading-partner credentials
- API keys
- Connection details
- Certificates
- Passwords
- `.env` files
- Partner-specific implementation-guide documents that cannot be shared publicly

---

## Project Status

**v1 complete.** The inbound 850 pipeline (parse → envelope validation → transaction validation → translation → 997) and the outbound 810 pipeline (validate → translate → round-trip validate) are both implemented, tested, and verified end-to-end through the FastAPI service. Invoice creation is intentionally out of scope — that responsibility belongs to the ERP/accounting system upstream; this pipeline validates and translates the invoice payload it receives.

---

## Where to Start Reading

Start with `src/main.py`, especially:

- `process_850()` for the inbound purchase-order workflow
- `process_invoice()` for the outbound invoice workflow

Then read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the execution flow and module-level explanation.
