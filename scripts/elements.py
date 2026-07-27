from scripts import settings, voice
import discord
from discord.ext import commands
from discord import app_commands
from discord.app_commands import default_permissions, describe, dm_only, guild_only, command, Range
from discord.ui import Button, View, Select, Modal, TextInput
import random
import time
from typing import List

#region Utils

class AnonModal(Modal):
    def __init__(self, ctx:discord.Interaction, user:discord.User, **kwargs):
        super().__init__(**kwargs)
        self.ctx = ctx
        self.user = user
        if user is None:
            target_name = ctx.channel.name
            target_id = ""
        else:
            target_name = user.display_name
            target_id = f"(@{user.global_name})" 
        anon_label = settings.Localize("mdl_anon_target", target_name, target_id)
        # Create inputs.
        self.message_input = discord.ui.TextInput(style=discord.TextStyle.long, label=anon_label, required=True, min_length=4, max_length=280)
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
         # Send confirmation.
        await interaction.response.send_message(settings.Localize("lbl_anon_sent"), ephemeral=True)
        embedded = discord.Embed(description=self.message_input.value).set_footer(icon_url='https://i.gifer.com/L7sU.gif', text=settings.Localize("lbl_anon_footer"))
        # Send message anonymously.
        if self.user is None:
            await interaction.channel.send(embed=embedded)
        else:
            await self.user.send(embed=embedded)

#endregion

#region Music permissions

# The slash command whose Integrations permissions gate each music button.
BUTTON_COMMANDS = {
    "play": "play",
    "prev": "prev",
    "next": "next",
    "stop": "stop",
    "clear": "clear",
    "shuffle": "shuffle",
    "loop": "play",
    "download": "download",
    "backward": "scrub",
    "forward": "scrub",
}
_permissions_cache = {}  # guild_id -> (fetched_at, {command_name: overrides})

async def FetchCommandOverrides(bot:commands.Bot, guild:discord.Guild) -> dict:
    """The guild's Integrations overrides for the commands backing music
    buttons, cached for a minute."""
    cached = _permissions_cache.get(guild.id)
    if cached and time.monotonic() - cached[0] < 60:
        return cached[1]
    overrides = {}
    try:
        # Commands are synced per guild, with a global fallback.
        fetched = await bot.tree.fetch_commands(guild=guild)
        if not fetched:
            fetched = await bot.tree.fetch_commands()
        for fetched_command in fetched:
            if fetched_command.name not in BUTTON_COMMANDS.values():
                continue
            try:
                permissions = await fetched_command.fetch_permissions(guild)
                overrides[fetched_command.name] = permissions.permissions
            except discord.NotFound:
                # No overrides configured for this command.
                continue
    except Exception as e:
        print(f"Music - Could not fetch command permissions.\nErrors: {e}\n")
    _permissions_cache[guild.id] = (time.monotonic(), overrides)
    return overrides

async def CanUseCommand(bot:commands.Bot, guild:discord.Guild, member:discord.Member, channel_id:int, command_name:str) -> bool:
    """Whether the member passes the Integrations permission overrides of
    the given command, evaluated the way Discord does."""
    if member.guild_permissions.administrator:
        return True
    overrides = (await FetchCommandOverrides(bot, guild)).get(command_name)
    if not overrides:
        # No overrides configured: the command is open to everyone.
        return True
    users = {o.id: o.permission for o in overrides if o.type is app_commands.AppCommandPermissionType.user}
    roles = {o.id: o.permission for o in overrides if o.type is app_commands.AppCommandPermissionType.role}
    channels = {o.id: o.permission for o in overrides if o.type is app_commands.AppCommandPermissionType.channel}
    # Channel gate first, "guild id - 1" meaning every channel.
    if not channels.get(channel_id, channels.get(guild.id - 1, True)):
        return False
    # A member override beats roles, any allowing role beats the
    # @everyone override, which acts as the base value.
    if member.id in users:
        return users[member.id]
    role_values = [roles[role.id] for role in member.roles if role.id in roles and role.id != guild.id]
    if role_values:
        return any(role_values)
    return roles.get(guild.id, True)

async def AllowedButtonCommands(bot:commands.Bot, guild:discord.Guild, member:discord.Member, channel_id:int) -> set:
    """The set of button-backing commands the member may use."""
    allowed = set()
    for command_name in set(BUTTON_COMMANDS.values()):
        if await CanUseCommand(bot, guild, member, channel_id, command_name):
            allowed.add(command_name)
    return allowed

#endregion

#region Music

class MusicMessageView(View):
    """Controls under the music message, rendered from the guild's current
    playback state. The buttons carry only custom_ids, the raw interactions
    are handled in events.py so they keep working after a restart without
    re-registering the view. Passing `allowed` (a set of command names)
    keeps only the buttons backed by those commands, for /controls."""
    def __init__(self, guild:discord.Guild = None, allowed:set = None, **kwargs):
        kwargs.setdefault("timeout", None)
        super().__init__(**kwargs)
        self.allowed = allowed
        # Read the playback state.
        data = voice.guild_data.get(guild.id) if guild is not None else None
        voice_client = guild.voice_client if guild is not None else None
        playing = bool(voice_client and voice_client.is_playing())
        paused = bool(voice_client and voice_client.is_paused())
        loop = voice.GetLoop(guild.id) if guild is not None else False
        has_current = data is not None and data.current is not None
        has_queue = data is not None and len(data.queue) > 1
        active = data is not None and (has_current or bool(data.queue) or playing or paused)
        # Toggled buttons light up, everything grays out when idle. The
        # play button always shows the action it will perform. A row holds
        # at most 5 buttons, so the transport strip gets its own line.
        def toggle_style(on:bool):
            return discord.ButtonStyle.blurple if on else discord.ButtonStyle.grey
        shuffle_button = Button(emoji="🔀", style=discord.ButtonStyle.grey, custom_id="shuffle", row=0, disabled=not has_queue)
        prev_button = Button(emoji="⏮️", style=discord.ButtonStyle.grey, custom_id="prev", row=0, disabled=not active)
        play_button = Button(emoji="⏸️" if playing else "▶️", style=toggle_style(playing), custom_id="play", row=0, disabled=not active)
        next_button = Button(emoji="⏭️", style=discord.ButtonStyle.grey, custom_id="next", row=0, disabled=not active)
        # The loop preference persists, so it stays togglable while idle.
        loop_button = Button(emoji="🔁", style=toggle_style(loop), custom_id="loop", row=0, disabled=guild is None)
        download_button = Button(emoji="💾", style=discord.ButtonStyle.grey, custom_id="download", row=1, disabled=not has_current)
        backward_button = Button(emoji="⏪", label="-10s", style=discord.ButtonStyle.grey, custom_id="backward", row=1, disabled=not has_current)
        forward_button = Button(emoji="⏩", label="+10s", style=discord.ButtonStyle.grey, custom_id="forward", row=1, disabled=not has_current)
        # Clearing also covers a queue stashed by a disconnect.
        stash = voice._music_backup.get(guild.id) if guild is not None else None
        has_items = (data is not None and len(data.queue) > 0) or bool(stash and stash[0])
        clear_button = Button(emoji="🗑️", style=discord.ButtonStyle.red, custom_id="clear", row=1, disabled=not has_items)
        for button in (shuffle_button, prev_button, play_button, next_button, loop_button, download_button, backward_button, forward_button, clear_button):
            # Keep only permitted buttons when a filter is given.
            if allowed is None or BUTTON_COMMANDS.get(button.custom_id) in allowed:
                self.add_item(button)
    ...

class ClearQueueModal(Modal):
    """Confirmation before the 🗑️ button empties the entire queue."""
    def __init__(self, guild_id:int, **kwargs):
        kwargs.setdefault("title", settings.Localize("mdl_clear_queue_title", guild_id=guild_id))
        super().__init__(**kwargs)
        self.confirm_text = settings.Localize("lbl_confirm", guild_id=guild_id)
        confirm_label = settings.Localize("lbl_type_confirmation", self.confirm_text, guild_id=guild_id)
        self.confirm_input = TextInput(style=discord.TextStyle.short, label=confirm_label, required=True, min_length=len(self.confirm_text), max_length=len(self.confirm_text))
        self.add_item(self.confirm_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Check if confirmation was correct.
        if str(self.confirm_input.value).lower() != self.confirm_text.lower():
            await interaction.response.send_message(settings.Localize("lbl_wrong_confirmation", guild_id=interaction.guild_id), ephemeral=True)
            return
        # Clear the queue, crediting the user on the music message footer.
        await voice.ClearQueue(interaction.guild, interaction.user)
        await interaction.response.defer()

#endregion

#region Fun

class FlipView(View):
    def __init__(self, ctx:discord.Interaction, **kwargs):
        super().__init__(**kwargs)
        # Generate view and first value.
        flipped = random.randint(0, 1)
        repeated = 1
        def flipped_name(value):
            return settings.Localize("lbl_flip_head") if value == 0 else settings.Localize("lbl_flip_tail")
        def flipped_emoji(value):
            return settings.Localize("lbl_flip_head_emoji") if value == 0 else settings.Localize("lbl_flip_tail_emoji")
        # Get old data.
        data = ctx.data.get("custom_id")
        if (data and data.startswith("flip")):
            last_user = data.split("|")[1]
            last_flipped = data.split("|")[2]
            repeated = int(data.split("|")[3])
            if last_user == str(ctx.user.id) and last_flipped == flipped_name(flipped):
                repeated = repeated + 1
            else:
                repeated = 1
        info = f"{str(ctx.user.id)}|{flipped_name(flipped)}|{repeated}"
        # Create buttons.
        flip = Button(label=settings.Localize("lbl_flip_title"), style=discord.ButtonStyle.grey, custom_id=f"flip_1|{info}")
        button = Button(label="" if repeated <= 1 else f"x{repeated}", style=discord.ButtonStyle.blurple, emoji=flipped_emoji(flipped), custom_id=f"flip_2|{info}")
        display = Button(label=settings.Localize("lbl_flip_display", ctx.user.display_name, flipped_name(flipped)), style=discord.ButtonStyle.grey, custom_id=f"flip_3|{info}")
        lock = Button(label="", style=discord.ButtonStyle.grey, emoji="🔒", custom_id="lock")
        # Add buttons.
        self.add_item(flip)
        self.add_item(button)
        self.add_item(display)
        self.add_item(lock)
    ...

class RollView(View):
    def __init__(self, ctx:discord.Interaction, number:int = 20, **kwargs):
        super().__init__(**kwargs)
        # Generate view and first value.
        data = ctx.data.get("custom_id")
        if (data and data.startswith("roll")):
            number = int(data.split("|")[1])
        rolled = random.randint(1, number)
        # Create buttons.
        roll = Button(label=settings.Localize("lbl_roll_title"), style=discord.ButtonStyle.grey, custom_id=f"roll_1|{number}")
        button = Button(label=rolled, style=discord.ButtonStyle.blurple, custom_id=f"roll_2|{number}")
        display = Button(label=settings.Localize("lbl_roll_display", ctx.user.display_name, number), style=discord.ButtonStyle.grey, custom_id=f"roll_3|{number}")
        lock = Button(label="", style=discord.ButtonStyle.grey, emoji="🔒", custom_id="lock")
        # Add buttons.
        self.add_item(roll)
        self.add_item(button)
        self.add_item(display)
        self.add_item(lock)
    ...

class RouletteView(View):
    def __init__(self, ctx:discord.Interaction, **kwargs):
        super().__init__(**kwargs)
        dead_value = random.randint(0,5)
        bullet = 6
        display_label = settings.Localize("lbl_roulette_display")
        data = ctx.data.get("custom_id")
        if (data and data.startswith("roulette")):
            dead_value = int(data.split("|")[1])
            bullet = int(data.split("|")[2]) - 1
            if bullet <= dead_value:
                display_label = settings.Localize("lbl_roulette_died", ctx.user.display_name)
            else:
                display_label = settings.Localize("lbl_roulette_survived", ctx.user.display_name)
        dead = bullet <= dead_value
        info = f"{dead_value}|{bullet}"
        # Create buttons.
        shoot = Button(label=settings.Localize("lbl_roulette_title"), style=discord.ButtonStyle.grey, custom_id=f"roulette_1|{info}", disabled=dead)
        button = Button(label=bullet if not dead else "☠️", style=discord.ButtonStyle.blurple if not dead else discord.ButtonStyle.danger, custom_id=f"roulette_2|{info}", disabled=dead)
        display = Button(label=display_label, style=discord.ButtonStyle.grey, custom_id=f"roulette_3|{info}", disabled=dead)
        # Add buttons.
        self.add_item(shoot)
        self.add_item(button)
        self.add_item(display)
    ...

#endregion

#region Say

class SaySettingsView(View):
    def __init__(self, warning:str = None, **kwargs):
        super().__init__(**kwargs)
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
                message:discord.Message = settings.editing_say[interaction.user.id]["message"]
                # Stop editing.
                settings.editing_say.pop(interaction.user.id)
                # Delete original message.
                await message.delete()
            except:
                await interaction.response.defer()
                ...
        async def send_callback(interaction:discord.Interaction):
            try:
                # Fetch values.
                original:discord.Message = settings.editing_say[interaction.user.id]["message"]
                content:str = settings.editing_say[interaction.user.id]["content"]
                embed:discord.Embed = settings.editing_say[interaction.user.id]["embed"]
                attachments:List[discord.Attachment] = settings.editing_say[interaction.user.id]["attachments"]
                if content or embed or attachments:
                    # Stop editing.
                    settings.editing_say.pop(interaction.user.id)
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
        # Initialize elemenets.
        return_button = Button(label="⬅️", style=discord.ButtonStyle.blurple, row=1)
        display_button = Button(label=settings.Localize("lbl_say_files"), style=discord.ButtonStyle.grey, row=1, disabled=True)
        clear_button = Button(label=settings.Localize("lbl_say_clear"), style=discord.ButtonStyle.grey, row=1)
        instruction_button = Button(label=settings.Localize("lbl_files_instruction"), style=discord.ButtonStyle.grey, row=2, disabled=True)
        
        # Function callbacks.
        async def return_callback(interaction:discord.Interaction):
            await interaction.response.edit_message(view=SaySettingsView())
        async def clear_callback(interaction:discord.Interaction):
            settings.editing_say[interaction.user.id]["attachments"] = []
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
        settings.editing_say[interaction.user.id]["content"] = content
        await interaction.response.edit_message(content=content, view=SaySettingsView())

class SayEmbeddedView(View):
    def __init__(self, warning:str = None, **kwargs):
        super().__init__(**kwargs)
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
            settings.editing_say[interaction.user.id]["embed"] = None
            await interaction.response.edit_message(embed=None)
        async def color_callback(interaction:discord.Interaction):
            # Fetch and clean.
            embedded:discord.Embed = settings.editing_say[interaction.user.id]["embed"]
            embedded = settings.EmbedClean(embedded)
            # Change values.
            color_value = int(color_select.values[0].lstrip("#"), 16)
            embedded.color = color_value if color_value != 0 else None
            # Save and send preview embedded.
            settings.editing_say[interaction.user.id]["embed"] = embedded
            preview_embedded = settings.EmbedClean(embedded, True)
            await interaction.response.edit_message(embed=preview_embedded)
        async def author_callback(interaction:discord.Interaction):
            #settings.editing_say[interaction.user.id]["embed"] = embedded
            await interaction.response.send_modal(EmbedAuthorModal(title=settings.Localize("mdl_say_title")))
        async def content_callback(interaction:discord.Interaction):
            #settings.editing_say[interaction.user.id]["embed"] = embedded
            await interaction.response.send_modal(EmbedContentModal(title=settings.Localize("mdl_say_title")))
        async def footer_callback(interaction:discord.Interaction):
            #settings.editing_say[interaction.user.id]["embed"] = embedded
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
        embedded:discord.Embed = settings.editing_say[interaction.user.id]["embed"]
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
        settings.editing_say[interaction.user.id]["embed"] = embedded
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
        embedded:discord.Embed = settings.editing_say[interaction.user.id]["embed"]
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
        settings.editing_say[interaction.user.id]["embed"] = embedded
        preview_embedded = settings.EmbedClean(embedded, True)
        await interaction.response.edit_message(embed=preview_embedded, view=SayEmbeddedView(warning))
        ...

class EmbedFooterModal(Modal):
    # Content, Icon URL
    content_input = TextInput(style=discord.TextStyle.long, label=settings.Localize("mdl_embed_footer"), required=False, max_length=2000)
    icon_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("mdl_embed_footer_icon"), required=False, max_length=1000)
    async def on_submit(self, interaction:discord.Interaction):
        # Fetch and clean.
        embedded:discord.Embed = settings.editing_say[interaction.user.id]["embed"]
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
        settings.editing_say[interaction.user.id]["embed"] = embedded
        preview_embedded = settings.EmbedClean(embedded, True)
        await interaction.response.edit_message(embed=preview_embedded, view=SayEmbeddedView(warning))
        ...

#endregion