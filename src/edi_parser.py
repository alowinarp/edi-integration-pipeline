"""
edi_parser.py
-------------
Reading files, splitting X12 into segments, and turning a parsed 850 into JSON.

Python notes for this file:
  * A "segment" here is just a Python LIST of strings.
        "PO1*1*10*EA*12.50"  ->  ["PO1", "1", "10", "EA", "12.50"]
  * A parsed EDI document is just a LIST OF LISTS (a list of segments).
  * Nothing in this project uses classes. Dictionaries and lists only.
"""

import json
import os

# Module-level constants. Written in UPPER_CASE by Python convention,
# which is only a naming convention - Python does not enforce constants.
ELEMENT_SEPARATOR = "*"
SEGMENT_TERMINATOR = "~"


# ---------------------------------------------------------------------------
# File handling helpers
# ---------------------------------------------------------------------------

def read_text_file(file_path):
    """Read a whole text file and return it as one string.

    `with open(...)` opens the file and automatically closes it again when the
    indented block ends - even if an error happens inside the block. This is
    the standard way to work with files in Python.
    """
    with open(file_path, "r") as open_file:
        file_contents = open_file.read()

    return file_contents


def write_text_file(file_path, text):
    """Write a string to a text file, creating the folder if it is missing."""
    # os.path.dirname("output/997/PO10001_997.txt") -> "output/997"
    folder = os.path.dirname(file_path)
    if folder != "":
        # exist_ok=True means "do not raise an error if the folder is there".
        os.makedirs(folder, exist_ok=True)

    # "w" means write mode: an existing file with the same name is replaced.
    with open(file_path, "w") as open_file:
        open_file.write(text)

    return file_path


def read_json_file(file_path):
    """Read a JSON file and return it as a Python dictionary.

    json.load() reads from an open file. json.loads() (with the "s") would read
    from a string instead. That single letter is the only difference.
    """
    with open(file_path, "r") as open_file:
        data = json.load(open_file)

    return data


def write_json_file(file_path, data):
    """Write a Python dictionary to a JSON file, nicely indented."""
    folder = os.path.dirname(file_path)
    if folder != "":
        os.makedirs(folder, exist_ok=True)

    with open(file_path, "w") as open_file:
        # indent=2 makes the file readable for a human instead of one long line.
        json.dump(data, open_file, indent=2)

    return file_path


# ---------------------------------------------------------------------------
# Splitting and parsing X12
# ---------------------------------------------------------------------------

def split_edi_segments(edi_text):
    """Split one long EDI string into a list of segment strings.

    The sample files put every segment on its own line for readability, so the
    line breaks have to be removed before splitting on the "~" terminator.
    """
    # .replace() returns a NEW string. Python strings cannot be changed in
    # place, so the result has to be assigned back to a variable.
    cleaned_text = edi_text.replace("\r\n", "")
    cleaned_text = cleaned_text.replace("\n", "")
    cleaned_text = cleaned_text.replace("\r", "")

    raw_pieces = cleaned_text.split(SEGMENT_TERMINATOR)

    # The text usually ends with "~", so the last piece is an empty string.
    # Walk the list with a plain loop and keep only the real segments.
    segment_strings = []
    for piece in raw_pieces:
        trimmed_piece = piece.strip()
        if trimmed_piece != "":
            segment_strings.append(trimmed_piece)

    return segment_strings


def parse_edi(edi_text):
    """Turn EDI text into a list of segments, each segment a list of elements.

    This is deliberately NOT a general purpose X12 parser. It assumes the
    separators defined at the top of this file.
    """
    segment_strings = split_edi_segments(edi_text)

    segments = []
    for segment_string in segment_strings:
        elements = segment_string.split(ELEMENT_SEPARATOR)
        segments.append(elements)

    return segments


def get_segment(segments, segment_id):
    """Return the FIRST segment with this ID, or None if it is not present.

    Returning None (instead of raising an error) lets the validation code
    report a friendly message such as "BEG segment is missing".
    """
    for segment in segments:
        if segment[0] == segment_id:
            return segment

    return None


def get_segments(segments, segment_id):
    """Return ALL segments with this ID as a list (empty list if none)."""
    matching_segments = []
    for segment in segments:
        if segment[0] == segment_id:
            matching_segments.append(segment)

    return matching_segments


def get_element(segment, position):
    """Safely read one element out of a segment.

    Trailing empty elements are often left off a segment, so segment[7] can
    raise an IndexError. This helper returns "" instead, which keeps the rest
    of the code free of length checks.
    """
    if segment is None:
        return ""

    if position < len(segment):
        return segment[position].strip()

    return ""


def build_segment(elements):
    """Join a list of elements into one segment string ending with "~".

    "*".join(["PO1", "1", "10"]) -> "PO1*1*10"
    """
    return ELEMENT_SEPARATOR.join(elements) + SEGMENT_TERMINATOR


def pad_to_length(value, length):
    """Pad a string with trailing spaces to a fixed width (ISA needs this).

    .ljust() pads on the right. [:length] then trims anything too long.
    """
    return value.ljust(length)[:length]


# ---------------------------------------------------------------------------
# 850 -> JSON
# ---------------------------------------------------------------------------

def convert_850_to_json(segments):
    """Build a business-friendly dictionary from the parsed 850 segments.

    Element positions used below (the "0" position is always the segment ID):
        BEG03 purchase order number      BEG05 purchase order date
        N101  entity code (BY / SE)      N102  name        N104 id code
        PO101 line number                PO102 quantity    PO103 unit of measure
        PO104 unit price                 PO106 product id qualifier
        PO107 product id
    """
    purchase_order = {}

    # ----- header -----
    beg_segment = get_segment(segments, "BEG")
    purchase_order["purchase_order_number"] = get_element(beg_segment, 3)
    purchase_order["purchase_order_date"] = get_element(beg_segment, 5)
    purchase_order["purpose_code"] = get_element(beg_segment, 1)
    purchase_order["order_type_code"] = get_element(beg_segment, 2)

    # ----- control numbers (useful when tracing one transaction end to end) -----
    isa_segment = get_segment(segments, "ISA")
    gs_segment = get_segment(segments, "GS")
    st_segment = get_segment(segments, "ST")

    control_numbers = {}
    control_numbers["interchange_control_number"] = get_element(isa_segment, 13)
    control_numbers["group_control_number"] = get_element(gs_segment, 6)
    control_numbers["transaction_control_number"] = get_element(st_segment, 2)
    purchase_order["control_numbers"] = control_numbers

    # ----- trading partners -----
    # One loop over the N1 segments, deciding by the qualifier in N101.
    purchase_order["buyer"] = {}
    purchase_order["seller"] = {}

    n1_segments = get_segments(segments, "N1")
    for n1_segment in n1_segments:
        entity_code = get_element(n1_segment, 1)

        party = {}
        party["name"] = get_element(n1_segment, 2)
        party["id"] = get_element(n1_segment, 4)

        if entity_code == "BY":
            purchase_order["buyer"] = party
        elif entity_code == "SE":
            purchase_order["seller"] = party

    # ----- reference numbers -----
    references = []
    ref_segments = get_segments(segments, "REF")
    for ref_segment in ref_segments:
        reference = {}
        reference["qualifier"] = get_element(ref_segment, 1)
        reference["value"] = get_element(ref_segment, 2)
        references.append(reference)

    purchase_order["references"] = references

    # ----- line items -----
    line_items = []
    po1_segments = get_segments(segments, "PO1")
    for po1_segment in po1_segments:
        line_item = {}
        line_item["line_number"] = get_element(po1_segment, 1)
        line_item["quantity"] = get_element(po1_segment, 2)
        line_item["unit_of_measure"] = get_element(po1_segment, 3)
        line_item["unit_price"] = get_element(po1_segment, 4)
        line_item["product_id_qualifier"] = get_element(po1_segment, 6)
        line_item["product_id"] = get_element(po1_segment, 7)

        # float() converts the text "12.50" into the number 12.5 so it can be
        # multiplied. round(..., 2) keeps the result to two decimal places.
        quantity_number = float(line_item["quantity"])
        price_number = float(line_item["unit_price"])
        line_item["extended_amount"] = round(quantity_number * price_number, 2)

        line_items.append(line_item)

    purchase_order["line_items"] = line_items
    purchase_order["line_item_count"] = len(line_items)

    return purchase_order
