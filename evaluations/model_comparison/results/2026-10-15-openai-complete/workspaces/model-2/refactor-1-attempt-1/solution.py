def _aggregate_region(rows, region):
    return sum(r['amount'] for r in rows if r['region'] == region)

def summarize_sales(rows):
    # Aggregate all regions in a single pass
    region_sums = {}
    for r in rows:
        reg = r['region']
        region_sums[reg] = region_sums.get(reg, 0) + r['amount']
    # Use the helper for 'north' and 'south' in accordance with requirements
    north = _aggregate_region(rows, 'north')
    south = _aggregate_region(rows, 'south')
    # Remove 'north' and 'south' since they are separately reported
    region_sums.pop('north', None)
    region_sums.pop('south', None)
    return {'north': north, 'south': south, **region_sums}
