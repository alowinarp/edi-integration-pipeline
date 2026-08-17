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


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

def is_number(value):
    """Return True if the text can be converted to a number.

    try/except is the normal Python way to test a conversion. float("ABC")
    raises ValueError, which is caught here and turned into False.
    """
    try:
        float(value)
        return True
    except ValueError:
        return False


def is_positive_number(value):
    """Return True if the text is a number greater than zero."""
    if not is_number(value):
        return False

    if float(value) <= 0:
        return False

    return True


def has_value(dictionary, key):
    """Return True if the key exists in the dictionary and is not empty."""
    if key not in dictionary:
        return False

    value = dictionary[key]
    if value is None:
        return False

    # A string of spaces counts as empty. str() protects against numbers.
    if str(value).strip() == "":
        return False

    return True


# ---------------------------------------------------------------------------
# Inbound 850 validation
# ---------------------------------------------------------------------------

def validate_850(segments):
    """Check a parsed 850 and return a list of human readable errors."""
    errors = []

    # ----- required envelope and transaction segments -----
    required_segment_ids = ["ISA", "GS", "ST", "BEG", "SE", "GE", "IEA"]
    for segment_id in required_segment_ids:
        if get_segment(segments, segment_id) is None:
            errors.append("Missing required segment: " + segment_id)

    # ----- ST must say 850 -----
    st_segment = get_segment(segments, "ST")
    if st_segment is not None:
        transaction_set_id = get_element(st_segment, 1)
        if transaction_set_id != "850":
            errors.append(
                "ST01 transaction set is '" + transaction_set_id +
                "' but 850 was expected"
            )

    # ----- purchase order number and date live in the BEG segment -----
    beg_segment = get_segment(segments, "BEG")
    if beg_segment is not None:
        purchase_order_number = get_element(beg_segment, 3)
        if purchase_order_number == "":
            errors.append("Purchase order number is missing (BEG03)")

        purchase_order_date = get_element(beg_segment, 5)
        if purchase_order_date == "":
            errors.append("Purchase order date is missing (BEG05)")

    # ----- at least one line item -----
    po1_segments = get_segments(segments, "PO1")
    if len(po1_segments) == 0:
        errors.append("No PO1 line items found - at least one is required")

    # ----- quantity and price on every line item -----
    for po1_segment in po1_segments:
        line_number = get_element(po1_segment, 1)
        quantity = get_element(po1_segment, 2)
        unit_price = get_element(po1_segment, 4)

        if not is_positive_number(quantity):
            errors.append(
                "PO1 line " + line_number + ": quantity '" + quantity +
                "' is not a valid positive number"
            )

        if not is_number(unit_price):
            errors.append(
                "PO1 line " + line_number + ": unit price '" + unit_price +
                "' is not a valid number"
            )

    return errors


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
    segments = parse_edi(edi_text)

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
