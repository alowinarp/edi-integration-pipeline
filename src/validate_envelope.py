"""
validate_envelope.py
-------------
This script is for:
    validating the enveloping segments ISA/GS
    extracting the delimiters from the ISA segment - element separator, sub-delimiter and segment terminator

An EMPTY list means "valid". This avoids exceptions and keeps the calling code
easy to read:

    errors = validate_envelope(content)
    if len(errors) == 0:
        ...
"""
from edi_parser import detect_delimiters, split_segments, get_element, get_segment, get_segments
from edi_exceptions import EDIParseError


def check_isa(raw_content: str) -> None:
    if not raw_content.startswith("ISA"):
        raise EDIParseError("Missing ISA segment")

    if len(raw_content) < 106:
        raise EDIParseError("Incomplete ISA segment")
    
    isa_terminator = raw_content[105]

    if isa_terminator.isalnum():
        raise EDIParseError("Invalid segment terminator")

    return None


def check_required_envelopes(segments: list, errors: list) -> None:

    # ----- required envelope and transaction segments -----
    required_segment_ids = ["GS", "GE", "IEA"]

    for segment_id in required_segment_ids:
        if get_segment(segments, segment_id) is None:
            errors.append("Missing required segment: " + segment_id)

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


def check_control_numbers(segments: list, errors: list) -> None:

    isa_segment = get_segment(segments, "ISA")
    gs_segment = get_segment(segments, "GS")
    iea_segment = get_segment(segments, "IEA")
    ge_segment = get_segment(segments, "GE")

    # Check Interchange Control Numbers (ISA13 vs IEA02)
    if isa_segment is not None and iea_segment is not None:
        isa13 = get_element(isa_segment,13)
        iea02 = get_element(iea_segment,2)
        if isa13 != iea02:
            errors.append(f"ISA13 control number ({isa13}) does not match IEA02 ({iea02}).")

    # Check Functional Group Control Numbers (GS06 vs GE02)
    if gs_segment is not None and ge_segment is not None:
        gs06 = get_element(gs_segment,6)
        ge02 = get_element(ge_segment,2)
        if gs06 != ge02:
            errors.append(f"GS06 control number ({gs06}) does not match GE02 ({ge02}).")

    return None


def check_group_count(segments: list, errors: list) -> None:

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


def check_transaction_count(segments: list, errors: list) -> None:

    st_segment = get_segment(segments, "ST")
    ge_segment = get_segment(segments, "GE")

    if ge_segment is not None and st_segment is not None:
        ge01 = get_element(ge_segment, 1)

        if not ge01.isdigit():
            errors.append(f"GE01 value '{ge01}' is invalid (expected a numeric count).")
            return None

        expected_st_count = int(ge01)
        actual_st_count = len(get_segments(segments, "ST"))

        #Compare counts
        if actual_st_count != expected_st_count:
            errors.append(f"Transaction set count mismatch: GE01 is {expected_st_count} vs ST segment(s)is {actual_st_count}.")

    return None
