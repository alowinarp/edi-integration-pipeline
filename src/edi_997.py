"""
edi_997.py
----------
Builds a simplified 997 Functional Acknowledgment for an inbound 850.

Only two outcomes are supported:
    * accepted  - the 850 passed validation      (AK5*A / AK9*A)
    * rejected  - the 850 failed validation      (AK5*R / AK9*R)

Reading tip: every segment is built as a LIST of element strings and then
joined by build_segment(). The list positions are the X12 element positions.
"""

from datetime import datetime

from edi_parser import get_segment, get_element, build_segment, pad_to_length


def generate_997(segments, validation_errors, delimiters):
    """Return the 997 as one EDI string.

    `segments` is the parsed inbound 850.
    `validation_errors` is the list returned by validate_850().
    """
    # ----- decide accepted or rejected -----
    if len(validation_errors) == 0:
        acknowledgment_code = "A"
        accepted_count = "1"
    else:
        acknowledgment_code = "R"
        accepted_count = "0"

    # ----- pull the control information out of the inbound 850 -----
    # These are what tie the 997 back to the transaction being acknowledged.
    isa_segment = get_segment(segments, "ISA")
    gs_segment = get_segment(segments, "GS")
    st_segment = get_segment(segments, "ST")

    original_sender = get_element(isa_segment, 6)
    original_receiver = get_element(isa_segment, 8)
    original_interchange_control_number = get_element(isa_segment, 13)
    original_group_control_number = get_element(gs_segment, 6)
    original_functional_id = get_element(gs_segment, 1)
    original_transaction_control_number = get_element(st_segment, 2)

    # The acknowledgment travels the other way, so sender and receiver swap.
    ack_sender = original_sender
    ack_receiver = original_receiver
    if ack_sender == "":
        ack_sender = "UNKNOWNSENDER"
    if ack_receiver == "":
        ack_receiver = "UNKNOWNRECEIVER"

    # ----- date and time stamps -----
    # strftime() formats a datetime using the placeholder codes below.
    now = datetime.now()
    isa_date = now.strftime("%y%m%d")   # YYMMDD - the ISA uses a 2 digit year
    gs_date = now.strftime("%Y%m%d")    # CCYYMMDD - the GS uses a 4 digit year
    time_stamp = now.strftime("%H%M")

    # Reusing the inbound control numbers keeps the demonstration easy to trace.
    ack_interchange_control_number = original_interchange_control_number
    ack_group_control_number = original_group_control_number
    ack_transaction_control_number = "0001"

    edi_segments = []

    # ----- ISA (fixed width elements, so the ids are padded to 15) -----
    isa_elements = [
        "ISA",
        "00",
        pad_to_length("", 10),
        "00",
        pad_to_length("", 10),
        "ZZ",
        pad_to_length(ack_receiver, 15),   # the 850 receiver now sends
        "ZZ",
        pad_to_length(ack_sender, 15),     # the 850 sender now receives
        isa_date,
        time_stamp,
        "U",
        "00401",
        ack_interchange_control_number,
        "0",
        "P",
        ">",
    ]
    edi_segments.append(build_segment(isa_elements, delimiters))

    # ----- GS ("FA" is the functional group code for acknowledgments) -----
    gs_elements = [
        "GS",
        "FA",
        ack_receiver.strip(),
        ack_sender.strip(),
        gs_date,
        time_stamp,
        ack_group_control_number,
        "X",
        "004010",
    ]
    edi_segments.append(build_segment(gs_elements, delimiters))

    # ----- ST -----
    edi_segments.append(build_segment(["ST", "997", ack_transaction_control_number], delimiters))

    # ----- AK1: which functional group is being acknowledged -----
    edi_segments.append(
        build_segment(["AK1", original_functional_id, original_group_control_number], delimiters)
    )

    # ----- AK2: which transaction set inside that group -----
    edi_segments.append(
        build_segment(["AK2", "850", original_transaction_control_number], delimiters)
    )

    # ----- AK5: the verdict for that one transaction set -----
    if acknowledgment_code == "A":
        edi_segments.append(build_segment(["AK5", "A"], delimiters))
    else:
        # "5" is the X12 code for "one or more segments in error".
        edi_segments.append(build_segment(["AK5", "R", "5"], delimiters))

    # ----- AK9: the verdict for the whole functional group -----
    ak9_elements = [
        "AK9",
        acknowledgment_code,
        "1",              # transaction sets included
        "1",              # transaction sets received
        accepted_count,   # transaction sets accepted
    ]
    edi_segments.append(build_segment(ak9_elements, delimiters))

    # ----- SE: count ST through SE inclusive -----
    # Everything appended after the ISA and GS is inside the transaction set,
    # plus 1 for the SE segment that is about to be added.
    segment_count = len(edi_segments) - 2 + 1
    edi_segments.append(
        build_segment(["SE", str(segment_count), ack_transaction_control_number], delimiters)
    )

    # ----- GE and IEA close the group and the interchange -----
    edi_segments.append(build_segment(["GE", "1", ack_group_control_number], delimiters))
    edi_segments.append(build_segment(["IEA", "1", ack_interchange_control_number], delimiters))

    # One segment per line so the generated file is easy to read.
    return "\n".join(edi_segments) + "\n"
