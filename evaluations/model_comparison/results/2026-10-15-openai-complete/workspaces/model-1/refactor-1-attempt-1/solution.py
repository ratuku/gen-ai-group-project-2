def _sum_region(rows, region):
    return sum(r['amount'] for r in rows if r['region'] == region)


def summarize_sales(rows):
    north = _sum_region(rows, 'north')
    south = _sum_region(rows, 'south')
    other = {}
    for row in rows:
        if row['region'] not in ('north', 'south'):
            other[row['region']] = other.get(row['region'], 0) + row['amount']
    return {'north': north, 'south': south, **other}
