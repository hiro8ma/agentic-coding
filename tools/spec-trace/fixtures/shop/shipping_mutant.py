"""送料の判定の変異。SHIP-1 を読み違え、税抜の合計で判定する。"""

FREE_SHIPPING_THRESHOLD = 5000


def is_free_shipping(total_excluding_tax: int) -> bool:
    return total_excluding_tax >= FREE_SHIPPING_THRESHOLD
