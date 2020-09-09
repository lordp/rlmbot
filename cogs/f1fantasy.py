from discord.ext import commands
from cachecontrol import CacheControl
from terminaltables import AsciiTable
from utils import *
import json


class F1Fantasy(commands.Cog):
    def __init__(self, bot_obj):
        self.bot = bot_obj
        self.config = {}
        self.credentials = {}

        self.load_config()

        self.session = CacheControl(requests.session())

    def load_config(self):
        try:
            with open("config.json") as config:
                self.config = json.load(config)
            with open("credentials.json") as credentials:
                self.credentials = json.load(credentials)
        except FileNotFoundError:
            self.config = {
                "division_season": {},
                "season_info": {},
                "division_map": {},
                "fantasy": {},
            }

    def save_config(self):
        with open("config.json", "w") as config:
            json.dump(self.config, config, indent=4)

    def _find_league(self, ctx):
        league = None

        try:
            league = next(
                iter(
                    [
                        info['tag']
                        for league_id, info in self.config["fantasy"].items()
                        if league_id == str(ctx.guild.id)
                    ]
                )
            )
        except StopIteration:
            pass

        return league

    def _find_player(self, ctx):
        player = None

        try:
            player = next(
                iter(
                    [
                        f1_id
                        for f1_id, info in self.config["fantasy"][str(ctx.guild.id)]["players"].items()
                        if info["id"] == ctx.author.id
                    ]
                )
            )
        except StopIteration:
            pass

        return player

    def _find_driver(self, tag):
        driver = None

        try:
            driver = next(
                iter(
                    [
                        f1_id
                        for f1_id, info in self.config["fantasy"]["drivers_teams"].items()
                        if info.lower() == tag.lower()
                    ]
                )
            )
        except StopIteration:
            pass

        return driver

    async def _show_fantasy(self, ctx):
        league = self._find_league(ctx)

        if league:
            with open(f"{league}-details.json") as infile:
                league = json.load(infile)

            headers = ["Pos", "Name", "Total", "Race", "Drivers", "Team", "Turbo", "Mega"]
            data = []
            index = 1
            for _, entry in league.items():
                try:
                    drivers = ", ".join([e["short_name"] for e in entry["drivers"]])
                    team = entry["team"]["short_name"]
                except KeyError:
                    drivers = ""
                    team = ""

                data.append(
                    [
                        p.ordinal(index),
                        entry["name"],
                        format_float(entry["score"]),
                        format_float(entry["race_score"]),
                        drivers,
                        team,
                        entry["turbo"] or "???",
                        entry["mega"] or "???"
                    ]
                )

                index += 1

            for group in grouper(data, 10):
                table_data = [headers]
                for row in list(group):
                    if row is not None:
                        table_data.append(row)

                table_instance = AsciiTable(table_data)
                table_instance.inner_column_border = False
                table_instance.outer_border = False
                table_instance.justify_columns[2] = "center"
                table_instance.justify_columns[3] = "center"
                table_instance.justify_columns[6] = "center"

                content = "```{}```".format(table_instance.table)
                await ctx.send(content)
        else:
            await ctx.send(f"League {league} not found.")

    @commands.group()
    async def fantasy(self, ctx):
        """F1 fantasy commands"""
        if ctx.invoked_subcommand is None:
            await ctx.send_help('fantasy')

    @fantasy.group()
    async def show(self, ctx):
        """Show the F1 fantasy table."""
        await self._show_fantasy(ctx)

    @fantasy.group()
    async def result(self, ctx):
        """Show your points from the most recent race."""
        league = self._find_league(ctx)

        if league:
            with open(f"{league}-details.json") as infile:
                details = json.load(infile)

            player = self._find_player(ctx)
            if player:
                totals = {
                    "points": 0,
                    "price": 0,
                    "picked": 0
                }

                headers = ["Name", "Turbo", "Mega", "Points", "Price", "Picked %"]
                data = [headers]
                player_details = details[str(player)]
                for entry in player_details["drivers"]:
                    data.append(
                        [
                            entry["name"],
                            "Yes" if entry["short_name"] == player_details["turbo"] else "No",
                            "Yes" if entry["short_name"] == player_details["mega"] else "No",
                            format_float(entry["score"]),
                            format_float(entry["price"]),
                            format_float(entry["picked"])
                        ]
                    )

                    totals["points"] += entry["score"]
                    totals["price"] += entry["price"]
                    totals["picked"] += entry["picked"]

                data.append([])
                team = player_details["team"]
                data.append(
                    [
                        team["name"],
                        "",
                        "",
                        format_float(team["score"]),
                        format_float(team["price"]),
                        format_float(team["picked"])
                    ]
                )

                totals["points"] += team["score"]
                totals["price"] += team["price"]
                totals["picked"] += team["picked"]

                totals["picked"] = round(totals["picked"] / 6, 1)

                data.append([])
                data.append(
                    [
                        "Total/Average",
                        "",
                        "",
                        format_float(round(totals["points"], 1)),
                        format_float(round(totals["price"], 1)),
                        format_float(round(totals["picked"], 1))
                    ]
                )

                table_instance = AsciiTable(data)
                table_instance.inner_column_border = False
                table_instance.outer_border = False
                table_instance.justify_columns[1] = "center"
                table_instance.justify_columns[2] = "right"
                table_instance.justify_columns[3] = "right"
                table_instance.justify_columns[4] = "right"

                msg = "```{}```".format(table_instance.table)
            else:
                msg = f"Player not found."
        else:
            msg = f"League {league} not found."

        await ctx.send(msg)

    @fantasy.group(hidden=True)
    async def set(self, ctx, league_id, tag):
        self.config['fantasy'][str(ctx.guild.id)] = {
            "tag": tag,
            "f1_id": league_id,
            "players": {}
        }

        self.save_config()

        await ctx.send(f'{tag} set to this server.')

    @fantasy.group(name="add-player")
    @commands.is_owner()
    async def add_player(self, ctx, player, alias, f1_id):
        """Add player info."""
        players = self.config['fantasy'][str(ctx.guild.id)]['players']
        for member in ctx.guild.members:
            if player.lower() in member.name.lower():
                found = False
                for _, info in players.items():
                    if info['name'].lower() == alias.lower():
                        info['name'] = alias
                        info['id'] = member.id
                        found = True
                        msg = 'Updated'
                if not found:
                    players[f1_id] = {
                        "name": alias,
                        "id": member.id
                    }

                    msg = 'added'

        self.save_config()

        await ctx.send(f'{alias} {msg}.')

    @fantasy.group()
    async def update(self, ctx):
        """Update the fantasy details (points, position, etc)"""
        await ctx.send("This command takes a couple of minutes to complete, please be patient.")
        if 'fantasy' not in self.credentials:
            msg = "Credentials missing."
        else:
            f1_cookie = generate_f1_cookie(self.config, self.credentials)
            if not f1_cookie:
                msg = "Fantasy update failed."
            elif str(ctx.guild.id) not in self.config['fantasy']:
                msg = "This server was not found in fantasy settings."
            else:
                league = self.config['fantasy'][str(ctx.guild.id)]
                msg = await ctx.send(f"Updating {league['tag']}:")
                await update_fantasy_details(msg, league, self.config, f1_cookie)
                msg = "Fantasy details updated."

        await ctx.send(msg)
        await self._show_fantasy(ctx)

    @fantasy.group()
    async def events(self, ctx, tag):
        """Show the point scoring events for a driver (most recent race)"""
        await ctx.send("Fetching events, please wait")

        if 'fantasy' not in self.credentials:
            msg = "Credentials missing."
        else:
            f1_cookie = generate_f1_cookie(self.config, self.credentials)
            if not f1_cookie:
                msg = "Events fetch failed."
            elif str(ctx.guild.id) not in self.config['fantasy']:
                msg = "This server was not found in fantasy settings."
            else:
                driver = self._find_driver(tag)
                if not driver:
                    msg = f"Driver {tag} not found"
                else:
                    headers = {
                        'X-F1-COOKIE-DATA': f1_cookie
                    }

                    r = requests.get(self.config['urls']['events_url'].format(driver), headers=headers)
                    if r.status_code in [200, 304]:
                        headers = ["Event", "Freq", "Points"]
                        data = [headers]

                        content = json.loads(r.content.decode('utf-8'))
                        events = content['game_periods_scores'][-1]
                        for event in events['events']:
                            data.append([
                                fix_title_weirdness(event['display_name'].title()),
                                event['freq'],
                                format_float(event['points'])
                            ])

                        table_instance = AsciiTable(data)
                        table_instance.inner_column_border = False
                        table_instance.outer_border = False
                        table_instance.justify_columns[1] = "center"
                        table_instance.justify_columns[2] = "center"

                        msg = "```{}```".format(table_instance.table)

        await ctx.send(msg)
