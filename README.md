# edi-integration-pipeline

A small, deliberately plain Python project demonstrating two EDI workflows:

1. **Inbound X12 850** → validate envelope → parse → validate transaction → generate 997 → convert to JSON
2. **Outbound invoice JSON** → validate → generate X12 810 → validate the generated EDI

Everything runs two ways — from files and from a FastAPI endpoint — using the
**same functions**. There is only one copy of the EDI logic.

The code uses only functions, dictionaries, lists, strings, loops and
conditionals. No classes, no dataclasses, no database, no third-party EDI
library. Readability is the point.

> **Build status:** This is a rebuild of the `v0.1-simple` baseline, adding an
> explicit envelope-validation layer and splitting validation/translation by
> transaction type. `validate_envelope.py`'s six check functions are built and
> verified; the public `validate_envelope()` orchestrator, transaction-tier
> porting, and the HTTP status-code mapping are in progress. See
> **Where this stands** below for the current line.

---

## Why an envelope layer

Real EDI platforms (Sterling, WTX) treat envelope integrity — ISA/GS/GE/IEA
structure, delimiter detection, control-number matching — as a distinct gate
that runs *before* any transaction-specific validation, because a broken
envelope means segment boundaries themselves can't be trusted. This project
mirrors that: `validate_envelope()` runs first and can halt outright
(`EDIParseError`) on a file too malformed to even parse, or collect a list of
structural errors (missing segments, bad control numbers, mismatched counts)
that don't stop parsing but do fail the interchange. Only once the envelope
passes does transaction-tier validation (850/810 specific rules) run.

This also drives the HTTP contract: envelope failure is a client error (400)
— the request itself was malformed. Transaction-tier rejection is not — a
correctly-formed 850 that fails business validation is a *successful* API
call that correctly reports an EDI business outcome, so it returns 200 with
the rejection recorded in the 997 body (AK5/AK9), not in the HTTP status.

---

## Flow diagram

### Inbound 850 Purchase Order Workflow

```mermaid
flowchart TD
    A1["File input: input/valid_850.txt<br/>or API: POST /edi/850"] --> A2["validate_envelope()<br/>src/validate_envelope.py"]
    A2 -->|EDIParseError| A2E["HTTP 400<br/>envelope structurally invalid"]
    A2 -->|Envelope OK| A3["translate_850()<br/>src/translation/translate_850.py"]
    A3 --> A4["validate_850()<br/>src/validation/validate_850.py"]
    A4 -->|Valid or Invalid| A5["generate_997()<br/>src/edi_997.py"]
    A4 -->|Valid 850| A6["Purchase order JSON"]
    A5 --> A7["Save 997<br/>output/997/PO10001_997.txt"]
    A6 --> A8["Save PO JSON<br/>output/850_json/PO10001.json"]
    A7 --> A9["HTTP 200<br/>always, regardless of AK5 accept/reject"]
    A8 --> A9
```

### Outbound 810 Invoice Workflow

```mermaid
flowchart TD
    B1["File input: input/valid_invoice.json<br/>or API: POST /invoice/810"] --> B2["validate_invoice()<br/>src/validation/validate_810.py"]
    B2 -->|Valid invoice| B3["translate_810()<br/>src/translation/translate_810.py"]
    B2 -->|Invalid invoice| B4["Return validation errors"]
    B3 --> B5["validate_generated_810()<br/>src/validation/validate_810.py"]
    B5 --> B6["Save X12 810<br/>output/810/INV10001_810.txt"]
    B6 --> B7["Return API response<br/>or file-based result"]
```

---

## Project structure

```
edi-integration-pipeline/
├── src/
│   ├── main.py                       FastAPI app + file-based examples + the two pipelines
│   ├── edi_parser.py                 delimiter detection, segment/element splitting,
│   │                                  segment lookup — parsing primitives only
│   ├── edi_exceptions.py             EDIParseError
│   ├── validate_envelope.py          envelope structural gate (ISA/GS/GE/IEA)
│   ├── validation/
│   │   ├── validation_shared.py      shared primitives (presence, qualifier pairing)
│   │   ├── validate_850.py           compliance + business-rule checks for inbound 850
│   │   └── validate_810.py           checks for invoice JSON and generated 810
│   ├── translation/
│   │   ├── translation_shared.py     shared parse/convert primitives
│   │   ├── translate_850.py          850 segments -> purchase order JSON (parse + convert)
│   │   └── translate_810.py          invoice JSON -> 810 segments
│   ├── edi_997.py                    generate_997()
│   └── edi_810.py                    generate_810() and the invoice total math
├── input/                            sample inbound files
├── output/
│   ├── 997/                          generated X12 997 acknowledgments
│   ├── 850_json/                     JSON produced from inbound 850s
│   └── 810/                          generated X12 810 invoices
├── tests/test_edi.py                 pytest suite
├── requirements.txt
├── .gitignore
└── README.md
```

### What each Python file does

| File | Contents |
|---|---|
| `src/edi_parser.py` | `read_text_file()`, `write_text_file()`, `read_json_file()`, `write_json_file()`, `detect_delimiters()`, `split_segments()`, `parse_edi()`, `get_segment()`, `get_segments()`, `get_element()`, `pad_to_length()`. Parsing-only — no transaction-specific translation logic lives here. |
| `src/edi_exceptions.py` | `EDIParseError` — raised for halt-tier parse failures (interchange too short/malformed to safely parse further). |
| `src/validate_envelope.py` | `validate_envelope()` — public orchestrator (in progress). Private checks: `check_isa()` (halt-tier), `check_required_envelopes()`, `check_gs04()`, `check_control_numbers()`, `check_group_count()`, `check_transaction_count()` (collect-tier, share one `errors` list). |
| `src/validation/validate_850.py` | Transaction-tier checks for an inbound 850, split into compliance-tier (feeds the 997/AK5) and business-rule-tier (value sanity, no ack equivalent). |
| `src/validation/validate_810.py` | `validate_invoice()`, `validate_generated_810()`. |
| `src/validation/validation_shared.py` | Primitives shared across 850/810 validation — segment presence, qualifier-pairing checks (e.g. REF01→REF02), `is_number()`, `has_value()`. |
| `src/translation/translate_850.py` | Parses 850 segments and converts to purchase-order JSON in one step — parsing is a sub-step of translation, not a peer stage. |
| `src/translation/translate_810.py` | Converts invoice JSON to 810 segments. |
| `src/translation/translation_shared.py` | Primitives shared across 850/810 translation. |
| `src/edi_997.py` | `generate_997()` — builds ISA/GS/ST/AK1/AK2/AK5/AK9/SE/GE/IEA, accepted or rejected. |
| `src/edi_810.py` | `generate_810()`, `calculate_invoice_total()`, `calculate_line_amount()`, `make_control_number()`. |
| `src/main.py` | `process_850()`, `save_850_output()`, `process_invoice()`, `save_810_output()`, the three API endpoints, and `run_file_examples()`. |

### What `input/` contains

| File | Purpose |
|---|---|
| `valid_850.txt` | One buyer, one seller, two PO1 lines. Passes validation. |
| `invalid_850.txt` | BEG has no PO number and no PO date, and the PO1 quantity is `ABC`. Fails three ways. |
| `valid_invoice.json` | Two line items totalling 350.00. Passes validation. |
| `invalid_invoice.json` | No `invoice_number`, no `seller`, quantity `ABC`, blank `product_id`, negative price. Fails five ways. |

### What `output/` contains

| Folder | Written by | Example filename |
|---|---|---|
| `output/997/` | `save_850_output()` | `PO10001_997.txt`, `REJECTED_997.txt` |
| `output/850_json/` | `save_850_output()` (accepted only) | `PO10001.json` |
| `output/810/` | `save_810_output()` | `INV10001_810.txt` |

---

## Where this stands

Built and terminal-verified today:

- `edi_parser.py`: `detect_delimiters()`, `split_segments()`, `parse_edi()` wired together correctly
- `validate_envelope.py` private checks, all six: `check_isa()` (halt-tier, raises `EDIParseError`), `check_required_envelopes()`, `check_gs04()`, `check_control_numbers()`, `check_group_count()`, `check_transaction_count()` (collect-tier, share one `errors` list)

Not yet built:

- `validate_envelope()` itself — the public function wiring the six checks together in sequence and returning the accumulated `errors` list
- Transaction-tier porting into `validation/validate_850.py` / `validate_810.py`
- Parse/convert logic into `translation/translate_850.py` / `translate_810.py`
- HTTP status-code mapping in `main.py` (400 on envelope failure, 200 always on a processed request regardless of AK5 accept/reject, 500 only on genuine unhandled bugs)

Known open questions, deliberately deferred rather than guessed at:

- Fixed positional indexing vs. qualifier-scanning for PO1 line items
- Whether `get_element()`'s silent `""` fallback on a missing element should instead be a checker-tier rejection
- True calendar validity for GS04 (currently checks digit-format/length only, not that the date is a real calendar date)

---

## Setup on macOS

Create the virtual environment (once):

```bash
cd /Users/aperalta/python-projects/edi-integration-pipeline && python3 -m venv .venv
```

Activate it (every new terminal session):

```bash
cd /Users/aperalta/python-projects/edi-integration-pipeline && source .venv/bin/activate
```

Your prompt now starts with `(.venv)`. Install the dependencies:

```bash
pip install -r requirements.txt
```

Leave the virtual environment later with `deactivate`.

---

## Run the file-based examples

This processes all four sample files and prints a full trace:

```bash
python src/main.py
```

## Start the API

```bash
uvicorn main:app --app-dir src --reload
```

`--app-dir src` puts `src/` on Python's import path, so `import edi_parser`
inside `main.py` works. `--reload` restarts the server when you edit a file.

Then open the interactive Swagger documentation in a browser:

```
http://127.0.0.1:8000/docs
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Expected: `{"status":"ok"}`

## Submit the sample 850

From a second terminal, in the project folder:

```bash
curl -X POST http://127.0.0.1:8000/edi/850 -H "Content-Type: text/plain" --data-binary @input/valid_850.txt
```

The response contains `validation_status`, `validation_errors`,
`purchase_order`, `acknowledgment_997` and `saved_files`. Try the invalid one
to see the error messages:

```bash
curl -X POST http://127.0.0.1:8000/edi/850 -H "Content-Type: text/plain" --data-binary @input/invalid_850.txt
```

## Submit the invoice JSON

```bash
curl -X POST http://127.0.0.1:8000/invoice/810 -H "Content-Type: application/json" --data-binary @input/valid_invoice.json
```

```bash
curl -X POST http://127.0.0.1:8000/invoice/810 -H "Content-Type: application/json" --data-binary @input/invalid_invoice.json
```

## Inspect the generated files

```bash
find output -type f
```

```bash
cat output/997/PO10001_997.txt
```

```bash
cat output/850_json/PO10001.json
```

```bash
cat output/810/INV10001_810.txt
```

## Run the tests

```bash
pytest
```

---

## How an 850 moves through the Python functions

```
input/valid_850.txt              POST /edi/850
        |                              |
   read_text_file()              post_850()  (main.py)
        |                              |
        +--------------+---------------+
                       |
                process_850(edi_text)          <- main.py, read this top to bottom
                       |
                validate_envelope()            <- validate_envelope.py
                       |     raises EDIParseError (halt) or collects
                       |     structural errors -> 400 if any halt-tier failure
                translate_850()                <- translation/translate_850.py
                       |     text -> purchase order JSON (parse is a sub-step)
                validate_850()                 <- validation/validate_850.py
                       |     returns [] or a list of readable error strings
                generate_997()                 <- edi_997.py
                       |     uses the inbound ISA / GS06 / ST02
                save_850_output()              <- main.py
                       |
        output/997/PO10001_997.txt
        output/850_json/PO10001.json
```

The API endpoint and the file example call exactly the same `process_850()`.
The only difference is where the EDI text came from.

## How an invoice moves through the Python functions

```
input/valid_invoice.json         POST /invoice/810
        |                              |
   read_json_file()              post_810()  (main.py)
        |                              |
        +--------------+---------------+
                       |
             process_invoice(invoice)          <- main.py
                       |
                validate_invoice()             <- validation/validate_810.py
                       |
                translate_810()                <- translation/translate_810.py
                       |     BIG, REF, N1 x2, IT1 per line,
                       |     TDS from calculate_invoice_total(),
                       |     CTT, then the SE segment count
                validate_generated_810()       <- validation/validate_810.py
                       |     re-parses the EDI it just built and
                       |     checks SE01 and CTT01 add up
                save_810_output()              <- main.py
                       |
        output/810/INV10001_810.txt
```

---

## Where to start reading

Start with **`src/main.py`**, specifically `process_850()`. It names every
other function in the project in the order they run. From there follow each
call into `validate_envelope.py`, `edi_parser.py`, `translation/`,
`validation/`, `edi_997.py`, and `edi_810.py`.
