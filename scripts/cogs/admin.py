from scripts import settings, voice
import discord
from discord.ext import commands
from discord.app_commands import default_permissions, describe, dm_only, guild_only, command, Range
from datetime import time
import os

async def setup(bot: commands.Bot):
    await bot.add_cog(commands_admin(bot))

class commands_admin(commands.Cog):
    def __init__(self, bot: commands.Cog):
        self.bot = bot

    # SAY ────────────────
    @command(name="say", description = "Force the bot to send the specified message.")
    @default_permissions(manage_guild=True)
    @guild_only()
    @describe(message="Message to be transmitted.")
    @describe(attachment1="First attached files or images.")
    @describe(attachment2="Second attached files or images.")
    @describe(attachment3="Third attached files or images.")
    @describe(attachment4="Forth attached files or images.")
    async def say(self, ctx:discord.Interaction, message:str, attachment1: discord.Attachment = None, attachment2: discord.Attachment = None, attachment3: discord.Attachment = None, attachment4: discord.Attachment = None):
        await ctx.defer(ephemeral=True)
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
        # Send message with or without attatchments.
        if len(files) > 0:
            await ctx.send(message if message != "." else "", files=files)
        elif message:
            await ctx.send(message)
        await ctx.followup.send(settings.Localize("message_sent"), ephemeral=True, delete_after=1)
        
    # PURGE ────────────────
    @command(name="purge", description = "Delete a specified number of messages in order in a channel.")
    @default_permissions(manage_guild=True, manage_messages=True)
    @guild_only()
    @describe(quantity="Quantity of messages to be purged")
    @describe(force="Force delete past marked messages")
    async def purge(self, ctx: discord.Interaction, quantity:Range[int,1,1000] = 1, force:bool = False):
        await ctx.defer(ephemeral=True)
        # Common variables.
        channel : discord.TextChannel = ctx.channel
        # Check function.
        def check_favorite(message:discord.Message):
            isPinned = message.pinned
            isSaved = False
            isMarked = False
            for reaction in message.reactions:
                if (reaction.emoji == '⭐') or (reaction.emoji == '🍞'): isSaved = True
                if (reaction.emoji == '🚩') and not force: isMarked = True
            deleteMessage = not isPinned and not isSaved and not isMarked
            return deleteMessage
        # Purge messages.
        if (quantity <= 0):
            quantity = 1
        await channel.purge(limit=quantity, check=check_favorite)
        # Send purging confirmation.
        await ctx.followup.send(settings.Localize("purged_messages", quantity))

    # ALLOW PULL ────────────────
    @command(name="allowpull", description = "-")
    @default_permissions(administrator=True)
    @guild_only()
    async def allow_pull(self, ctx: discord.Interaction):
        await ctx.response.send_message("Allow Pull", ephemeral=True)

    # TODO: Change this to /theme add
    # ADD ICON ────────────────
    @command(name="addicon", description = "-")
    @default_permissions(administrator=True)
    @guild_only()
    async def add_icon(self, ctx: discord.Interaction, day:int, month:int, name:str, icon:discord.Attachment, sleep_icon:discord.Attachment = None, wake_hour:int = None, sleep_hour:int = None):
        # Initialize variables.
        icon_data = { "icon": name }
        allowedTypes = {"image/png", "image/jpeg", "image/jpg", "image/gif"}
        valid_date = settings.IsValidDate(day, month, 2024)
        if not wake_hour: wake_hour = 8
        if not sleep_hour: sleep_hour = 22
        # Check parameters.
        if not valid_date:
            await ctx.response.send_message(settings.Localize("invalid_date"), ephemeral=True)
            return
        if len(name) < 3 and len(name) > 35:
            await ctx.response.send_message(settings.Localize("invalid_name_lenght"), ephemeral=True)
            return
        if sleep_icon:
            if not wake_hour:
                await ctx.response.send_message(settings.Localize("requires_awake_hour"), ephemeral=True)
                return
            if not sleep_hour:
                await ctx.response.send_message(settings.Localize("requires_sleep_hour"), ephemeral=True)
                return
            if (wake_hour < 0 and wake_hour > 24) or (sleep_hour < 0 and sleep_hour > 24):
                await ctx.response.send_message(settings.Localize("invalid_hour"), ephemeral=True)
                return
        if (wake_hour or sleep_hour) and not sleep_icon:
            await ctx.response.send_message(settings.Localize("requires_icon"), ephemeral=True)
            return
        if icon.content_type not in allowedTypes or sleep_icon.content_type not in allowedTypes:
            await ctx.response.send_message(settings.Localize("invalid_image_type"), ephemeral=True)
            return
        # Send successful message.
        await ctx.response.send_message(settings.Localize("guild_icon_added"), ephemeral=True)
        # Create guild icons folder.
        path = f'./guilds/{ctx.guild_id}/icons'
        os.makedirs(path, exist_ok=True)
        # Save icon file.
        icon_file_name, icon_file_extension = os.path.splitext(icon.filename)
        icon_path = os.path.join(path, f'{name}{icon_file_extension}')
        await icon.save(icon_path)
        # Save sleep icon file.
        if sleep_icon:
            sleep_icon_file_name, sleep_icon_file_extension = os.path.splitext(sleep_icon.filename)
            sleep_icon_path = os.path.join(path, f'{name}_sleep{sleep_icon_file_extension}')
            await sleep_icon.save(sleep_icon_path)
            icon_data = { "icon": name, "wake":wake_hour, "sleep":sleep_hour }
        # Add avatar icon to guild settings.
        settings.SetInfo(ctx.guild_id, f"icons/{day}-{month}", icon_data)
        