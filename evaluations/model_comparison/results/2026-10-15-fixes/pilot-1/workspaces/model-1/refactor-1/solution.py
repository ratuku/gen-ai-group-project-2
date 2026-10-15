def _aggregate(rows, region):
    """Return the sum of amounts for the given region.
    Handles empty rows and any numeric amount (negative, fractional)."""
    return sum(r['amount'] for r in rows if r['region'] == region)

def summarize_sales(rows):
    """Summarize sales amounts by region.

    The function returns a dictionary with keys for each region that appears in
    *rows*.  The keys ``north`` and ``south`` are always present (even if the
    sum is zero).  Any other region is added dynamically.

    Parameters
    ----------
    rows : iterable of dict
        Each dict must contain ``region`` and ``amount`` keys.

    Returns
    -------
    dict
        Mapping of region names to the total amount.
    """
    # Determine all unique regions
    regions = {row['region'] for row in rows}
    # Ensure north and south are always included
    regions.update(['north', 'south'])
    # Aggregate amounts per region using the helper
    result = {region: _aggregate(rows, region) for region in regions}
    return result
