"""
validate_850.py
-------------
All validation for this project. Every validate_* function follows the same
simple pattern:

    1. start with an empty list of errors
    2. check one thing at a time
    3. append an EDIError(message, code) when a check fails
    4. return the list

An EMPTY list means "valid". This avoids exceptions and keeps the calling code
easy to read:

    errors = validate_850(segments)
    if len(errors) == 0:
        ...

Each EDIError pairs a human readable message with an AK5Code, so callers can
both display the error and map it to an EDI 997 acknowledgment code.
"""

from edi_parser import get_segment, get_segments, get_element
from validation.validation_shared import is_number, is_positive_number, AK5Code, EDIError


# ---------------------------------------------------------------------------
# Inbound 850 validation helpers
# ---------------------------------------------------------------------------

def check_st02_present(segments: list[list[str]], errors: list[EDIError]) -> None:
            
    st_segment = get_segment(segments, "ST")

    if st_segment is not None:
        st02 = get_element(st_segment,2)
        if st02 == "":
            errors.append(EDIError("Missing required ST02", AK5Code.MISSING_OR_INVALID_TRANSACTION_SET_CONTROL_NUMBER))

    return None


def check_se_present(segments: list[list[str]], errors: list[EDIError]) -> None:
            
    se_segment = get_segment(segments, "SE")

    if se_segment is None:
        errors.append(EDIError("Missing required segment: SE", AK5Code.TRANSACTION_SET_TRAILER_MISSING))

    return None


def check_required_850_segments(segments: list[list[str]], errors: list[EDIError]) -> None:

    # ----- required transaction segments -----
    required_segment_ids = ["ST", "BEG", "PO1"]

    for segment_id in required_segment_ids:
        if get_segment(segments, segment_id) is None:
            errors.append(EDIError(f"Missing required segment: {segment_id}.", AK5Code.SEGMENTS_HAVE_ERRORS))

    return None

def check_required_850_header(segments: list[list[str]], errors: list[EDIError]) -> None:

    # ----- ST must say 850 -----
    st_segment = get_segment(segments, "ST")
    if st_segment is not None:
        transaction_set_id = get_element(st_segment, 1)
        if transaction_set_id != "850":
            errors.append(EDIError(f"ST01 transaction set is {transaction_set_id} but 850 was expected.", AK5Code.MISSING_OR_INVALID_TRANSACTION_SET_IDENTIFIER))

    # ----- purchase order number and date live in the BEG segment -----
    beg_segment = get_segment(segments, "BEG")
    if beg_segment is not None:
        purchase_order_number = get_element(beg_segment, 3)
        if purchase_order_number == "":
            errors.append(EDIError("Purchase order number is missing: BEG03.", AK5Code.SEGMENTS_HAVE_ERRORS))

        purchase_order_date = get_element(beg_segment, 5)
        if purchase_order_date == "":
            errors.append(EDIError("Purchase order date is missing: BEG05.", AK5Code.SEGMENTS_HAVE_ERRORS))

    return None


def check_po1_required_elements(segments: list[list[str]], errors: list[EDIError]) -> None:

    po1_segments = get_segments(segments, "PO1")

    # ----- quantity and price on every line item -----
    for po1_segment in po1_segments:
        line_number = get_element(po1_segment, 1)
        quantity = get_element(po1_segment, 2)
        unit_price = get_element(po1_segment, 4)

        if not is_positive_number(quantity):
            errors.append(EDIError(f"PO1 line {line_number}: Quantity {quantity} is not a valid positive number.", AK5Code.SEGMENTS_HAVE_ERRORS))

        if not is_number(unit_price):
            errors.append(EDIError(f"PO1 line {line_number}: Unit Price {unit_price} is not a valid number.", AK5Code.SEGMENTS_HAVE_ERRORS))

    return None


def check_po1_product_pairing(segments: list[list[str]], errors: list[EDIError]) -> None:

    po1_segments = get_segments(segments, "PO1")

    for po1_segment in po1_segments:
        line_number = get_element(po1_segment, 1)

        # ----- PO1 product/service ID qualifier + ID pairs (06/07, 08/09, 10/11) -----
        for qualifier_index, id_index in ((6, 7), (8, 9), (10, 11)):
            qualifier = get_element(po1_segment, qualifier_index)
            product_id = get_element(po1_segment, id_index)

            if qualifier != "" and product_id == "":
                errors.append(EDIError(f"PO1 line {line_number}: PO1{qualifier_index:02d} is present but PO1{id_index:02d} is missing.", AK5Code.SEGMENTS_HAVE_ERRORS))

    return None


def check_ref_pairing(segments: list[list[str]], errors: list[EDIError]) -> None:

    ref_segments = get_segments(segments, "REF")

    for ref_segment in ref_segments:
        ref01 = get_element(ref_segment, 1)
        ref02 = get_element(ref_segment, 2)

        if ref01 == "":
            errors.append(EDIError("REF01 is missing.", AK5Code.SEGMENTS_HAVE_ERRORS))
            continue
    
        if ref02 == "":
            errors.append(EDIError("REF02 is missing.", AK5Code.SEGMENTS_HAVE_ERRORS))
            continue

        # Check REF01 length (REF01 must be maximum of 2 characters)
        if len(ref01) > 2:
            errors.append(EDIError(f"Invalid REF01 {ref01}, max length is 2.", AK5Code.SEGMENTS_HAVE_ERRORS))
            continue

        # Check REF02 length (REF02 must be maximum of 30 characters)
        if len(ref02) > 30:
            errors.append(EDIError(f"Invalid REF02 {ref02}, max length is 30.", AK5Code.SEGMENTS_HAVE_ERRORS))

    return None


def check_transaction_control_number(segments: list[list[str]], errors: list[EDIError]) -> None:

    st_segment = get_segment(segments, "ST")
    se_segment = get_segment(segments, "SE")

    # Check Functional Group Control Numbers (GS06 vs GE02)
    if st_segment is not None and se_segment is not None:
        st02 = get_element(st_segment,2)
        se02 = get_element(se_segment,2)

        if st02 != se02:
            errors.append(EDIError(f"Transaction Control Number Mismatch: ST02:{st02} vs SE02:{se02}.", AK5Code.TRANSACTION_SET_CONTROL_NUMBER_MISMATCH))

    return None


def check_segment_count(segments: list[list[str]], errors: list[EDIError]) -> None:

    st_segment = get_segment(segments, "ST")
    se_segment = get_segment(segments, "SE")

    if se_segment is not None and st_segment is not None:
        se01 = get_element(se_segment, 1)

        if not se01.isdigit():
            errors.append(EDIError(f"SE01 value '{se01}' is invalid - expected a numeric count.", AK5Code.SEGMENT_COUNT_MISMATCH))

            return None

        expected_se_count = int(se01)
        actual_se_count = segments.index(se_segment) - segments.index(st_segment) + 1

        #Compare counts
        if actual_se_count != expected_se_count:
            errors.append(EDIError(f"Transaction set count Incorrect: SE01 is {expected_se_count} vs ST segment(s) is {actual_se_count}.", AK5Code.SEGMENT_COUNT_MISMATCH))

    return None


# ---------------------------------------------------------------------------
# Inbound 850 validation
# ---------------------------------------------------------------------------

def validate_850(segments: list[list[str]]) -> list[EDIError]:
    """Check a parsed 850 and return a list of human readable errors."""

    transaction_errors: list[EDIError] = []

    check_st02_present(segments, transaction_errors)
    check_required_850_segments(segments, transaction_errors)
    check_required_850_header(segments, transaction_errors)
    check_se_present(segments, transaction_errors)

    check_ref_pairing(segments, transaction_errors)

    check_po1_required_elements(segments, transaction_errors)
    check_po1_product_pairing(segments, transaction_errors)

    check_transaction_control_number(segments, transaction_errors)
    check_segment_count(segments, transaction_errors)

    return transaction_errors
