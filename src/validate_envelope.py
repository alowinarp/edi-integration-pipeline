"""
validate_envelope.py
-------------
This script is for:
    validating the enveloping segments ISA/GS/GE/IEA enveloping structure of a parsed EDI transmission,
split by acknowledgment tier:

    Interchange tier (ISA/IEA) — unacknowledgeable. A failure here means no
    reliable functional group can be identified, so no AK1 can be built.
    Callers should treat interchange_errors as fatal: reject the envelope,
    skip 997 generation, return HTTP 400.

    Group tier (GS/GE) — acknowledgeable. GS presence is confirmed before
    these checks run, so an AK1 can be built even when a group-tier check
    fails. Callers should route group_errors into a negative 997 (AK9 with
    the relevant AK905 code) rather than rejecting outright.

Note: ISA structural validity (presence, length, terminator) is checked
earlier in edi_parser, since delimiter extraction depends on it — this
module assumes segments have already been successfully tokenized.

    result = validate_envelope(segments)
    if result.interchange_errors:
        # unacknowledgeable — envelope_rejected, no 997, HTTP 400
        ...
    elif result.group_errors:
        # acknowledgeable — negative 997 via generate_997()
        ...
    else:
        # clean — proceed to transaction-tier validation
        ...
"""

from datetime import datetime
from edi_parser import get_element, get_segment, get_segments
from typing import NamedTuple
from validation.validation_shared import AK905Code, EDIError


class EnvelopeValidationResult(NamedTuple):
    interchange_errors: list[str]
    group_errors: list[EDIError]


# ---------------------------------------------------------------------------
# Interchange Validation helpers
# ---------------------------------------------------------------------------
def check_required_envelopes(segments: list, errors: list) -> None:

    # ----- required envelope and transaction segments -----
    required_segment_ids = ["GS", "IEA"]

    for segment_id in required_segment_ids:
        if get_segment(segments, segment_id) is None:
            errors.append("Missing required segment: " + segment_id)

    return None


def check_interchange_control_numbers(segments: list, errors: list) -> None:

    isa_segment = get_segment(segments, "ISA")
    iea_segment = get_segment(segments, "IEA")

    # Check Interchange Control Numbers (ISA13 vs IEA02)
    if isa_segment is not None and iea_segment is not None:
        isa13 = get_element(isa_segment,13)
        iea02 = get_element(iea_segment,2)
        if isa13 != iea02:
            errors.append(f"Interchange Control Number Mismatch: ISA13:{isa13} vs IEA02:{iea02}.")

    return None


def check_gs04(segments: list, errors: list) -> None:

    gs_segment = get_segment(segments, "GS")

    if gs_segment is None:
        return None

    gs04_date = get_element(gs_segment,4)

    if gs04_date == "":
        errors.append("GS04 date is missing")
        return None
    
    # Perform length or format validation (X12 GS04 must be 8 digits: CCYYMMDD)
    if len(gs04_date) != 8 or not gs04_date.isdigit():
        errors.append(f"Invalid GS04 date format: {gs04_date}. Expected CCYYMMDD.")
        return None
    
    #Perform calendar date validation using datetime.strptime
    try:
        datetime.strptime(gs04_date, "%Y%m%d")
    except ValueError:
        errors.append(f"Invalid GS04 calendar date: '{gs04_date}'. Date does not exist.")

    return None


def check_interchange_group_count(segments: list, errors: list) -> None:

    gs_segment = get_segment(segments, "GS")
    iea_segment = get_segment(segments, "IEA")

    if iea_segment is not None and gs_segment is not None:
        iea01 = get_element(iea_segment, 1)

        if not iea01.isdigit():
            errors.append(f"IEA01 value '{iea01}' is invalid (expected a numeric count).")
            return None

        expected_gs_count = int(iea01)
        actual_gs_count = len(get_segments(segments, "GS"))

        #Compare counts
        if actual_gs_count != expected_gs_count:
            errors.append(f"Group Control count mismatch: IEA01 is {expected_gs_count} vs GS segment(s) count is {actual_gs_count}.")

    return None


# ---------------------------------------------------------------------------
# Group Validation helpers
# ---------------------------------------------------------------------------

def check_ge_present(segments: list, errors: list) -> None:
            
    ge_segment = get_segment(segments, "GE")
    
    if ge_segment is None:
        errors.append(EDIError("Missing required segment: GE", AK905Code.FUNCTIONAL_GROUP_TRAILER_MISSING))
        return None
    
    return None


def check_group_control_number(segments: list, errors: list) -> None:

    gs_segment = get_segment(segments, "GS")
    ge_segment = get_segment(segments, "GE")

    # Check Functional Group Control Numbers (GS06 vs GE02)
    if gs_segment is not None and ge_segment is not None:
        gs06 = get_element(gs_segment,6)
        ge02 = get_element(ge_segment,2)

        if gs06 != ge02:
            errors.append(EDIError(f"Group Control Number Mismatch: GS06:{gs06} vs GE02:{ge02}.", AK905Code.GROUP_CONTROL_NUMBER_MISMATCH))

    return None


def check_transaction_count(segments: list, errors: list) -> None:

    st_segment = get_segment(segments, "ST")
    ge_segment = get_segment(segments, "GE")

    if ge_segment is not None and st_segment is not None:
        ge01 = get_element(ge_segment, 1)

        if not ge01.isdigit():
            errors.append(EDIError(f"Invalid Format: GE01 is '{ge01}' - must be a number.", AK905Code.TRANSACTION_COUNT_MISMATCH))
            return None

        expected_st_count = int(ge01)
        actual_st_count = len(get_segments(segments, "ST"))

        #Compare counts
        if actual_st_count != expected_st_count:
            errors.append(EDIError(f"Transaction set count mismatch: GE01 is {expected_st_count} vs ST segment(s) is {actual_st_count}.", AK905Code.TRANSACTION_COUNT_MISMATCH))

    return None


def validate_envelope(segment_string: list) -> EnvelopeValidationResult:

    interchange_errors: list[str] = []
    group_errors: list[EDIError] = []

    check_required_envelopes(segment_string, interchange_errors)
    check_interchange_control_numbers(segment_string, interchange_errors)
    check_gs04(segment_string, interchange_errors)
    check_interchange_group_count(segment_string, interchange_errors)

    if interchange_errors:
        return EnvelopeValidationResult(interchange_errors, [])

    # ----- group tier: GS/GE checks, only reached if GS confirmed present -----
    check_ge_present(segment_string, group_errors)
    check_group_control_number(segment_string, group_errors)
    check_transaction_count(segment_string, group_errors)

    return EnvelopeValidationResult(
        interchange_errors=interchange_errors,
        group_errors=group_errors
    )