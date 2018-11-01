from inflect import engine
import json

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


def format_delta(delta):
    string_delta = ''
    if delta.months != 0:
        string_delta = f'{abs(delta.months)} months'
        if delta.days != 0:
            string_delta = f'{string_delta}, {abs(delta.days)} days'
    elif delta.days != 0:
        string_delta = f'{abs(delta.days)} days'

    if delta.months < 0 or delta.days < 0:
        string_delta = f'{string_delta} ago'

    return string_delta


def get_current_season(division, bot):
    if division.lower() not in bot.config['division_season']:
        r = bot.session.get(f'{bot.base_url}/api/info/{division.lower()}')
        info = json.loads(r.content)
        if 'season' not in info:
            return False

        bot.config['division_season'][division.lower()] = str(info['season']['id'])
        if str(info['season']['id']) not in bot.config['season_info']:
            bot.config['season_info'][str(info['season']['id'])] = info['season']

        bot.save_config()

    return True
