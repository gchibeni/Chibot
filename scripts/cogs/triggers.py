from scripts import settings, voice
import discord
from discord.ext import commands
from discord.app_commands import default_permissions, describe, dm_only, guild_only, command, Range

async def setup(bot: commands.Bot):
    await bot.add_cog(commands_triggers(bot))

class commands_triggers(commands.Cog):
    def __init__(self, bot: commands.Cog):
        self.bot = bot