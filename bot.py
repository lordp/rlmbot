import discord
from discord.ext import commands
from cogs.rlmbot import RLMBot
from cogs.f1fantasy import F1Fantasy

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or("+"),
    description="RLM Bot",
    intents=intents
)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")


bot.add_cog(RLMBot(bot))
bot.add_cog(F1Fantasy(bot))
bot.run("TOKEN", reconnect=True)
