from discord.ext import commands
import requests
from cachecontrol import CacheControl
import json
from collections import Counter
from datetime import datetime
from terminaltables import AsciiTable
from utils import *


class FSRBot:
    def __init__(self, bot_obj):
        self.bot = bot_obj
        self.config = {}

        self.load_config()

        req_sess = requests.session()
        self.session = CacheControl(req_sess)
        
        self.base_url = 'http://localhost:8000'

    def load_config(self):
        try:
            with open('config.json') as config:
                self.config = json.load(config)
        except FileNotFoundError:
            self.config = {
                'division_season': {},
                'season_info': {},
                'division_map': {}
            }

    def save_config(self):
        with open('config.json', 'w') as config:
            json.dump(self.config, config, indent=4)

    @commands.command()
    async def nextrace(self, ctx, division: str = None):
        """Show when the next race is, or when the next race for a particular division is."""
        url = f'{self.base_url}/api/next-race'
        if division:
            url += f'?division={division}'

        r = self.session.get(url)
        next_race = json.loads(r.content)

        now = datetime.today().utcnow().replace(second=0, microsecond=0)
        start_time = datetime.strptime(next_race['start_time'], '%Y-%m-%dT%H:%M:%SZ')
        delta = str(start_time - now)

        msg = f"**Division**: {next_race['division']}\n" \
              f"**Round**: {next_race['round_number']}\n" \
              f"**Name**: {next_race['name']}\n" \
              f"**When**: {next_race['start_time']} (in {delta})"

        await ctx.send(msg)

    @commands.command()
    async def stats(self, ctx, driver: str, season: str = None, division: str = None):
        """Show stats for a particular driver, optionally filtered by season and division"""
        if len(driver) < 3:
            msg = 'Minimum search length is 3 characters'
        else:
            url = f'{self.base_url}/api/stats?driver={driver.lower()}'
            if season:
                url += f'&season={season.lower()}'
            if division:
                division = self.config['division_map'].get(division.lower(), division.lower())
                url += f'&division={division.lower()}'

            r = self.session.get(url)
            stats = json.loads(r.content)

            if 'name' not in stats:
                if 'error' in stats:
                    msg = stats['error']
                else:
                    msg = 'Driver not found.'
            else:
                qualifying = list_or_none(sort_counter(Counter(stats['qualifying_positions'])))
                race_results = list_or_none(sort_counter(Counter(stats['race_positions'])))
                dnfs = list_or_none(sort_counter(Counter(stats['dnf_reasons']), convert_int=False, ordinal=False))

                msg = f"**{stats['name']}**\n" \
                      f"{stats['attendance']} races, {stats['points_finishes']} points finishes\n" \
                      f"**Qualifying**: {qualifying}\n" \
                      f"**Average**: {p.ordinal(int(stats['avg_qualifying']))}\n" \
                      f"**Poles**: {stats['pole_positions']}, " \
                      f"**Q DSQ**: {stats['qualifying_penalty_dsq']}, " \
                      f"**Q Grid**: {stats['qualifying_penalty_grid']}, " \
                      f"**Q BoG**: {stats['qualifying_penalty_bog']}, " \
                      f"**Q SFP**: {stats['qualifying_penalty_sfp']}\n" \
                      f"**Results**: {race_results}\n" \
                      f"**Average**: {p.ordinal(int(stats['avg_race']))}\n" \
                      f"**Best Finish**: {p.ordinal(stats['best_finish'])}, " \
                      f"**Wins**: {stats['wins']}, **Podiums**: {stats['podiums']}, " \
                      f"**R DSQ**: {stats['race_penalty_dsq']}, " \
                      f"**R Time**: {stats['race_penalty_time']}, " \
                      f"**R Pos**: {stats['race_penalty_positions']}, " \
                      f"**Penalty Points**: {stats['penalty_points']}\n" \
                      f"**DNFs**: {dnfs}\n" \
                      f"{stats['laps_completed']} laps completed ({stats['laps_lead']} in the lead), " \
                      f"with {stats['fastest_laps']} fastest laps"

        await ctx.send(msg)

    @commands.command()
    async def standings(self, ctx, division, driver: str = None):
        """Show standings for the current season of the specified division."""
        division = self.config['division_map'].get(division.lower(), division.lower())

        if division.lower() not in self.config['division_season']:
            r = self.session.get(f'{self.base_url}/api/info/{division.lower()}')
            info = json.loads(r.content)
            if 'season' not in info:
                await ctx.send('No seasons found for division')
                return

            self.config['division_season'][division.lower()] = str(info['season']['id'])
            if str(info['season']['id']) not in self.config['season_info']:
                self.config['season_info'][str(info['season']['id'])] = info['season']

            self.save_config()

        season_id = self.config['division_season'][division.lower()]

        url = f'{self.base_url}/api/standings/{season_id}'
        if driver:
            url += f'?driver={driver.lower()}'

        r = self.session.get(url)
        standings = json.loads(r.content)

        data = [
            ['Pos', 'Driver', 'Team', 'Points'],
        ]

        if self.config['season_info'][season_id]['teams_disabled']:
            data[0].pop(2)

        for pos in standings[0:5]:
            add_row(data, pos, self.config['season_info'][season_id]['teams_disabled'])

        found = False
        if driver:
            try:
                found = [d for d in data if driver.lower() in d[1].lower()][0]
            except IndexError:
                pass

            if not found:
                try:
                    info = [d for d in standings if driver.lower() in d['name'].lower()][0]
                    data.append(['...'])
                    add_row(data, info, self.config['season_info'][season_id]['teams_disabled'])
                except IndexError:
                    pass

        table_instance = AsciiTable(data)
        table_instance.inner_column_border = False
        table_instance.outer_border = False

        season_info = self.config['season_info'][season_id]
        season = f"Name: {season_info['name']} ({season_info['start_date']} to {season_info['end_date']})"
        msg = table_instance.table

        await ctx.send(f"```{season}\n\n{msg}```")

    @commands.command(hidden=True)
    async def info(self, ctx):
        print(ctx.guild.created_at)


bot = commands.Bot(command_prefix=commands.when_mentioned_or("?"),
                   description='FSR Bot')


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} ({bot.user.id})')


bot.add_cog(FSRBot(bot))
bot.run('TOKEN', reconnect=True)
