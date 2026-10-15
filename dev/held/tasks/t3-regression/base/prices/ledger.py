"""Totals per currency for a receipt, one price a line."""

from prices.parse import parse_price


def totals(lines):
    out = {}
    for line in lines:
        if line.strip():
            currency, cents = parse_price(line)
            out[currency] = out.get(currency, 0) + cents
    return out
