"""
validation.py
-------------
All validation for this project. Every validate_* function follows the same
simple pattern:

    1. start with an empty list of errors
    2. check one thing at a time
    3. append a human readable sentence when a check fails
    4. return the list

An EMPTY list means "valid". This avoids exceptions and keeps the calling code
easy to read:

    errors = validate_850(segments)
    if len(errors) == 0:
        ...
"""

from edi_parser import get_segment, get_segments, get_element, parse_edi
from validation.validation_shared import is_number, is_positive_number, has_value


# ---------------------------------------------------------------------------
# Outbound invoice (JSON) validation
# ---------------------------------------------------------------------------

def validate_invoice(invoice):
    """Check an invoice dictionary and return a list of human readable errors."""
    errors = []

    # ----- simple top level fields -----
    required_fields = [
        "invoice_number",
        "invoice_date",
        "purchase_order_number",
    ]
    for field_name in required_fields:
        if not has_value(invoice, field_name):
            errors.append("Invoice field is missing or empty: " + field_name)

    # ----- buyer and seller are small nested dictionaries -----
    for party_name in ["buyer", "seller"]:
        if party_name not in invoice:
            errors.append("Invoice is missing the " + party_name + " section")
            continue

        party = invoice[party_name]
        if not has_value(party, "name"):
            errors.append("Missing " + party_name + " name")
        if not has_value(party, "id"):
            errors.append("Missing " + party_name + " id")

    # ----- line items -----
    if "line_items" not in invoice:
        errors.append("Invoice is missing the line_items list")
        return errors

    line_items = invoice["line_items"]
    if len(line_items) == 0:
        errors.append("Invoice has no line items - at least one is required")
        return errors

    # enumerate() gives the position AND the value. start=1 so the numbering
    # matches how a human counts line items.
    for position, line_item in enumerate(line_items, start=1):
        label = "Line item " + str(position) + ": "

        if not has_value(line_item, "product_id"):
            errors.append(label + "product/SKU identifier is missing")

        if not has_value(line_item, "quantity"):
            errors.append(label + "quantity is missing")
        elif not is_positive_number(line_item["quantity"]):
            errors.append(
                label + "quantity '" + str(line_item["quantity"]) +
                "' is not a valid positive number"
            )

        if not has_value(line_item, "unit_price"):
            errors.append(label + "unit price is missing")
        elif not is_positive_number(line_item["unit_price"]):
            errors.append(
                label + "unit price '" + str(line_item["unit_price"]) +
                "' is not a valid positive number"
            )

    return errors


# ---------------------------------------------------------------------------
# Validation of the EDI this project generates
# ---------------------------------------------------------------------------

def validate_generated_810(edi_text):
    """Re-read a generated 810 and confirm it hangs together.

    This is the "did my own output come out right" check: envelope present,
    ST says 810, the SE segment count is correct, and CTT matches the number
    of IT1 segments.
    """
    errors = []
    result = parse_edi(edi_text)
    segments = result.segments

    required_segment_ids = ["ISA", "GS", "ST", "BIG", "IT1", "TDS", "CTT",
                            "SE", "GE", "IEA"]
    
    for segment_id in required_segment_ids:
        if get_segment(segments, segment_id) is None:
            errors.append("Generated 810 is missing segment: " + segment_id)

    st_segment = get_segment(segments, "ST")
    if st_segment is not None and get_element(st_segment, 1) != "810":
        errors.append("Generated 810 has the wrong ST01 transaction set")

    # ----- SE01 must count every segment from ST through SE -----
    se_segment = get_segment(segments, "SE")
    if st_segment is not None and se_segment is not None:
        counted_segments = 0
        inside_transaction = False

        for segment in segments:
            if segment[0] == "ST":
                inside_transaction = True

            if inside_transaction:
                counted_segments = counted_segments + 1

            if segment[0] == "SE":
                inside_transaction = False

        stated_count = get_element(se_segment, 1)
        if stated_count != str(counted_segments):
            errors.append(
                "SE01 says " + stated_count + " segments but " +
                str(counted_segments) + " were found"
            )

    # ----- CTT01 must match the number of IT1 segments -----
    ctt_segment = get_segment(segments, "CTT")
    it1_segments = get_segments(segments, "IT1")
    if ctt_segment is not None:
        stated_line_count = get_element(ctt_segment, 1)
        if stated_line_count != str(len(it1_segments)):
            errors.append(
                "CTT01 says " + stated_line_count + " line items but " +
                str(len(it1_segments)) + " IT1 segments were found"
            )

    return errors
