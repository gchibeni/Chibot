from scripts import settings
import discord
from discord.ext import commands, tasks
from discord import app_commands

client:commands.Bot = None

async def setup(bot: commands.Bot):
    client = bot
    await bot.add_cog(commands_admin(bot))

class commands_admin(commands.Cog):
    def __init__(self, bot: commands.Cog):
        self.bot = bot

    # SAY ────────────────
    @app_commands.command(name="say", description = "Force the bot to send the specified message.")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.describe(message="Message to be transmitted.", attachment1="First attached files or images.", attachment2="Second attached files or images.", attachment3="Third attached files or images.")
    async def say(self, ctx:discord.Interaction, message:str = "", attachment1: discord.Attachment = None, attachment2: discord.Attachment = None, attachment3: discord.Attachment = None):
        await ctx.response.defer(thinking=True, ephemeral=True)
        # Prepare attatchment files.
        files = []
        if attachment1:
            file = await attachment1.to_file()
            files.append(file)
        if attachment2:
            file = await attachment2.to_file()
            files.append(file)
        if attachment3:
            file = await attachment3.to_file()
            files.append(file)
        await ctx.delete_original_response()
        # Send message with or without attatchments.
        if len(files) > 0:
            await ctx.channel.send(message if message != "." else "", files=files)
            return
        if message:
            await ctx.channel.send(message)

    @say.error
    async def say_error(self, ctx: discord.Interaction, error):
        if isinstance(error, app_commands.errors.MissingPermissions):
            await ctx.response.send_message("You need to be an administrator to use this command.", ephemeral=True)
        if isinstance(error, app_commands.errors.CheckFailure):
            await ctx.response.send_message("You need to be an administrator to use this command.", ephemeral=True)

    # PURGE ────────────────
    @app_commands.command(name="purge", description = "Delete a specified number of messages in order in a channel.")
    @app_commands.guild_only()
    async def purge(self, ctx: discord.Interaction, quantity:int, force:bool = False):
        await ctx.response.send_message("Purge", ephemeral=True)

    # ALLOW PULL ────────────────
    @app_commands.command(name="allowpull", description = "-")
    @app_commands.guild_only()
    @app_commands.describe(allow="Toggle pulling.")
    async def allow_pull(self, ctx: discord.Interaction, allow:bool = True):
        await ctx.response.send_message("Allow Pull", ephemeral=True)