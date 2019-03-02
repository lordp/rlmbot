from inflect import engine
import json
from urllib import parse
from base64 import b64encode
import requests

p = engine()


def format_float(num):
    return format(num, ".15g")


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
        return ", ".join(values)
    else:
        return "None"


def add_row(data, pos, teams_disabled):
    if teams_disabled:
        data.append(
            [p.ordinal(pos["position"]), pos["name"], format_float(pos["points"])]
        )
    else:
        data.append(
            [
                p.ordinal(pos["position"]),
                pos["name"],
                pos["team"]["name"],
                format_float(pos["points"]),
            ]
        )

    return data


def format_delta(delta):
    string_delta = ""
    if delta.months != 0:
        string_delta = f"{abs(delta.months)} months"
        if delta.days != 0:
            string_delta = f"{string_delta}, {abs(delta.days)} days"
    elif delta.days != 0:
        string_delta = f"{abs(delta.days)} days"

    if delta.months < 0 or delta.days < 0:
        string_delta = f"{string_delta} ago"

    return string_delta


def get_current_season(division, bot):
    if division.lower() not in bot.config["division_season"]:
        r = bot.session.get(f"{bot.base_url}/api/info/{division.lower()}")
        info = json.loads(r.content)
        if "season" not in info:
            return False

        bot.config["division_season"][division.lower()] = str(info["season"]["id"])
        if str(info["season"]["id"]) not in bot.config["season_info"]:
            bot.config["season_info"][str(info["season"]["id"])] = info["season"]

        bot.save_config()

    return True


def generate_f1_cookie(config, credentials):
    headers = {
        'apiKey': credentials['fantasy']['apikey'],
        'cd-systemid': credentials['fantasy']['cd-systemid'],
        'Content-Type': 'application/json',
        'cd-language': 'en-US'
    }

    payload = json.dumps({
        'Login': credentials['fantasy']['username'],
        'Password': credentials['fantasy']['password']
    })

    response = requests.post(config['urls']['create_session_url'], data=payload, headers=headers)
    if response.status_code not in [200, 304]:
        return False

    body = json.loads(response.content.decode('utf-8'))

    info = {"data": {"subscriptionStatus": "inactive", "subscriptionToken": body['data']['subscriptionToken']},
            "profile": {"SubscriberId": 34767804, "country": "NZL", "firstName": "Darryl"}}

    cookie = parse.quote(json.dumps(info))
    return b64encode("account-info={}".format(cookie).encode('utf8')).decode('utf8')


def update_fantasy_details(league, config, f1_cookie):
    headers = {
        'X-F1-COOKIE-DATA': f1_cookie
    }

    r = requests.get(config['urls']['league_url'].format(league['f1_id']), headers=headers)
    if r.status_code in [200, 304]:
        content = json.loads(r.content.decode('utf-8'))
        entrants = content['leaderboard']['leaderboard_entrants']
    else:
        return False

    for entrant in entrants:
        r = requests.get(config['urls']['user_url'].format(entrant['user_id']), headers=headers)
        if r.status_code in [200, 304]:
            content = json.loads(r.content.decode('utf-8'))
            entrant['picks'] = {
                'drivers': [],
                'team': None,
                'score': content['user']['leaderboard_positions']['slot_1'][league['f1_id']]['score']
            }

            for entry in content['user']['this_week_player_ids']['slot_1']:
                if entry <= 10:
                    entrant['picks']['team'] = config['fantasy']['drivers_teams'][str(entry)]
                else:
                    entrant['picks']['drivers'].append(config['fantasy']['drivers_teams'][str(entry)])

            if str(entrant['user_id']) not in league['players']:
                entrant['user'] = f"Unknown ({entrant['user_id']})"
            else:
                entrant['user'] = league['players'][str(entrant['user_id'])]

            print(f"{entrant['user']} collected")

    with open(f"{league['tag']}.json", 'w') as outfile:
        json.dump(entrants, outfile, indent=4)

    return True