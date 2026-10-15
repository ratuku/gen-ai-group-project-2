def _aggregate_by_region(rows):
    """Return a dictionary mapping each region to the total amount.

    This helper iterates once over ``rows`` and accumulates the ``amount``
    for every encountered region. It is deliberately kept private – the
    public API of the module remains ``summarize_sales``.
    """
    totals = {}
    for row in rows:
        # ``row`` is expected to be a mapping with ``region`` and ``amount``
        region = row['region']
        totals[region] = totals.get(region, 0) + row['amount']
    return totals


def summarize_sales(rows):
    """Summarize sales amounts per region.

    The function returns a dictionary with keys ``'north'`` and ``'south'``
    (always present, defaulting to ``0``) followed by any other region that
    appears in ``rows``. The ordering mirrors the original implementation:
    ``north`` then ``south`` then the remaining regions in the order they were
    first encountered.

    The behavior is unchanged for empty input, negative values, or
    fractional amounts.
    """
    # Use the shared aggregation helper to avoid duplicated logic.
    aggregated = _aggregate_by_region(rows)

    # Build the result preserving the original key order (north, south, then others).
    result = {
        'north': aggregated.get('north', 0),
        'south': aggregated.get('south', 0),
    }
    for region, amount in aggregated.items():
        if region not in ('north', 'south'):
            result[region] = amount
    return result

