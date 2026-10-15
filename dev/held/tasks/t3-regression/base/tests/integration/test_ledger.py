import unittest

from prices.ledger import totals


class LedgerTest(unittest.TestCase):
    def test_refunds_come_off_the_total(self):
        receipt = ["$12.50", "-$2.50", "", "€1.00", "-€0.25"]
        self.assertEqual(totals(receipt), {"USD": 1000, "EUR": 75})
