from scripts import settings
import discord
from discord.ext import commands, tasks
from discord import app_commands
import scripts.settings as settings

async def setup(bot: commands.Bot):
    print("Cog added - Admin")
    await bot.add_cog(commands_admin(bot))

class commands_admin(commands.Cog):
    def __init__(self, bot: commands.Cog):
        self.bot = bot
    
    # SAY ────────────────
    @app_commands.command(name="say", description = "Force the bot to send the specified message.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(message="Message to be transmitted.", attatchment="Attached files or images.")
    async def say(self, ctx:discord.Interaction, message:str, attatchment:discord.Attachment = None):
        await ctx.response.send_message(message, ephemeral=True)

    # PURGE ────────────────
    @app_commands.command(name="purge", description = "Delete a specified number of messages in order in a channel.")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def purge(self, ctx: discord.Interaction, quantity:int, force:bool = False):
        await ctx.response.send_message("Purge", ephemeral=True)

    # ALLOW PULL ────────────────
    @app_commands.command(name="allowpull", description = "-")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(allow="Toggle pulling.")
    async def allow_pull(self, ctx: discord.Interaction, allow:bool = True):
        await ctx.response.send_message("Allow Pull", ephemeral=True)

