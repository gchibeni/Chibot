from scripts import settings, voice
import discord
from discord.ext import commands
from discord.app_commands import default_permissions, describe, dm_only, guild_only, command, Range
from discord.ui import Button, View, Select, Modal, TextInput
from datetime import time, datetime, timezone
import os
from typing import List

#region Global

editing_say = {} # All users editing "say" messages.

#endregion

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
        global editing_say
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
        if ctx.user.id in editing_say:
            # Fetch variables.
            view = SaySettingsView()
            original:discord.Message = editing_say[ctx.user.id]["message"]
            now = datetime.now(timezone.utc)
            age_in_seconds = (now - original.created_at).total_seconds()
            # Check if builder didn't expired and regenerate builder.
            try:
                if (age_in_seconds < 900):
                    await original.delete()
                    content:str = editing_say[ctx.user.id]["content"]
                    embed:discord.Embed = editing_say[ctx.user.id]["embed"]
                    attachments:List[discord.Attachment] = editing_say[ctx.user.id]["attachments"]
                    files = []
                    for att in attachments:
                        files.append(await att.to_file())
                    interaction = await ctx.followup.send(view=view, content=content, embed=embed, files=files)
                    editing_say[ctx.user.id]["message"] = interaction
                    return
                else:
                    # Delete expired builder and continue to new builder.
                    await original.delete()
                    editing_say.pop(ctx.user.id)
            except:
                editing_say.pop(ctx.user.id)
        # Show message builder.
        view = SaySettingsView()
        interaction = await ctx.followup.send(view=view, ephemeral=True)
        editing_say[ctx.user.id] = { "message":interaction, "content":None, "embed":None, "attachments":[] }
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
            if ctx.user.id in editing_say:
                try:
                    original:discord.Message = editing_say[ctx.user.id]["message"]
                    now = datetime.now(timezone.utc)
                    age_in_seconds = (now - original.created_at).total_seconds()
                    # Check if builder didn't expired and attach.
                    if (age_in_seconds < 900):
                        # Send attached files to message editor.
                        editing_say[ctx.user.id]["attachments"] = attachments
                        await ctx.delete_original_response()
                        await original.edit(attachments=files)
                        return
                    else:
                        # Delete expired builder and continue.
                        await original.delete()
                        editing_say.pop(ctx.user.id)
                except:
                    editing_say.pop(ctx.user.id)
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

#region Elements

class SaySettingsView(View):
    def __init__(self, warning:str = None, **kwargs):
        super().__init__(**kwargs)
        global editing_say
        # Initialize elements.
        if warning is not None:
            warning_button = Button(label=warning, style=discord.ButtonStyle.grey, row=1, disabled=True)
            self.add_item(warning_button)
        message_button = Button(label=settings.Localize("lbl_say_message"), style=discord.ButtonStyle.grey, row=3)
        embed_button = Button(label=settings.Localize("lbl_say_embed"), style=discord.ButtonStyle.grey, row=3)
        files_button = Button(label=settings.Localize("lbl_say_files"), style=discord.ButtonStyle.grey, row=3)
        cancel_button = Button(label="🛑", style=discord.ButtonStyle.red, row=2)
        display_button = Button(label=settings.Localize("lbl_say_title"), style=discord.ButtonStyle.grey, row=2, disabled=True)
        send_button = Button(label="✅", style=discord.ButtonStyle.green, row=2)
        # Function callbacks.
        async def message_callback(interaction:discord.Interaction):
            await interaction.response.send_modal(SayMessageModal(title=settings.Localize("mdl_say_title")))
            ...      
        async def embed_callback(interaction:discord.Interaction):
            await interaction.response.edit_message(view=SayEmbeddedView())
            ...
        async def files_callback(interaction:discord.Interaction):
            await interaction.response.edit_message(view=SayFilesView())
            ...
        async def cancel_callback(interaction:discord.Interaction):
            try:
                message:discord.Message = editing_say[interaction.user.id]["message"]
                # Stop editing.
                editing_say.pop(interaction.user.id)
                # Delete original message.
                await message.delete()
            except:
                await interaction.response.defer()
                ...
        async def send_callback(interaction:discord.Interaction):
            try:
                # Fetch values.
                original:discord.Message = editing_say[interaction.user.id]["message"]
                content:str = editing_say[interaction.user.id]["content"]
                embed:discord.Embed = editing_say[interaction.user.id]["embed"]
                attachments:List[discord.Attachment] = editing_say[interaction.user.id]["attachments"]
                if content or embed or attachments:
                    # Stop editing.
                    editing_say.pop(interaction.user.id)
                    # Disable buttons.
                    message_button.disabled = embed_button.disabled = files_button.disabled = True
                    cancel_button.disabled = send_button.disabled = True
                    # Disable everything before interaction is blocked.
                    await original.delete()
                    # Delete message builder.
                    files = []
                    for att in attachments:
                        files.append(await att.to_file())
                    # Send the builded message.
                    await interaction.channel.send(content=content, embed=embed, files=files)
                else:
                    await interaction.response.edit_message(view=SaySettingsView(settings.Localize("lbl_empty_content")))
            except:
                await interaction.response.defer()
                ...
        # Set callbacks.
        message_button.callback = message_callback
        embed_button.callback = embed_callback
        files_button.callback = files_callback
        cancel_button.callback = cancel_callback
        send_button.callback = send_callback
        # Add items.
        self.add_item(cancel_button)
        self.add_item(display_button)
        self.add_item(send_button)
        self.add_item(message_button)
        self.add_item(embed_button)
        self.add_item(files_button)

class SayFilesView(View):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        global editing_say
        # Initialize elemenets.
        return_button = Button(label="⬅️", style=discord.ButtonStyle.blurple, row=1)
        display_button = Button(label=settings.Localize("lbl_say_files"), style=discord.ButtonStyle.grey, row=1, disabled=True)
        clear_button = Button(label=settings.Localize("lbl_say_clear"), style=discord.ButtonStyle.grey, row=1)
        instruction_button = Button(label=settings.Localize("lbl_files_instruction"), style=discord.ButtonStyle.grey, row=2, disabled=True)
        
        # Function callbacks.
        async def return_callback(interaction:discord.Interaction):
            await interaction.response.edit_message(view=SaySettingsView())
        async def clear_callback(interaction:discord.Interaction):
            editing_say[interaction.user.id]["attachments"] = []
            await interaction.response.edit_message(attachments=[])
        # Set callbacks.
        return_button.callback = return_callback
        clear_button.callback = clear_callback
        # Add items.
        self.add_item(return_button)
        self.add_item(display_button)
        self.add_item(clear_button)
        self.add_item(instruction_button)
        ...

class SayMessageModal(Modal):
    message_input = TextInput(style=discord.TextStyle.long, label=settings.Localize("mdl_say_label"), required=False, max_length=2000)
    async def on_submit(self, interaction:discord.Interaction):
        content = self.message_input.value
        editing_say[interaction.user.id]["content"] = content
        await interaction.response.edit_message(content=content, view=SaySettingsView())

class SayEmbeddedView(View):
    def __init__(self, warning:str = None, **kwargs):
        super().__init__(**kwargs)
        global editing_say
        if warning is not None:
            warning_button = Button(label=warning, style=discord.ButtonStyle.grey, row=1, disabled=True)
            self.add_item(warning_button)
        elif warning:
            self.remove_item(warning_button)
        # Initialize elemenets.
        return_button = Button(label="⬅️", style=discord.ButtonStyle.blurple, row=2)
        display_button = Button(label=settings.Localize("lbl_say_embed"), style=discord.ButtonStyle.grey, row=2, disabled=True)
        clear_button = Button(label=settings.Localize("lbl_say_clear"), style=discord.ButtonStyle.grey, row=2)
        color_select = Select(placeholder=settings.Localize("lbl_embed_color"), row=3)
        author_button = Button(label=settings.Localize("lbl_embed_author"), style=discord.ButtonStyle.grey, row=4)
        content_button = Button(label=settings.Localize("lbl_embed_content"), style=discord.ButtonStyle.grey, row=4)
        footer_button = Button(label=settings.Localize("lbl_embed_footer"), style=discord.ButtonStyle.grey, row=4)
        # Initialize color options.
        color_select.add_option(label=settings.Localize("lbl_color_default"), value="0")
        color_select.add_option(label=settings.Localize("lbl_color_red"), value="#dd2e44")
        color_select.add_option(label=settings.Localize("lbl_color_orange"), value="#f4900c")
        color_select.add_option(label=settings.Localize("lbl_color_yellow"), value="#fdcb58")
        color_select.add_option(label=settings.Localize("lbl_color_green"), value="#78b159")
        color_select.add_option(label=settings.Localize("lbl_color_blue"), value="#55acee")
        color_select.add_option(label=settings.Localize("lbl_color_purple"), value="#aa8ed6")
        color_select.add_option(label=settings.Localize("lbl_color_brown"), value="#664736")
        color_select.add_option(label=settings.Localize("lbl_color_black"), value="#131313")
        color_select.add_option(label=settings.Localize("lbl_color_white"), value="#eeeeee")
        # Function callbacks.
        async def return_callback(interaction:discord.Interaction):
            await interaction.response.edit_message(view=SaySettingsView())
        async def clear_callback(interaction:discord.Interaction):
            editing_say[interaction.user.id]["embed"] = None
            await interaction.response.edit_message(embed=None)
        async def color_callback(interaction:discord.Interaction):
            # Fetch and clean.
            embedded:discord.Embed = editing_say[interaction.user.id]["embed"]
            embedded = settings.EmbedClean(embedded)
            # Change values.
            color_value = int(color_select.values[0].lstrip("#"), 16)
            embedded.color = color_value if color_value != 0 else None
            # Save and send preview embedded.
            editing_say[interaction.user.id]["embed"] = embedded
            preview_embedded = settings.EmbedClean(embedded, True)
            await interaction.response.edit_message(embed=preview_embedded)
        async def author_callback(interaction:discord.Interaction):
            #editing_say[interaction.user.id]["embed"] = embedded
            await interaction.response.send_modal(EmbedAuthorModal(title=settings.Localize("mdl_say_title")))
        async def content_callback(interaction:discord.Interaction):
            #editing_say[interaction.user.id]["embed"] = embedded
            await interaction.response.send_modal(EmbedContentModal(title=settings.Localize("mdl_say_title")))
        async def footer_callback(interaction:discord.Interaction):
            #editing_say[interaction.user.id]["embed"] = embedded
            await interaction.response.send_modal(EmbedFooterModal(title=settings.Localize("mdl_say_title")))
        # Set callbacks.
        return_button.callback = return_callback
        clear_button.callback = clear_callback
        color_select.callback = color_callback
        author_button.callback = author_callback
        content_button.callback = content_callback
        footer_button.callback = footer_callback
        # Add items.
        self.add_item(return_button)
        self.add_item(display_button)
        self.add_item(clear_button)
        self.add_item(color_select)
        self.add_item(author_button)
        self.add_item(content_button)
        self.add_item(footer_button)
    ...

class EmbedAuthorModal(Modal):
    # Author, Website, Avatar URL
    author_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("mdl_embed_author_name"), required=False, max_length=256)
    website_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("mdl_embed_author_website"), required=False, max_length=1000)
    avatar_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("mdl_embed_author_image"), required=False, max_length=1000)
    async def on_submit(self, interaction:discord.Interaction):
        # Fetch and clean.
        embedded:discord.Embed = editing_say[interaction.user.id]["embed"]
        embedded = settings.EmbedClean(embedded)
        # Simplify variables.
        author = self.author_input.value
        website = self.website_input.value
        avatar = self.avatar_input.value
        # Change values.
        embedded.set_author(name=author, url=website, icon_url=avatar)
        # Check errors.
        warning = None
        if website and not settings.GetHTTP(website):
            warning = settings.Localize("lbl_invalid_url")
        if avatar and not settings.GetHTTP(avatar):
            warning = settings.Localize("lbl_invalid_image_url")
        # Save and send preview embedded.
        editing_say[interaction.user.id]["embed"] = embedded
        preview_embedded = settings.EmbedClean(embedded, True)
        await interaction.response.edit_message(embed=preview_embedded, view=SayEmbeddedView(warning))
        ...

class EmbedContentModal(Modal):
    # Title, Description, Website, Image URL, Thumbnail URL
    title_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("mdl_embed_title"), required=False, max_length=256)
    description_input = TextInput(style=discord.TextStyle.long, label=settings.Localize("mdl_embed_description"), required=False, max_length=4000)
    website_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("mdl_embed_website"), required=False, max_length=1000)
    image_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("mdl_embed_image"), required=False, max_length=1000)
    thumbnail_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("mdl_embed_thumbnail"), required=False, max_length=1000)
    async def on_submit(self, interaction:discord.Interaction):
        # Fetch and clean.
        embedded:discord.Embed = editing_say[interaction.user.id]["embed"]
        embedded = settings.EmbedClean(embedded)
        # Simplify variables.
        title = self.title_input.value
        description = self.description_input.value
        url = self.website_input.value
        image = self.image_input.value
        thumbnail = self.thumbnail_input.value
        # Change values.
        embedded.title = title
        embedded.description = description
        embedded.url = url
        embedded.set_image(url=image)
        embedded.set_thumbnail(url=thumbnail)
        # Check errors.
        warning = None
        if url and not settings.GetHTTP(url):
            warning = settings.Localize("lbl_invalid_url")
        if image and not settings.GetHTTP(image, True) or thumbnail and not settings.GetHTTP(thumbnail, True):
            warning = settings.Localize("lbl_invalid_image_url")
        # Save and send preview embedded.
        editing_say[interaction.user.id]["embed"] = embedded
        preview_embedded = settings.EmbedClean(embedded, True)
        await interaction.response.edit_message(embed=preview_embedded, view=SayEmbeddedView(warning))
        ...

class EmbedFooterModal(Modal):
    # Content, Icon URL
    content_input = TextInput(style=discord.TextStyle.long, label=settings.Localize("mdl_embed_footer"), required=False, max_length=2000)
    icon_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("mdl_embed_footer_icon"), required=False, max_length=1000)
    async def on_submit(self, interaction:discord.Interaction):
        # Fetch and clean.
        embedded:discord.Embed = editing_say[interaction.user.id]["embed"]
        embedded = settings.EmbedClean(embedded)
        # Simplify variables.
        content = self.content_input.value
        icon_url = self.icon_input.value
        # Change values.
        embedded.set_footer(text=content, icon_url=icon_url)
        # Check errors.
        warning = None
        if icon_url and not settings.GetHTTP(icon_url, True):
            warning = settings.Localize("lbl_invalid_image_url")
        # Save and send preview embedded.
        editing_say[interaction.user.id]["embed"] = embedded
        preview_embedded = settings.EmbedClean(embedded, True)
        await interaction.response.edit_message(embed=preview_embedded, view=SayEmbeddedView(warning))
        ...

#endregion