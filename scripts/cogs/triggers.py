from scripts import settings
import discord
from discord.ext import commands, tasks

def setup(bot: commands.Bot):
    bot.add_cog(commands_triggers(bot))

class commands_triggers(commands.Cog):
    def __init__(self, bot: commands.Cog):
        self.bot = bot