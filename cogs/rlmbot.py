from discord.ext import commands
from cachecontrol import CacheControl
from collections import Counter
from terminaltables import AsciiTable
from utils import *
from dateutil.parser import *
from dateutil.utils import today
from dateutil.tz import *
from dateutil.relativedelta import *
import json


class RLMBot(commands.Cog):
    def __init__(self, bot_obj):
        self.bot = bot_obj
        self.config = {}
        self.credentials = {}

        self.load_config()

        req_sess = requests.session()
        self.session = CacheControl(req_sess)

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

    @commands.command()
    async def nextrace(self, ctx, division: str = None):
        """Show when the next race is, or when the next race for a particular division is."""
        url = f"{self.config['urls']['base_url']}/api/next-race"
        if division:
            url += f"?division={division}"

        r = self.session.get(url)
        next_race = json.loads(r.content)

        now = datetime.today().utcnow().replace(second=0, microsecond=0)
        start_time = datetime.strptime(next_race["start_time"], "%Y-%m-%dT%H:%M:%SZ")
        delta = str(start_time - now)

        msg = (
            f"**Division**: {next_race['division']}\n"
            f"**Round**: {next_race['round_number']}\n"
            f"**Name**: {next_race['name']}\n"
            f"**When**: {next_race['start_time']} (in {delta})"
        )

        await ctx.send(msg)

    @commands.command()
    async def stats(self, ctx, driver: str, season: str = None, division: str = None):
        """Show stats for a particular driver, optionally filtered by season and division"""
        if len(driver) < 3:
            msg = "Minimum search length is 3 characters"
        else:
            url = f"{self.config['urls']['base_url']}/api/stats?driver={driver.lower()}"
            if season:
                url += f"&season={season.lower()}"
            if division:
                division = self.config["division_map"].get(
                    division.lower(), division.lower()
                )
                url += f"&division={division.lower()}"

            r = self.session.get(url)
            stats = json.loads(r.content)

            if "name" not in stats:
                if "error" in stats:
                    msg = stats["error"]
                else:
                    msg = "Driver not found."
            else:
                qualifying = list_or_none(
                    sort_counter(Counter(stats["qualifying_positions"]))
                )
                race_results = list_or_none(
                    sort_counter(Counter(stats["race_positions"]))
                )
                dnfs = list_or_none(
                    sort_counter(
                        Counter(stats["dnf_reasons"]), convert_int=False, ordinal=False
                    )
                )

                msg = (
                    f"**{stats['name']}**\n"
                    f"{stats['attendance']} races, {stats['points_finishes']} points finishes\n"
                    f"**Qualifying**: {qualifying}\n"
                    f"**Average**: {p.ordinal(int(stats['avg_qualifying']))}\n"
                    f"**Poles**: {stats['pole_positions']}, "
                    f"**Q DSQ**: {stats['qualifying_penalty_dsq']}, "
                    f"**Q Grid**: {stats['qualifying_penalty_grid']}, "
                    f"**Q BoG**: {stats['qualifying_penalty_bog']}, "
                    f"**Q SFP**: {stats['qualifying_penalty_sfp']}\n"
                    f"**Results**: {race_results}\n"
                    f"**Average**: {p.ordinal(int(stats['avg_race']))}\n"
                    f"**Best Finish**: {p.ordinal(stats['best_finish'])}, "
                    f"**Wins**: {stats['wins']}, **Podiums**: {stats['podiums']}, "
                    f"**R DSQ**: {stats['race_penalty_dsq']}, "
                    f"**R Time**: {stats['race_penalty_time']}, "
                    f"**R Pos**: {stats['race_penalty_positions']}, "
                    f"**Penalty Points**: {stats['penalty_points']}\n"
                    f"**DNFs**: {dnfs}\n"
                    f"{stats['laps_completed']} laps completed ({stats['laps_lead']} in the lead), "
                    f"with {stats['fastest_laps']} fastest laps"
                )

        await ctx.send(msg)

    @commands.command()
    async def standings(self, ctx, division, driver: str = None):
        """Show standings for the current season of the specified division."""
        division = self.config["division_map"].get(division.lower(), division.lower())
        if not get_current_season(division, self):
            await ctx.send("No seasons found for division")

        season_id = self.config["division_season"][division.lower()]
        teams_disabled = self.config["season_info"][season_id]["teams_disabled"]

        url = f"{self.config['urls']['base_url']}/api/standings/{season_id}"
        if driver:
            url += f"?driver={driver.lower()}"

        r = self.session.get(url)
        try:
            standings = json.loads(r.content)

            data = [["Pos", "Driver", "Team", "Points"]]

            if teams_disabled:
                data[0].pop(2)

            for pos in standings[0:5]:
                add_row(data, pos, teams_disabled)

            found = False
            if driver:
                try:
                    found = next(
                        iter([d for d in data if driver.lower() in d[1].lower()])
                    )
                except StopIteration:
                    pass

                if not found:
                    try:
                        info = next(
                            iter(
                                [
                                    {"index": i, "details": d}
                                    for i, d in enumerate(standings)
                                    if driver.lower() in d["name"].lower()
                                ]
                            )
                        )
                        prev_pos = standings[info["index"] - 1]
                        if prev_pos["position"] > 6:
                            data.append(["..."])
                        if prev_pos["position"] > 5:
                            add_row(data, prev_pos, teams_disabled)
                        add_row(data, info["details"], teams_disabled)
                        try:
                            next_pos = standings[info["index"] + 1]
                            add_row(data, next_pos, teams_disabled)
                        except IndexError:
                            pass
                    except StopIteration:
                        pass

            table_instance = AsciiTable(data)
            table_instance.inner_column_border = False
            table_instance.outer_border = False
            table_instance.justify_columns[3] = "center"

            season_info = self.config["season_info"][season_id]
            season = f"Name: {season_info['name']} ({season_info['start_date']} to {season_info['end_date']})"
            msg = table_instance.table
        except json.decoder.JSONDecodeError:
            season = "Error"
            msg = "There was an error retrieving the standings"

        await ctx.send(f"```{season}\n\n{msg}```")

    @commands.command()
    async def schedule(self, ctx, division):
        """Show the schedule for the current season of the specified division."""
        division = self.config["division_map"].get(division.lower(), division.lower())
        if not get_current_season(division, self):
            await ctx.send("No seasons found for division")

        season_id = self.config["division_season"][division.lower()]

        url = f"{self.config['urls']['base_url']}/api/races?season={season_id}"
        r = self.session.get(url)
        try:
            schedule = json.loads(r.content)

            data = [["Round", "Name", "Start Time"]]

            this_day = today(tzinfo=tzutc())
            for event in schedule:
                start_time = parse(event["start_time"]).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                delta = format_delta(relativedelta(start_time, this_day))
                data.append(
                    [
                        event["round_number"],
                        event["name"],
                        start_time.strftime("%a, %d %b %Y"),
                        delta,
                    ]
                )

            table_instance = AsciiTable(data)
            table_instance.inner_column_border = False
            table_instance.outer_border = False

            season_info = self.config["season_info"][season_id]
            season = f"Name: {season_info['name']} ({season_info['start_date']} to {season_info['end_date']})"
            msg = table_instance.table
        except json.decoder.JSONDecodeError:
            season = "Error"
            msg = "There was an error retrieving the schedule"

        await ctx.send(f"```{season}\n\n{msg}```")

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
        """Show the F1 fantasy table."""
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
                        entry["user"],
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

    @commands.command()
    async def fantasy(self, ctx):
        await self._show_fantasy(ctx)

    @commands.command()
    async def fantasy_result(self, ctx):
        league = self._find_league(ctx)

        if league:
            with open(f"{league}-details.json") as infile:
                details = json.load(infile)

            player = self._find_player(ctx)

            headers = ["Name", "Turbo", "Points", "Price", "Picked %"]
            data = [headers]
            for index, entry in details[str(player)].items():
                data.append(
                    [
                        entry["name"],
                        "Yes" if entry["turbo"] else "No",
                        entry["score"],
                        entry["price"],
                        entry["picked"]
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
            msg = f"League {league} not found."

        await ctx.send(msg)

    @commands.command(hidden=True)
    async def fantasy_set(self, ctx, league_id, tag):
        self.config['fantasy'][str(ctx.guild.id)] = {
            "tag": tag,
            "f1_id": league_id,
            "players": {}
        }

        self.save_config()

        await ctx.send(f'{tag} set to this server.')

    @commands.command()
    async def fantasy_update(self, ctx):
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

    @commands.command(hidden=True)
    async def parrot(self, ctx, guild, channel, msg):
        try:
            guild_obj = next(iter([x for x in ctx.bot.guilds if x.name == guild]))
            if guild_obj:
                channel_obj = next(iter([x for x in guild_obj.channels if x.name == channel]))
                if channel_obj:
                    msg = find_emojis(msg, ctx.bot)
                    await channel_obj.send(msg)
        except StopIteration:
            await ctx.send(f"Guild '{guild}' or channel '{channel}' not found")
