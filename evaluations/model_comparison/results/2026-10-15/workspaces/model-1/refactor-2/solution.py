def summarize_sales(rows):
    north = sum(r['amount'] for r in rows if r['region'] == 'north')
    south = sum(r['amount'] for r in rows if r['region'] == 'south')
    other = {}
    for row in rows:
        if row['region'] not in ('north', 'south'):
            other[row['region']] = other.get(row['region'], 0) + row['amount']
    return {'north': north, 'south': south, **other}
