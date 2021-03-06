from inflect import engine
import json
from urllib import parse
from base64 import b64encode
import requests
import os
from datetime import datetime
import time
import re
from itertools import zip_longest
import logging
import sys, traceback

p = engine()

logging.basicConfig(filename='fantasy_info.log', level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")


class Entrant:
    def __init__(self, config, league, cookie, headers, info):
        self.config = config
        self.league = league
        self.cookie = cookie
        self.headers = headers

        self.retry = False

        self.team = None
        self.drivers = []
        self.turbo = None
        self.mega = None
        self.race_score = 0
        self.score = 0

        self.discord_id = None
        self.id = str(info['user_id'])
        if self.id not in league['players']:
            self.name = f"Unknown ({info['team_name']} / {self.id})"
        else:
            self.name = league['players'][self.id]['name']
            self.discord_id = league['players'][self.id]['id']

    def retrieve_info(self):
        logging.info(f"Getting player info - {self.name}")
        self.retry = False

        r = requests.get(self.config['urls']['user_url'].format(self.id), headers=self.headers)
        if r.status_code in [200, 304]:
            content = json.loads(r.content.decode('utf-8'))
            self.score = content['user']['leaderboard_positions']['slot_1'][self.league['f1_id']]['score']

            logging.info(f"Getting team info")
            team_id = content["user"]["historical_picked_teams_info"]["slot_1"]["historical_team_info"][-1]["picked_team_id"]
            tr = requests.get(self.config['urls']['team_url'].format(team_id), headers=self.headers)
            if tr.status_code in [200, 304]:
                tc = json.loads(tr.content.decode("utf-8"))
                self.race_score = tc['picked_team']['score']
                for entry in tc['picked_team']['picked_players']:
                    driver = self.config['fantasy']['drivers_teams'][str(entry["player"]["id"])]

                    if entry["player"]["position_id"] == 2:
                        self.team = {
                            "short_name": entry["player"]["external_id"][-3:],
                            "name": entry["player"]["display_name"],
                            "price": entry["player"]["price"],
                            "picked": entry["player"]["current_price_change_info"]["current_selection_percentage"],
                            "score": entry["score"]
                        }
                    else:
                        self.drivers.append({
                            "short_name": entry["player"]["external_id"][3:6],
                            "name": entry["player"]["display_name"],
                            "price": entry["player"]["price"],
                            "picked": entry["player"]["current_price_change_info"]["current_selection_percentage"],
                            "score": entry["score"]
                        })

                        if str(tc['picked_team']['boosted_player_id']) in self.config['fantasy']['drivers_teams']:
                            self.turbo = self.config['fantasy']['drivers_teams'][str(tc['picked_team']['boosted_player_id'])]

                        if str(tc['picked_team']['mega_boosted_player_id']) in self.config['fantasy']['drivers_teams']:
                            self.mega = self.config['fantasy']['drivers_teams'][str(tc['picked_team']['mega_boosted_player_id'])]
            else:
                logging.info(f"[team] HTTP status code - {r.status_code}")
                self.retry = True

            print(f"{self.name} collected")
        else:
            logging.info(f"[user] HTTP status code - {r.status_code}")
            self.retry = True


class EntrantEncoder(json.JSONEncoder):
    def default(self, entrant):
        return {
            "id": entrant.id,
            "discord_id": entrant.discord_id,
            "name": entrant.name,
            "team": entrant.team,
            "drivers": entrant.drivers,
            "race_score": entrant.race_score,
            "score": entrant.score,
            "turbo": entrant.turbo,
            "mega": entrant.mega
        }


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
            'Content-Type': 'application/json',
        }

        payload = json.dumps({
            'Login': credentials['fantasy']['username'],
            'Password': credentials['fantasy']['password']
        })

        response = requests.post(config['urls']['create_session_url'], data=payload, headers=headers)
        if response.status_code not in [200, 304]:
            return False

        body = json.loads(response.content.decode('utf-8'))

        info = {"data": {"subscriptionToken": body['data']['subscriptionToken']}}

        cookie = parse.quote(json.dumps(info))
        b64cookie = b64encode(cookie.encode('utf8')).decode('utf8')
        with open('cookie.txt', 'w') as outfile:
            outfile.write(b64cookie)
        return b64cookie
    else:
        print('Using stored cookie')
        with open('cookie.txt') as infile:
            return infile.read().strip()


async def update_fantasy_details(msg, league, config, f1_cookie):
    headers = {
        'X-F1-COOKIE-DATA': f1_cookie,
        'User-Agent': 'VirtualWDCPC F1 Fantasy Discord Bot v0.1'
    }

    logging.info("Requesting league info")
    r = requests.get(config['urls']['league_url'].format(league['f1_id']), headers=headers)
    if r.status_code in [200, 304]:
        content = json.loads(r.content.decode('utf-8'))
        entrants = content['leaderboard']['leaderboard_entrants']
        details = {}
    else:
        logging.info(f"HTTP status code - {r.status_code}")
        return False

    retry = []

    logging.info("Filtering entrants")
    filtered_entrants = [x for x in entrants if str(x['user_id']) not in league['ignore']]
    for _, info in enumerate(filtered_entrants):
        entrant = Entrant(config, league, f1_cookie, headers, info)

        await msg.edit(content=f"Updating: {entrant.name}")
        entrant.retrieve_info()
        if entrant.retry:
            retry.append(entrant)

        details[entrant.id] = entrant
        time.sleep(1)

    while len(retry) > 0:
        time.sleep(5)
        logging.info("Processing retries")
        for entrant in retry:
            await msg.edit(content=f"Updating: {entrant.name}")
            entrant.retrieve_info()
            if not entrant.retry:
                retry.remove(entrant)
            details[entrant.id] = entrant
            time.sleep(1)

    with open(f"{league['tag']}.json", 'w') as outfile:
        json.dump(filtered_entrants, outfile, indent=4)

    with open(f"{league['tag']}-details.json", 'w') as outfile:
        json.dump(details, outfile, cls=EntrantEncoder, indent=4)

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


def fix_title_weirdness(value):
    return value.replace("Th", "th").replace("Rd", "rd").replace("Nd", "nd").replace("St", "st")
