def _aggregate_region(rows, target_regions):
    """Helper to sum amounts for rows whose region is in *target_regions*.

    Returns a dictionary mapping each region in *target_regions* to the total
    amount for that region. Regions not present in *rows* will have a total of
    ``0``.
    """
    totals = {region: 0 for region in target_regions}
    for row in rows:
        region = row.get('region')
        if region in target_regions:
            totals[region] += row.get('amount', 0)
    return totals


def summarize_sales(rows):
    """Summarize sales amounts by region.

    The function returns a dictionary with keys for ``'north'`` and ``'south'``
    as well as any other region present in *rows*. The values are the summed
    ``amount`` fields for each region. The behaviour matches the original
    implementation, handling empty input, negative and fractional amounts.
    """
    # Aggregate known regions using the shared helper
    known = _aggregate_region(rows, ('north', 'south'))
    # Aggregate any other regions
    other = {}
    for row in rows:
        region = row.get('region')
        if region not in ('north', 'south'):
            other[region] = other.get(region, 0) + row.get('amount', 0)
    # Combine the dictionaries, ensuring known regions appear first
    return {**known, **other}
