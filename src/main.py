"""
main.py
-------
The entry point for BOTH ways of running this project:

    * the FastAPI endpoints  (see the "API endpoints" section near the bottom)
    * the file based examples (run this file directly: python src/main.py)

The two share the same processing functions - process_850() and
process_invoice() - so there is only ever one copy of the EDI logic.

Trace an inbound 850 by reading process_850() from top to bottom.
Trace an outbound invoice by reading process_invoice() from top to bottom.
"""

import os

from fastapi import Body, FastAPI

from edi_parser import (
    parse_edi,
    convert_850_to_json,
    read_text_file,
    read_json_file,
    write_text_file,
    write_json_file,
)
from validation import validate_850, validate_invoice, validate_generated_810
from edi_997 import generate_997
from edi_810 import generate_810


# ---------------------------------------------------------------------------
# Folder locations
# ---------------------------------------------------------------------------
# __file__ is the path of THIS file. Two dirname() calls step up from
# .../simple-edi-pipeline/src/main.py to .../simple-edi-pipeline, so the paths
# below work no matter which folder the program is started from.
PROJECT_FOLDER = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

INPUT_FOLDER = os.path.join(PROJECT_FOLDER, "input")
OUTPUT_997_FOLDER = os.path.join(PROJECT_FOLDER, "output", "997")
OUTPUT_850_JSON_FOLDER = os.path.join(PROJECT_FOLDER, "output", "850_json")
OUTPUT_810_FOLDER = os.path.join(PROJECT_FOLDER, "output", "810")


# ---------------------------------------------------------------------------
# Workflow 1 - inbound 850
# ---------------------------------------------------------------------------

def process_850(edi_text):
    """Run one inbound 850 through the whole pipeline.

    parse -> validate -> 997 -> JSON

    Returns a dictionary holding every result, so the caller can decide what
    to do with it (write files, return it from the API, assert on it in a test).
    """
    # STEP 1 - text into a list of segments
    segments = parse_edi(edi_text)

    # STEP 2 - check the segments
    validation_errors = validate_850(segments)

    # STEP 3 - acknowledge, accepted or rejected
    acknowledgment_997 = generate_997(segments, validation_errors)

    # STEP 4 - only convert to JSON when the 850 is good
    if len(validation_errors) == 0:
        validation_status = "accepted"
        purchase_order = convert_850_to_json(segments)
    else:
        validation_status = "rejected"
        purchase_order = None

    result = {}
    result["validation_status"] = validation_status
    result["validation_errors"] = validation_errors
    result["purchase_order"] = purchase_order
    result["acknowledgment_997"] = acknowledgment_997

    return result


def save_850_output(result):
    """Write the 997, and the purchase order JSON when there is one.

    Returns a dictionary of the files that were written, which is handy for
    printing a trace or returning from the API.
    """
    saved_files = {}

    if result["validation_status"] == "accepted":
        purchase_order_number = result["purchase_order"]["purchase_order_number"]
    else:
        # A rejected 850 may have no usable PO number, so fall back to
        # something that still identifies the file.
        purchase_order_number = "REJECTED"

    # ----- always save the 997 -----
    ack_path = os.path.join(OUTPUT_997_FOLDER, purchase_order_number + "_997.txt")
    write_text_file(ack_path, result["acknowledgment_997"])
    saved_files["acknowledgment_997"] = ack_path

    # ----- only save JSON for an accepted 850 -----
    if result["validation_status"] == "accepted":
        json_path = os.path.join(
            OUTPUT_850_JSON_FOLDER, purchase_order_number + ".json"
        )
        write_json_file(json_path, result["purchase_order"])
        saved_files["purchase_order_json"] = json_path

    return saved_files


# ---------------------------------------------------------------------------
# Workflow 2 - outbound invoice / 810
# ---------------------------------------------------------------------------

def process_invoice(invoice):
    """Run one invoice dictionary through the whole pipeline.

    validate -> generate 810 -> validate the generated 810
    """
    # STEP 1 - check the incoming JSON
    validation_errors = validate_invoice(invoice)

    if len(validation_errors) > 0:
        result = {}
        result["validation_status"] = "rejected"
        result["validation_errors"] = validation_errors
        result["edi_810"] = None
        return result

    # STEP 2 - build the EDI
    edi_810 = generate_810(invoice)

    # STEP 3 - read the generated EDI back and check it
    generated_errors = validate_generated_810(edi_810)

    if len(generated_errors) > 0:
        result = {}
        result["validation_status"] = "rejected"
        result["validation_errors"] = generated_errors
        result["edi_810"] = None
        return result

    result = {}
    result["validation_status"] = "accepted"
    result["validation_errors"] = []
    result["edi_810"] = edi_810
    result["invoice_number"] = invoice["invoice_number"]

    return result


def save_810_output(result):
    """Write the generated 810 to output/810/ and return the file paths."""
    saved_files = {}

    if result["validation_status"] != "accepted":
        return saved_files

    file_name = result["invoice_number"] + "_810.txt"
    edi_path = os.path.join(OUTPUT_810_FOLDER, file_name)
    write_text_file(edi_path, result["edi_810"])
    saved_files["edi_810"] = edi_path

    return saved_files


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Simple EDI Pipeline",
    description="Inbound X12 850 -> 997 + JSON, and invoice JSON -> X12 810.",
)


@app.get("/health")
def health():
    """Confirm the API is running."""
    return {"status": "ok"}


@app.post("/edi/850")
def post_850(edi_text: str = Body(..., media_type="text/plain")):
    """Accept a raw X12 850 as plain text.

    Body(..., media_type="text/plain") tells FastAPI to hand over the request
    body as a plain string instead of parsing it as JSON. The "..." means the
    body is required.
    """
    result = process_850(edi_text)
    saved_files = save_850_output(result)

    response = {}
    response["validation_status"] = result["validation_status"]
    response["validation_errors"] = result["validation_errors"]
    response["purchase_order"] = result["purchase_order"]
    response["acknowledgment_997"] = result["acknowledgment_997"]
    response["saved_files"] = saved_files

    return response


@app.post("/invoice/810")
def post_810(invoice: dict = Body(...)):
    """Accept an invoice as JSON and return the generated X12 810.

    The body is typed as a plain `dict`, so FastAPI simply converts the JSON
    into a Python dictionary. No models or classes are involved.
    """
    result = process_invoice(invoice)
    saved_files = save_810_output(result)

    response = {}
    response["validation_status"] = result["validation_status"]
    response["validation_errors"] = result["validation_errors"]
    response["edi_810"] = result["edi_810"]
    response["saved_files"] = saved_files

    return response


# ---------------------------------------------------------------------------
# File based examples (python src/main.py)
# ---------------------------------------------------------------------------

def run_850_file_example(file_name):
    """Read one 850 from input/, process it, and print a short trace."""
    print("=" * 70)
    print("850 FILE EXAMPLE:", file_name)
    print("=" * 70)

    file_path = os.path.join(INPUT_FOLDER, file_name)
    edi_text = read_text_file(file_path)

    result = process_850(edi_text)
    saved_files = save_850_output(result)

    print("validation status:", result["validation_status"])

    for error in result["validation_errors"]:
        print("  error:", error)

    if result["purchase_order"] is not None:
        purchase_order = result["purchase_order"]
        print("PO number :", purchase_order["purchase_order_number"])
        print("PO date   :", purchase_order["purchase_order_date"])
        print("buyer     :", purchase_order["buyer"]["name"])
        print("seller    :", purchase_order["seller"]["name"])
        print("line items:", purchase_order["line_item_count"])

    print("generated 997:")
    print(result["acknowledgment_997"].strip())

    for description in saved_files:
        print("saved", description, "->", saved_files[description])

    print("")


def run_invoice_file_example(file_name):
    """Read one invoice from input/, process it, and print a short trace."""
    print("=" * 70)
    print("INVOICE FILE EXAMPLE:", file_name)
    print("=" * 70)

    file_path = os.path.join(INPUT_FOLDER, file_name)
    invoice = read_json_file(file_path)

    result = process_invoice(invoice)
    saved_files = save_810_output(result)

    print("validation status:", result["validation_status"])

    for error in result["validation_errors"]:
        print("  error:", error)

    if result["edi_810"] is not None:
        print("generated 810:")
        print(result["edi_810"].strip())

    for description in saved_files:
        print("saved", description, "->", saved_files[description])

    print("")


def run_file_examples():
    """Process all four sample files in input/."""
    run_850_file_example("valid_850.txt")
    run_850_file_example("invalid_850.txt")
    run_invoice_file_example("valid_invoice.json")
    run_invoice_file_example("invalid_invoice.json")


# This block runs only when the file is executed directly
# (python src/main.py), not when uvicorn or pytest imports it.
if __name__ == "__main__":
    run_file_examples()
