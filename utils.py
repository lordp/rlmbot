from inflect import engine

p = engine()


def format_float(num):
    return format(num, '.15g')


def sort_counter(results, ordinal=True, convert_int=True):
    if convert_int:
        results = {int(k): int(v) for k, v in results.items()}
    order = sorted(results)
    if ordinal:
        result = ["{} x {}".format(p.ordinal(place), results[place]) for place in order]
    else:
        result = ["{} x {}".format(place, results[place]) for place in order]

    return result


def list_or_none(values):
    if len(values) > 0:
        return ', '.join(values)
    else:
        return "None"


def add_row(data, pos, teams_disabled):
    if teams_disabled:
        data.append([
            p.ordinal(pos['position']),
            pos['name'],
            format_float(pos['points'])
        ])
    else:
        data.append([
            p.ordinal(pos['position']),
            pos['name'],
            pos['team']['name'],
            format_float(pos['points'])
        ])

    return data
