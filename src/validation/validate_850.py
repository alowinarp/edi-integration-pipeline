"""
validate_850.py
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

from edi_parser import get_segment, get_segments, get_element
from validation.validation_shared import is_number, is_positive_number

# ---------------------------------------------------------------------------
# Inbound 850 validation helpers
# ---------------------------------------------------------------------------

def check_required_850_segments(segments: list, errors: list) -> None:

    # ----- required transaction segments -----
    required_segment_ids = ["ST", "BEG", "PO1","SE"]

    for segment_id in required_segment_ids:
        if get_segment(segments, segment_id) is None:
            errors.append("Missing required segment: " + segment_id)
    
    return None


def check_required_850_header(segments: list, errors: list) -> None:

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

    return None


def check_po1_required_elements(segments: list, errors: list) -> None:

    po1_segments = get_segments(segments, "PO1")

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

    return None


def check_po1_product_pairing(segments: list, errors: list) -> None:

    po1_segments = get_segments(segments, "PO1")

    for po1_segment in po1_segments:
        line_number = get_element(po1_segment, 1)

        # ----- PO1 product/service ID qualifier + ID pairs (06/07, 08/09, 10/11) -----
        for qualifier_index, id_index in ((6, 7), (8, 9), (10, 11)):
            qualifier = get_element(po1_segment, qualifier_index)
            product_id = get_element(po1_segment, id_index)

            if qualifier != "" and product_id == "":
                errors.append(
                    f"PO1 line {line_number}: PO1{qualifier_index:02d} is present "
                    f"but PO1{id_index:02d} is missing"
                )

    return None


def check_ref_pairing(segments: list, errors: list) -> None:

    ref_segments = get_segments(segments, "REF")

    for ref_segment in ref_segments:
        ref01 = get_element(ref_segment, 1)
        ref02 = get_element(ref_segment, 2)

        if ref01 == "":
            errors.append("REF01 is missing")
            continue
    
        if ref02 == "":
            errors.append("REF02 is missing")
            continue

        # Check REF01 length (REF01 must be maximum of 2 characters)
        if len(ref01) > 2:
            errors.append(f"Invalid REF01, max length is 2")
            continue

        # Check REF02 length (REF02 must be maximum of 30 characters)
        if len(ref02) > 30:
            errors.append(f"Invalid REF02, max length is 30")

    return None


def check_segment_count(segments: list, errors: list) -> None:

    st_segment = get_segment(segments, "ST")
    se_segment = get_segment(segments, "SE")

    if se_segment is not None and st_segment is not None:
        se01 = get_element(se_segment, 1)

        if not se01.isdigit():
            errors.append(f"SE01 value '{se01}' is invalid (expected a numeric count).")
            return None

        expected_se_count = int(se01)
        actual_se_count = segments.index(se_segment) - segments.index(st_segment) + 1

        #Compare counts
        if actual_se_count != expected_se_count:
            errors.append(f"Transaction set count Incorrect: SE01 is {expected_se_count} vs ST segment(s)is {actual_se_count}.")

    return None



# ---------------------------------------------------------------------------
# Inbound 850 validation
# ---------------------------------------------------------------------------

def validate_850(segments:list) -> list[str]:
    """Check a parsed 850 and return a list of human readable errors."""

    transaction_errors: list[str] = []

    check_required_850_segments(segments, transaction_errors)
    check_required_850_header(segments, transaction_errors)

    check_ref_pairing(segments, transaction_errors)

    check_po1_required_elements(segments, transaction_errors)
    check_po1_product_pairing(segments, transaction_errors)
    
    check_segment_count(segments, transaction_errors)

    return transaction_errors
