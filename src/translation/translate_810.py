"""
translate_810.py
----------
Turns an invoice dictionary (from JSON) into a simplified X12 810 Invoice.

Every segment is built in one clearly marked block below, in the order it
appears in the finished document:

    ISA -> GS -> ST -> BIG -> REF -> N1 (buyer) -> N1 (seller)
        -> IT1 (one per line item) -> TDS -> CTT -> SE -> GE -> IEA
"""

from datetime import datetime
from edi_parser import Delimiters, DEFAULT_DELIMITERS, build_segment, pad_to_length


# ---------------------------------------------------------------------------
# Build Invoice helpers
# ---------------------------------------------------------------------------

def calculate_line_amount(line_item: dict) -> float:
    """quantity x unit price, rounded to two decimals."""
    quantity = float(line_item["quantity"])
    unit_price = float(line_item["unit_price"])

    return round(quantity * unit_price, 2)


def calculate_invoice_total(invoice: dict) -> float:
    """Add up every line item to get the invoice total."""
    total = 0.0

    for line_item in invoice["line_items"]:
        total = total + calculate_line_amount(line_item)

    return round(total, 2)


def make_control_number(invoice_number: str) -> str:
    """Derive a numeric control number from the invoice number.

    A real system would keep a counter somewhere. Deriving the number from the
    invoice keeps this project free of databases and makes the output
    predictable: "INV10001" -> "10001".
    """
    digits = ""
    for character in invoice_number:
        if character.isdigit():
            digits = digits + character

    if digits == "":
        digits = "1"

    return digits


# ---------------------------------------------------------------------------
# Build Invoice
# ---------------------------------------------------------------------------

def translate_810(invoice: dict, delimiters: Delimiters = DEFAULT_DELIMITERS) -> str:
    """Return the X12 810 for this invoice dictionary, as one EDI string."""
    invoice_number = invoice["invoice_number"]
    invoice_date = invoice["invoice_date"]
    purchase_order_number = invoice["purchase_order_number"]
    buyer = invoice["buyer"]
    seller = invoice["seller"]
    line_items = invoice["line_items"]

    # ----- control numbers -----
    control_number = make_control_number(invoice_number)
    # .zfill() pads on the left with zeros: "10001" -> "000010001"
    interchange_control_number = control_number.zfill(9)
    group_control_number = control_number
    transaction_control_number = control_number[-4:].zfill(4)

    # ----- date and time stamps -----
    now = datetime.now()
    isa_date = now.strftime("%y%m%d")
    gs_date = now.strftime("%Y%m%d")
    time_stamp = now.strftime("%H%M")

    # The invoice is sent by the seller to the buyer.
    sender_id = seller["id"]
    receiver_id = buyer["id"]

    edi_segments = []

    # ----- ISA (fixed width, so the ids are padded to exactly 15) -----
    isa_elements = [
        "ISA",
        "00",
        pad_to_length("", 10),
        "00",
        pad_to_length("", 10),
        "ZZ",
        pad_to_length(sender_id, 15),
        "ZZ",
        pad_to_length(receiver_id, 15),
        isa_date,
        time_stamp,
        "U",
        "00401",
        interchange_control_number,
        "0",
        "P",
        ">",
    ]
    edi_segments.append(build_segment(isa_elements, delimiters))

    # ----- GS ("IN" is the functional group code for invoices) -----
    gs_elements = [
        "GS",
        "IN",
        sender_id,
        receiver_id,
        gs_date,
        time_stamp,
        group_control_number,
        "X",
        "004010",
    ]
    edi_segments.append(build_segment(gs_elements, delimiters))

    # ----- ST -----
    edi_segments.append(build_segment(["ST", "810", transaction_control_number], delimiters))

    # ----- BIG: invoice date/number and the purchase order it bills against -----
    big_elements = [
        "BIG",
        invoice_date,             # BIG01 invoice date
        invoice_number,           # BIG02 invoice number
        "",                       # BIG03 purchase order date (not tracked here)
        purchase_order_number,    # BIG04 purchase order number
    ]
    edi_segments.append(build_segment(big_elements, delimiters))

    # ----- REF: seller's invoice number ("IV") -----
    edi_segments.append(build_segment(["REF", "IV", invoice_number], delimiters))

    # ----- N1: buyer then seller -----
    buyer_elements = ["N1", "BY", buyer["name"], "92", buyer["id"]]
    edi_segments.append(build_segment(buyer_elements, delimiters))

    seller_elements = ["N1", "SE", seller["name"], "92", seller["id"]]
    edi_segments.append(build_segment(seller_elements, delimiters))

    # ----- IT1: one segment per invoice line -----
    for line_item in line_items:
        it1_elements = [
            "IT1",
            str(line_item["line_number"]),      # IT101 line number
            str(line_item["quantity"]),         # IT102 quantity
            str(line_item["unit_of_measure"]),  # IT103 unit of measure
            str(line_item["unit_price"]),       # IT104 unit price
            "",                                 # IT105 basis of unit price
            "BP",                               # IT106 product id qualifier
            str(line_item["product_id"]),       # IT107 product id
        ]
        edi_segments.append(build_segment(it1_elements, delimiters))

    # ----- TDS: total amount, sent with an implied decimal (cents) -----
    invoice_total = calculate_invoice_total(invoice)
    # 350.0 -> 35000 -> "35000". round() before int() avoids float rounding
    # surprises such as 34999.999999999996.
    total_in_cents = int(round(invoice_total * 100))
    edi_segments.append(build_segment(["TDS", str(total_in_cents)], delimiters))

    # ----- CTT: how many line items -----
    edi_segments.append(build_segment(["CTT", str(len(line_items))], delimiters))

    # ----- SE: count ST through SE inclusive -----
    # ISA and GS sit outside the transaction set, so subtract 2, then add 1
    # for the SE segment being created right now.
    segment_count = len(edi_segments) - 2 + 1
    edi_segments.append(
        build_segment(["SE", str(segment_count), transaction_control_number], delimiters)
    )

    # ----- GE and IEA close the group and the interchange -----
    edi_segments.append(build_segment(["GE", "1", group_control_number], delimiters))
    edi_segments.append(build_segment(["IEA", "1", interchange_control_number], delimiters))

    return "".join(edi_segments)