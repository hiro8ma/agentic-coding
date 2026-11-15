"""送料の判定のテスト。

環境変数 SHIPPING_IMPL に shipping_mutant を渡すと、税抜で判定する変異に対して流す。
"""

from __future__ import annotations

import importlib
import os
import unittest


def is_free_shipping(total_excluding_tax: int) -> bool:
    impl = importlib.import_module(os.environ.get("SHIPPING_IMPL", "shipping"))
    return impl.is_free_shipping(total_excluding_tax)


class FreeShippingTest(unittest.TestCase):
    def test_free_from_tax_included_5000(self) -> None:
        """SHIP-1 税抜4,546円は税込5,000円で無料、税抜4,545円は税込4,999円で有料"""
        self.assertTrue(is_free_shipping(4546), "税込5,000円は送料無料")
        self.assertFalse(is_free_shipping(4545), "税込4,999円は送料を取る")

    def test_free_for_large_order(self) -> None:
        """SHIP-1 税抜10,000円は税込11,000円で無料"""
        self.assertTrue(is_free_shipping(10000), "税込11,000円は送料無料")


if __name__ == "__main__":
    unittest.main()
