"""Shopping cart calculator with intentionally broken calculations."""


def calculate_total(items, discount_percent=0, tax_percent=0):
    if not 0 <= discount_percent <= 100:
        raise ValueError("discount_percent must be between 0 and 100")
    if tax_percent < 0:
        raise ValueError("tax_percent must be non-negative")

    subtotal = 0
    for item in items:
        price = item["price"]
        quantity = item["quantity"]
        if price < 0:
            raise ValueError("price must be non-negative")
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("quantity must be a positive integer")
        subtotal += price * quantity

    discounted = subtotal * (1 - discount_percent / 100)
    total = discounted * (1 + tax_percent / 100)
    return round(total, 2)
