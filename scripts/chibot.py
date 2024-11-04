import discord
from discord.ext import commands
import scripts.events as events

# Get and read bot token.
with open('./token.secret') as f:
    token = f.read().strip()

intents = discord.Intents.all()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

events.bot_events(bot)

bot.run(token)