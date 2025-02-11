from scripts import settings, voice, elements
import discord
from discord.ext import commands
from discord.app_commands import default_permissions, describe, dm_only, guild_only, command, Range
from discord.ui import Button, View, Select, Modal, TextInput
from datetime import time, datetime, timezone
import os
from typing import List

#region Initialization

async def setup(bot: commands.Bot):
    await bot.add_cog(commands_admin(bot))

class commands_admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

#endregion

#region Commands

    # SAY ────────────────
    @command(name="say", description=settings.Localize("cmd_say"), )
    @default_permissions(manage_guild=True)
    @guild_only()
    @describe(message=settings.Localize("cmd_say_message"))
    @describe(attachment=settings.Localize("cmd_say_attachment"))
    async def say(self, ctx:discord.Interaction, message:str = "", attachment: discord.Attachment = None):
        await ctx.response.defer(ephemeral=True)
        if message or attachment:
            # Quick send.
            files = []
            if attachment:
                file = await attachment.to_file()
                files.append(file)
            await ctx.delete_original_response()
            await ctx.channel.send(message, files=files)
            return
        if ctx.user.id in settings.editing_say:
            # Fetch variables.
            view = elements.SaySettingsView()
            original:discord.Message = settings.editing_say[ctx.user.id]["message"]
            now = datetime.now(timezone.utc)
            age_in_seconds = (now - original.created_at).total_seconds()
            # Check if builder didn't expired and regenerate builder.
            try:
                if (age_in_seconds < 900):
                    await original.delete()
                    content:str = settings.editing_say[ctx.user.id]["content"]
                    embed:discord.Embed = settings.editing_say[ctx.user.id]["embed"]
                    attachments:List[discord.Attachment] = settings.editing_say[ctx.user.id]["attachments"]
                    files = []
                    for att in attachments:
                        files.append(await att.to_file())
                    interaction = await ctx.followup.send(view=view, content=content, embed=embed, files=files)
                    settings.editing_say[ctx.user.id]["message"] = interaction
                    return
                else:
                    # Delete expired builder and continue to new builder.
                    await original.delete()
                    settings.editing_say.pop(ctx.user.id)
            except:
                settings.editing_say.pop(ctx.user.id)
        # Show message builder.
        view = elements.SaySettingsView()
        interaction = await ctx.followup.send(view=view, ephemeral=True)
        settings.editing_say[ctx.user.id] = { "message":interaction, "content":None, "embed":None, "attachments":[] }
        ...

    @command(name="attach", description=settings.Localize("cmd_attach"))
    @default_permissions(manage_guild=True)
    @guild_only()
    @describe(attachment1=settings.Localize("lbl_attached_file"))
    @describe(attachment2=settings.Localize("lbl_attached_file"))
    @describe(attachment3=settings.Localize("lbl_attached_file"))
    @describe(attachment4=settings.Localize("lbl_attached_file"))
    async def attach(self, ctx:discord.Interaction, attachment1: discord.Attachment, attachment2: discord.Attachment = None, attachment3: discord.Attachment = None, attachment4: discord.Attachment = None):
        await ctx.response.defer(ephemeral=True)
        files = []
        attachments = []
        if attachment1:
            file = await attachment1.to_file()
            files.append(file)
            attachments.append(attachment1)
        if attachment2:
            file = await attachment2.to_file()
            files.append(file)
            attachments.append(attachment2)
        if attachment3:
            file = await attachment3.to_file()
            files.append(file)
            attachments.append(attachment3)
        if attachment4:
            file = await attachment4.to_file()
            files.append(file)
            attachments.append(attachment4)
        if len(files) > 0:
            # Send attachment in a separate message if not editing.
            if ctx.user.id in settings.editing_say:
                try:
                    original:discord.Message = settings.editing_say[ctx.user.id]["message"]
                    now = datetime.now(timezone.utc)
                    age_in_seconds = (now - original.created_at).total_seconds()
                    # Check if builder didn't expired and attach.
                    if (age_in_seconds < 900):
                        # Send attached files to message editor.
                        settings.editing_say[ctx.user.id]["attachments"] = attachments
                        await ctx.delete_original_response()
                        await original.edit(attachments=files)
                        return
                    else:
                        # Delete expired builder and continue.
                        await original.delete()
                        settings.editing_say.pop(ctx.user.id)
                except:
                    settings.editing_say.pop(ctx.user.id)
            await ctx.delete_original_response()
            await ctx.channel.send(files=files)
            return
            ...

    # PURGE ────────────────
    @command(name="purge", description=settings.Localize("cmd_purge"))
    @default_permissions(manage_guild=True, manage_messages=True)
    @guild_only()
    @describe(quantity=settings.Localize("cmd_purge_quantity"))
    @describe(force=settings.Localize("cmd_purge_force"))
    async def purge(self, ctx: discord.Interaction, quantity:Range[int,1,250] = 1, force:bool = False):
        await ctx.response.defer(ephemeral=True)
        del_messages:list[discord.Message] = []
        # Check messages.
        async for message in ctx.channel.history(limit=quantity):
            isPinned = message.pinned
            isSaved = False
            isMarked = False
            for reaction in message.reactions:
                if (reaction.emoji == '⭐'): isSaved = True
                if (reaction.emoji == '🚩') and not force: isMarked = True
            deleteMessage = not isPinned and not isSaved and not isMarked
            if deleteMessage:
                del_messages.append(message)
            elif isMarked:
                break
        # Purge messages.
        #await ctx.channel.purge(limit=quantity, check=check_favorite, bulk=True)
        await ctx.channel.delete_messages(del_messages)
        # Send purging confirmation.
        await ctx.followup.send(settings.Localize("lbl_purge_ended", quantity))

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

#endregion