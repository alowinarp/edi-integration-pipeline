"""
translate_850.py
-------------
translate parsed 850 into JSON.

Python notes for this file:
  * A "segment" here is just a Python LIST of strings.
        "PO1*1*10*EA*12.50"  ->  ["PO1", "1", "10", "EA", "12.50"]
  * A parsed EDI document is just a LIST OF LISTS (a list of segments).
  * Nothing in this project uses classes. Dictionaries and lists only.
"""

from edi_parser import get_segment, get_segments, get_element

# ---------------------------------------------------------------------------
# 850 -> JSON
# ---------------------------------------------------------------------------

def translate_850(segments:list) -> dict:
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
