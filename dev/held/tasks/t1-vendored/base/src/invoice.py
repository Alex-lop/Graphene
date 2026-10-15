"""Invoice totals. A line is (quantity, unit price in dollars as a string)."""

from vendor.money import fmt, to_cents


def total_cents(lines):
    return to_cents(sum(qty * float(price) for qty, price in lines))


def total(lines):
    return fmt(total_cents(lines))
