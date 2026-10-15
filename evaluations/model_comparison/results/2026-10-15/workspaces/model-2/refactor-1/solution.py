def _aggregate_sales(rows):
    """Return a dict mapping each region to the total amount.

    This helper consolidates the aggregation logic in one place, making it
    reusable for any region. It simply walks the input rows and sums the
    ``amount`` values per ``region``.
    """
    totals = {}
    for row in rows:
        region = row['region']
        totals[region] = totals.get(region, 0) + row['amount']
    return totals


def summarize_sales(rows):
    """Summarize sales amounts per region.

    The function returns a dictionary with keys ``'north'`` and ``'south'``
    always present (defaulting to ``0`` when no rows for those regions exist)
    followed by any other regions in the order they first appear in ``rows``.
    """
    # Use the shared helper to get totals for all regions.
    totals = _aggregate_sales(rows)

    # Ensure north and south are present, defaulting to 0.
    north = totals.get('north', 0)
    south = totals.get('south', 0)

    # Build the result preserving the required order: north, south, then
    # other regions in their first‑seen order.
    result = {'north': north, 'south': south}
    for row in rows:
        region = row['region']
        if region not in ('north', 'south') and region not in result:
            result[region] = totals[region]
    return result

