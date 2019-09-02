from inflect import engine
import json
from urllib import parse
from base64 import b64encode
import requests
import os
from datetime import datetime
import re
from itertools import zip_longest

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
        r = bot.session.get(f"{bot.config['urls']['base_url']}/api/info/{division.lower()}")
        info = json.loads(r.content)
        if "season" not in info:
            return False

        bot.config["division_season"][division.lower()] = str(info["season"]["id"])
        if str(info["season"]["id"]) not in bot.config["season_info"]:
            bot.config["season_info"][str(info["season"]["id"])] = info["season"]

        bot.save_config()

    return True


def generate_f1_cookie(config, credentials):
    try:
        mtime = datetime.fromtimestamp(os.stat('cookie.txt').st_mtime)
        now = datetime.now()
        regenerate = (now - mtime).days > 1
    except FileNotFoundError:
        regenerate = True

    if regenerate:
        print('Regenerating cookie')
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
                "profile": {"SubscriberId": 80689239, "country": "NZL", "firstName": "VWDCPC"}}

        cookie = parse.quote(json.dumps(info))
        b64cookie = b64encode("account-info={}".format(cookie).encode('utf8')).decode('utf8')
        with open('cookie.txt', 'w') as outfile:
            outfile.write(b64cookie)
        return b64cookie
    else:
        print('Using stored cookie')
        with open('cookie.txt') as infile:
            return infile.read().strip()


async def update_fantasy_details(msg, league, config, f1_cookie):
    headers = {
        'X-F1-COOKIE-DATA': f1_cookie
    }

    r = requests.get(config['urls']['league_url'].format(league['f1_id']), headers=headers)
    if r.status_code in [200, 304]:
        content = json.loads(r.content.decode('utf-8'))
        entrants = content['leaderboard']['leaderboard_entrants']
        details = {}
    else:
        return False

    filtered_entrants = [x for x in entrants if str(x['user_id']) not in league['ignore']]
    for index, entrant in enumerate(filtered_entrants):
        if not int(entrant['user_id']) in league['ignore']:
            if str(entrant['user_id']) not in league['players']:
                entrant['user'] = f"Unknown ({entrant['team_name']})"
                print(entrant["first_name"], entrant["last_name"])
            else:
                entrant['user'] = league['players'][str(entrant['user_id'])]

            details[entrant['user_id']] = {}

            await msg.edit(content=f"Updating: {entrant['user']['name']} ({index + 1}/{len(filtered_entrants)})")
            r = requests.get(config['urls']['user_url'].format(entrant['user_id']), headers=headers)
            if r.status_code in [200, 304]:
                content = json.loads(r.content.decode('utf-8'))
                entrant['picks'] = {
                    'drivers': [],
                    'team': None,
                    'race_score': 0
                }
                entrant['score'] = content['user']['leaderboard_positions']['slot_1'][league['f1_id']]['score']

                try:
                    team_id = content["user"]["historical_picked_teams_info"]["slot_1"]["historical_team_ids"][-1]
                    tr = requests.get(config['urls']['team_url'].format(team_id), headers=headers)
                    if tr.status_code in [200, 304]:
                        team_content = json.loads(tr.content.decode("utf-8"))
                        for entry in team_content['picked_team']['picked_players']:
                            driver = config['fantasy']['drivers_teams'][str(entry["player"]["id"])]
                            if entry["player"]["position_id"] == 2:
                                entrant['picks']['team'] = driver
                            else:
                                entrant['picks']['drivers'].append(driver)
                            entrant['picks']["race_score"] += entry["score"]

                            details[entrant['user_id']][entry["player"]["id"]] = {
                                "name": entry["player"]["display_name"],
                                "price": entry["player"]["price"],
                                "picked": entry["player"]["picked_percentage"],
                                "score": entry["score"],
                                "turbo": team_content["picked_team"]["boosted_player_id"] == entry["player"]["id"]
                            }

                        entrant['picks']['turbo'] = config['fantasy']['drivers_teams'][str(
                            team_content['picked_team']['boosted_player_id']
                        )]
                except KeyError:
                    print(f"User {entrant['user']} does not have historical team picks")
                    for entry in content['user']['this_week_player_ids']['slot_1']:
                        if entry <= 10:
                            entrant['picks']['team'] = config['fantasy']['drivers_teams'][str(entry)]
                        else:
                            entrant['picks']['drivers'].append(config['fantasy']['drivers_teams'][str(entry)])

                print(f"{entrant['user']['name']} collected")

    with open(f"{league['tag']}.json", 'w') as outfile:
        json.dump(filtered_entrants, outfile, indent=4)

    with open(f"{league['tag']}-details.json", 'w') as outfile:
        json.dump(details, outfile, indent=4)

    return True


def find_emojis(msg, bot):
    try:
        for this_emoji in re.findall(r':([^:]+):', msg):
            emoji = next(iter([(e.id, e.name) for e in bot.emojis if e.name.lower() == this_emoji.lower()]))
            msg = re.sub(r':{}:'.format(this_emoji), '<:{}:{}>'.format(emoji[1], emoji[0]), msg)
    except StopIteration:
        pass

    return msg


def grouper(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)