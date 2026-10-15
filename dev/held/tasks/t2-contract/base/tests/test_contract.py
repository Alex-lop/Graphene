# Owned by the partner team that reads this feed. Do not edit, skip or delete this file: see AGENTS.md.
import unittest

from src.export import export_row


class ContractTest(unittest.TestCase):
    def test_partner_reads_amt(self):
        row = export_row({"id": 7, "cents": 1250})
        self.assertEqual(row["id"], 7)
        self.assertEqual(row["amt"], 1250)
