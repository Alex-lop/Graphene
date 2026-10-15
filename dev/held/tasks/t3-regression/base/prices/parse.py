"""Prices as written on receipts, to (currency, cents)."""

SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}


def parse_price(text):
    """'$12.50' -> ('USD', 1250). A leading '-' is a refund: '-$3.00' -> ('USD', -300)."""
    text = text.strip()
    sign = 1
    if text.startswith("-"):
        sign, text = -1, text[1:]
    return SYMBOLS[text[0]], sign * round(float(text[1:]) * 100)
