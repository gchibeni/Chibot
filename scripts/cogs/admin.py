from scripts import settings, voice
import discord
from discord.ext import commands
from discord.app_commands import default_permissions, describe, dm_only, guild_only, command, Range
from discord.ui import Button, View, Select, Modal, TextInput
from datetime import time, datetime, timezone
import os
from typing import List

editing_say = {} # All users editing "say" messages.

#region Initialization

async def setup(bot: commands.Bot):
    await bot.add_cog(commands_admin(bot))

class commands_admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

#endregion

#region Commands

    # SAY ────────────────
    @command(name="say", description = "Build and send a message.")
    @default_permissions(manage_guild=True)
    @guild_only()
    @describe(message="Send a quick text only message.")
    @describe(attachment="Attatched file or image.")
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

    @command(name="attach", description = "Force the bot to send the specified message.")
    @default_permissions(manage_guild=True)
    @guild_only()
    @describe(attachment1="First attached file or image.")
    @describe(attachment2="Second attached file or image.")
    @describe(attachment3="Third attached file or image.")
    @describe(attachment4="Fourth attached file or image.")
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
    @command(name="purge", description = "Delete a specified number of messages in order in a channel.")
    @default_permissions(manage_guild=True, manage_messages=True)
    @guild_only()
    @describe(quantity="Quantity of messages to be purged")
    @describe(force="Force delete past marked messages")
    async def purge(self, ctx: discord.Interaction, quantity:Range[int,1,1000] = 1, force:bool = False):
        await ctx.response.defer(ephemeral=True)
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
        message_button = Button(label="MESSAGE", style=discord.ButtonStyle.grey, row=3)
        embed_button = Button(label="EMBED", style=discord.ButtonStyle.grey, row=3)
        files_button = Button(label="FILES", style=discord.ButtonStyle.grey, row=3)
        cancel_button = Button(label="🛑", style=discord.ButtonStyle.red, row=2)
        display_button = Button(label="SAY", style=discord.ButtonStyle.grey, row=2, disabled=True)
        send_button = Button(label="✅", style=discord.ButtonStyle.green, row=2)
        # Function callbacks.
        async def message_callback(interaction:discord.Interaction):
            await interaction.response.send_modal(SayMessageModal(title=settings.Localize("say_message_title")))
            ...      
        async def embed_callback(interaction:discord.Interaction):
            await interaction.response.edit_message(view=SayEmbededView())
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
                    await interaction.response.edit_message(view=SaySettingsView(settings.Localize("error_empty_content")))
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
        display_button = Button(label="FILES", style=discord.ButtonStyle.grey, row=1, disabled=True)
        clear_button = Button(label="CLEAR", style=discord.ButtonStyle.grey, row=1)
        instruction_button = Button(label="Use /attach to add files.", style=discord.ButtonStyle.grey, row=2, disabled=True)
        
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
    message_input = TextInput(style=discord.TextStyle.long, label=settings.Localize("say_m_message_label"), required=False, max_length=2000)
    async def on_submit(self, interaction:discord.Interaction):
        content = self.message_input.value
        editing_say[interaction.user.id]["content"] = content
        await interaction.response.edit_message(content=content, view=SaySettingsView())

class SayEmbededView(View):
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
        display_button = Button(label="EMBED", style=discord.ButtonStyle.grey, row=2, disabled=True)
        clear_button = Button(label="CLEAR", style=discord.ButtonStyle.grey, row=2)
        color_select = Select(placeholder="SELECT COLOR", row=3)
        author_button = Button(label="AUTHOR", style=discord.ButtonStyle.grey, row=4)
        content_button = Button(label="CONTENT", style=discord.ButtonStyle.grey, row=4)
        footer_button = Button(label="FOOTER", style=discord.ButtonStyle.grey, row=4)
        # Initialize color options.
        color_select.add_option(label="🔘 DEFAULT", value="0")
        color_select.add_option(label="🔴 RED", value="#dd2e44")
        color_select.add_option(label="🟠 ORANGE", value="#f4900c")
        color_select.add_option(label="🟡 YELLOW", value="#fdcb58")
        color_select.add_option(label="🟢 GREEN", value="#78b159")
        color_select.add_option(label="🔵 BLUE", value="#55acee")
        color_select.add_option(label="🟣 PURPLE", value="#aa8ed6")
        color_select.add_option(label="🟤 BROWN", value="#664736")
        color_select.add_option(label="⚫ BLACK", value="#131313")
        color_select.add_option(label="⚪ WHITE", value="#eeeeee")
        # Function callbacks.
        async def return_callback(interaction:discord.Interaction):
            await interaction.response.edit_message(view=SaySettingsView())
        async def clear_callback(interaction:discord.Interaction):
            editing_say[interaction.user.id]["embed"] = None
            await interaction.response.edit_message(embed=None)
        async def color_callback(interaction:discord.Interaction):
            # Fetch and clean.
            embeded:discord.Embed = editing_say[interaction.user.id]["embed"]
            embeded = EmbedClean(embeded)
            # Change values.
            color_value = int(color_select.values[0].lstrip("#"), 16)
            embeded.color = color_value if color_value != 0 else None
            # Save and send preview embeded.
            editing_say[interaction.user.id]["embed"] = embeded
            preview_embeded = EmbedClean(embeded, True)
            await interaction.response.edit_message(embed=preview_embeded)
        async def author_callback(interaction:discord.Interaction):
            #editing_say[interaction.user.id]["embed"] = embeded
            await interaction.response.send_modal(EmbedAuthorModal(title=settings.Localize("say_embed_title")))
        async def content_callback(interaction:discord.Interaction):
            #editing_say[interaction.user.id]["embed"] = embeded
            await interaction.response.send_modal(EmbedContentModal(title=settings.Localize("say_embed_title")))
        async def footer_callback(interaction:discord.Interaction):
            #editing_say[interaction.user.id]["embed"] = embeded
            await interaction.response.send_modal(EmbedFooterModal(title=settings.Localize("say_embed_title")))
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
    ...

class EmbedAuthorModal(Modal):
    # Author, Website, Avatar URL
    author_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("embed_m_author_name_label"), required=False, max_length=256)
    website_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("embed_m_author_website_label"), required=False, max_length=1000)
    avatar_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("embed_m_author_avatar_url_label"), required=False, max_length=1000)
    async def on_submit(self, interaction:discord.Interaction):
        # Fetch and clean.
        embeded:discord.Embed = editing_say[interaction.user.id]["embed"]
        embeded = EmbedClean(embeded)
        # Change values.
        embeded.set_author(name="", url="", icon_url="")

        # Save and send preview embeded.
        editing_say[interaction.user.id]["embed"] = embeded
        preview_embeded = EmbedClean(embeded)
        await interaction.response.edit_message(embed=preview_embeded, view=SayEmbededView("warning"))
        ...

class EmbedContentModal(Modal):
    # Title, Description, Website, Image URL, Thumbnail URL
    title_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("embed_m_title_label"), required=False, max_length=256)
    description_input = TextInput(style=discord.TextStyle.long, label=settings.Localize("embed_m_description_label"), required=False, max_length=4000)
    website_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("embed_m_website_label"), required=False, max_length=1000)
    image_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("embed_m_image_label"), required=False, max_length=1000)
    thumbnail_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("embed_m_thumbnail_label"), required=False, max_length=1000)
    async def on_submit(self, interaction:discord.Interaction):
        # Fetch and clean.
        embeded:discord.Embed = editing_say[interaction.user.id]["embed"]
        embeded = EmbedClean(embeded)
        # Change values.
        embeded.title = self.title_input.value
        embeded.description = self.description_input.value
        embeded.url = self.website_input.value if settings.IsValidUrl(self.website_input.value) else None
        embeded.set_image(url=self.image_input.value if settings.IsValidUrlImage(self.image_input.value) else None)
        embeded.set_thumbnail(url=self.thumbnail_input.value if settings.IsValidUrlImage(self.thumbnail_input.value) else None)
        # Check errors.
        # Save and send preview embeded.
        editing_say[interaction.user.id]["embed"] = embeded
        preview_embeded = EmbedClean(embeded)
        warning = "test"
        await interaction.response.edit_message(embed=preview_embeded, view=SayEmbededView(warning or None))
        ...

class EmbedFooterModal(Modal):
    # Content, Icon URL
    content_input = TextInput(style=discord.TextStyle.long, label=settings.Localize("embed_m_footer_content_label"), required=False, max_length=2000)
    icon_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("embed_m_footer_icon_label"), required=False, max_length=1000)
    async def on_submit(self, interaction:discord.Interaction):
        # Fetch and clean.
        embeded:discord.Embed = editing_say[interaction.user.id]["embed"]
        embeded = EmbedClean(embeded)
        # Simplify variables.
        content = self.content_input.value
        icon_url = self.icon_input.value
        # Check errors.
        warning = None
        if icon_url and not settings.GetHTTP(icon_url):
            warning = settings.Localize("error_invalid_url")
        # Change values.
        embeded.set_footer(text=content, icon_url=icon_url)
        # Save and send preview embeded.
        editing_say[interaction.user.id]["embed"] = embeded
        preview_embeded = EmbedClean(embeded)
        await interaction.response.edit_message(embed=preview_embeded, view=SayEmbededView(warning))
        ...

def EmbedClean(embed:discord.Embed, check_valid:bool = False) -> discord.Embed:
    # Fetch or generate embed.
    new_embed = discord.Embed()
    embed = embed or discord.Embed()
    # Copy values.
    new_embed.title = embed.title or ""
    new_embed.description = embed.description or ""
    new_embed.url = embed.url or None
    new_embed.colour = embed.colour or None
    new_embed.set_image(url=embed.image.url or None)
    new_embed.set_thumbnail(url=embed.thumbnail.url or None)
    new_embed.set_footer(text=embed.footer.text or "", icon_url=embed.footer.icon_url or None)
    new_embed.set_author(name=embed.author.name or "", url=embed.author.url or None, icon_url=embed.author.icon_url or None)
    # Check and save.
    if check_valid and not settings.IsValidEmbed(new_embed):
        new_embed.description = "ㅤ"
    return new_embed

#endregion