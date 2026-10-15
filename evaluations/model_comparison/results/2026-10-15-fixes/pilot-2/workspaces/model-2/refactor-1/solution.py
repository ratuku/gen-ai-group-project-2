def _sum_region(rows, target_region):
    """Helper to sum amounts for a specific region.

    Args:
        rows (list[dict]): List of sales rows, each containing 'region' and 'amount'.
        target_region (str): The region to aggregate.

    Returns:
        float: Sum of amounts for the given region (0 if none).
    """
    return sum(r['amount'] for r in rows if r['region'] == target_region)

def summarize_sales(rows):
    """Summarize sales amounts by region.

    Returns a dictionary with keys for each region present in the data.
    The 'north' and 'south' regions are always included (with 0 if absent),
    and any other regions are added dynamically.
    """
    north = _sum_region(rows, 'north')
    south = _sum_region(rows, 'south')
    other = {}
    for row in rows:
        if row['region'] not in ('north', 'south'):
            other[row['region']] = other.get(row['region'], 0) + row['amount']
    return {'north': north, 'south': south, **other}
