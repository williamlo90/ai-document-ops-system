from decimal import Decimal


def estimate_cost(input_units: int, output_units: int, *, input_rate: Decimal, output_rate: Decimal) -> Decimal:
    return (Decimal(input_units) * input_rate + Decimal(output_units) * output_rate).quantize(Decimal("0.000001"))
