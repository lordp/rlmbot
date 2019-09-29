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

    async def _show_fantasy(self, ctx):
        league = self._find_league(ctx)

        if league:
            with open(f"{league}.json") as infile:
                league = json.load(infile)

            headers = ["Pos", "Name", "Total", "Race", "Drivers", "Team", "Turbo"]
            data = []
            for index, entry in enumerate(league):
                try:
                    drivers = ", ".join(entry["picks"]["drivers"])
                    team = entry["picks"]["team"]
                except KeyError:
                    drivers = ""
                    team = ""

                data.append(
                    [
                        p.ordinal(index + 1),
                        entry["user"]["name"],
                        format_float(entry["score"]),
                        format_float(entry["picks"]["race_score"]),
                        drivers,
                        team,
                        entry["picks"]["turbo"] if "turbo" in entry["picks"] else "???"
                    ]
                )

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

                headers = ["Name", "Turbo", "Points", "Price", "Picked %"]
                data = [headers]
                for index, entry in details[str(player)]["drivers"].items():
                    data.append(
                        [
                            entry["name"],
                            "Yes" if entry["turbo"] else "No",
                            format_float(entry["score"]),
                            format_float(entry["price"]),
                            format_float(entry["picked"])
                        ]
                    )

                    totals["points"] += entry["score"]
                    totals["price"] += entry["price"]
                    totals["picked"] += entry["picked"]

                data.append([])
                team = details[str(player)]["team"]
                data.append(
                    [
                        team["name"],
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
                msg = await ctx.send("Updating:")
                await update_fantasy_details(msg, league, self.config, f1_cookie)
                msg = "Fantasy details updated."

        await ctx.send(msg)
        await self._show_fantasy(ctx)
