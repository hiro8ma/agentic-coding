"""送料の判定。SHIP-1 のとおり、税込の合計で判定する。"""

FREE_SHIPPING_THRESHOLD = 5000
TAX_INCLUDED_PERCENT = 110


def tax_included(total_excluding_tax: int) -> int:
    return total_excluding_tax * TAX_INCLUDED_PERCENT // 100


def is_free_shipping(total_excluding_tax: int) -> bool:
    return tax_included(total_excluding_tax) >= FREE_SHIPPING_THRESHOLD
