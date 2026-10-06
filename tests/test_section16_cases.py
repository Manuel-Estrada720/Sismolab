"""The six mandatory cases of section 16 (see scripts/section16_cases.py)."""

import unittest

from scripts.section16_cases import ALL_CASES


class Section16Tests(unittest.TestCase):
    def test_every_case(self):
        for function in ALL_CASES:
            case = function()
            with self.subTest(case=case.number):
                failed = [item for item in case.checks if not item["ok"]]
                self.assertEqual(failed, [], "Caso %d: %s" % (case.number, case.title))
                self.assertGreater(len(case.checks), 5)


if __name__ == "__main__":
    unittest.main()
