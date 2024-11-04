from scripts import settings
import discord
from discord.ext import commands, tasks
from discord import app_commands

async def setup(bot: commands.Bot):
    print("Cog added - Triggers")
    await bot.add_cog(commands_triggers(bot))

class commands_triggers(commands.Cog):
    def __init__(self, bot: commands.Cog):
        self.bot = bot