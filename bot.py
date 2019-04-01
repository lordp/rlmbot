from discord.ext import commands
from cogs.rlmbot import RLMBot

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("!"), description="RLM Bot"
)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")


bot.add_cog(RLMBot(bot))
bot.run("TOKEN", reconnect=True)
