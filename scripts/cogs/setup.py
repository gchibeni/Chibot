from scripts import settings, speech, actions, voice
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, Select, ChannelSelect, Modal, TextInput, Label

#region Initialization

async def setup(bot: commands.Bot):
    await bot.add_cog(commands_setup(bot))

class commands_setup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Both subcommands are admin actions, so sharing the group's
    # permission override is fine here.
    group = app_commands.Group(name="setup", description=settings.Localize("cmd_setup"), guild_only=True, default_permissions=discord.Permissions(administrator=True))

#endregion

#region Commands

    # SETUP SETTINGS ────────────────
    @group.command(name="settings", description = settings.Localize("cmd_setup_settings"))
    async def setup_settings(self, ctx: discord.Interaction):
        if not ctx.user.guild_permissions.administrator:
            await ctx.response.send_message(settings.Localize("lbl_no_permission", guild_id=ctx.guild_id), ephemeral=True)
            return
        await ctx.response.send_message(embed=SetupEmbed(ctx.guild), view=SetupView(ctx), ephemeral=True)

    # The panel is driven by raw custom_ids so it never expires: the view
    # and modals are rebuilt from the interaction, surviving bot restarts.
    @commands.Cog.listener("on_interaction")
    async def handle_components(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component or interaction.guild is None:
            return
        custom_id = (interaction.data or {}).get("custom_id") or ""
        if custom_id not in ("setup_channels", "setup_preferences"):
            return
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(settings.Localize("lbl_no_permission", guild_id=interaction.guild_id), ephemeral=True)
            return
        if custom_id == "setup_channels":
            await interaction.response.send_modal(SetupChannelsModal(interaction, title=settings.Localize("mdl_setup_channels_title", guild_id=interaction.guild_id)))
        else:
            await interaction.response.send_modal(SetupPreferencesModal(interaction, title=settings.Localize("mdl_setup_preferences_title", guild_id=interaction.guild_id)))

    # SETUP MEDIA QUEUE ────────────────
    @group.command(name="media-queue", description = settings.Localize("cmd_musicmessage"))
    async def setup_media_queue(self, ctx: discord.Interaction):
        if not ctx.user.guild_permissions.administrator:
            await ctx.response.send_message(settings.Localize("lbl_no_permission", guild_id=ctx.guild_id), ephemeral=True)
            return
        await ctx.response.defer(ephemeral=True)
        # The current channel becomes the guild's music channel.
        await voice.CreateMusicMessage(ctx.guild, ctx.channel)
        settings.SetInfo(ctx.guild_id, "setup/music_channel", ctx.channel.id)
        await ctx.followup.send(settings.Localize("lbl_music_message_created", ctx.channel.mention, guild_id=ctx.guild_id), ephemeral=True)

#endregion

#region Elements

# The channel fields shown in the channels modal: settings key under
# "setup/", locale key and selectable channel types.
CHANNEL_FIELDS = [
    ("text_channel", "lbl_setup_text_channel", [discord.ChannelType.text]),
    ("music_channel", "lbl_setup_music_channel", [discord.ChannelType.text]),
    ("auto_join_channel", "lbl_setup_auto_join_channel", [discord.ChannelType.voice]),
]

def SetupEmbed(guild:discord.Guild) -> discord.Embed:
    """Overview of the guild's current setup."""
    guild_id = guild.id
    not_set = settings.Localize("lbl_not_set", guild_id=guild_id)
    lines = []
    for key, locale_key, _ in CHANNEL_FIELDS:
        channel_id = settings.GetInfo(guild_id, f"setup/{key}")
        value = f"<#{channel_id}>" if channel_id else not_set
        lines.append(f"**{settings.Localize(locale_key, guild_id=guild_id)}** ➜ {value}")
    wake_word = actions.GetWakeWord(guild_id)
    lines.append(f"**{settings.Localize('lbl_setup_wake_word', guild_id=guild_id)}** ➜ {settings.Localize(f'lbl_wake_{wake_word}', guild_id=guild_id)}")
    language = settings.GetLanguage(guild_id)
    lines.append(f"**{settings.Localize('lbl_setup_language', guild_id=guild_id)}** ➜ {settings.LANGUAGES[language]}")
    spotify = settings.Localize("lbl_setup_spotify_set", guild_id=guild_id) if settings.GetInfo(guild_id, "setup/spotify_token") else not_set
    lines.append(f"**{settings.Localize('lbl_setup_spotify_token', guild_id=guild_id)}** ➜ {spotify}")
    return discord.Embed(title=settings.Localize("lbl_setup_title", guild_id=guild_id), description="\n".join(lines))

class SetupView(View):
    def __init__(self, ctx:discord.Interaction, warning:str = None, **kwargs):
        kwargs.setdefault("timeout", None)
        super().__init__(**kwargs)
        guild_id = ctx.guild_id
        # Create elements. The buttons carry only custom_ids, the raw
        # interactions are handled by the cog listener so the panel keeps
        # working after a restart.
        if warning is not None:
            warning_button = Button(label=warning, style=discord.ButtonStyle.grey, row=1, disabled=True)
            self.add_item(warning_button)
        channels_button = Button(label=settings.Localize("lbl_setup_channels", guild_id=guild_id), style=discord.ButtonStyle.blurple, row=2, custom_id="setup_channels")
        preferences_button = Button(label=settings.Localize("lbl_setup_preferences", guild_id=guild_id), style=discord.ButtonStyle.blurple, row=2, custom_id="setup_preferences")
        # Add elements.
        self.add_item(channels_button)
        self.add_item(preferences_button)

class SetupChannelsModal(Modal):
    def __init__(self, ctx:discord.Interaction, **kwargs):
        super().__init__(**kwargs)
        self.ctx = ctx
        self.key_id = ctx.guild_id
        self.selects:dict[str, ChannelSelect] = {}
        # One channel select per field, prefilled with the saved channel.
        for key, locale_key, channel_types in CHANNEL_FIELDS:
            channel_id = settings.GetInfo(self.key_id, f"setup/{key}")
            defaults = []
            if channel_id:
                defaults = [discord.SelectDefaultValue(id=int(channel_id), type=discord.SelectDefaultValueType.channel)]
            select = ChannelSelect(channel_types=channel_types, min_values=0, max_values=1, default_values=defaults)
            self.selects[key] = select
            self.add_item(Label(text=settings.Localize(locale_key, guild_id=self.key_id), component=select))

    async def on_submit(self, interaction: discord.Interaction):
        # Save every field, clearing the ones left unselected.
        for key, select in self.selects.items():
            value = select.values[0].id if select.values else None
            settings.SetInfo(self.key_id, f"setup/{key}", value)
        await interaction.response.edit_message(embed=SetupEmbed(interaction.guild), view=SetupView(self.ctx, settings.Localize("lbl_setup_saved", guild_id=self.key_id)))
        ...

class SetupPreferencesModal(Modal):
    def __init__(self, ctx:discord.Interaction, **kwargs):
        super().__init__(**kwargs)
        self.ctx = ctx
        self.key_id = ctx.guild_id
        current_wake = actions.GetWakeWord(self.key_id)
        current_language = settings.GetLanguage(self.key_id)
        has_token = bool(settings.GetInfo(self.key_id, "setup/spotify_token"))
        # Create inputs.
        self.wake_select = Select()
        for wake_word in actions.WAKE_WORD_OPTIONS:
            label = settings.Localize(f"lbl_wake_{wake_word}", guild_id=self.key_id)
            self.wake_select.add_option(value=wake_word, label=label, default=(wake_word == current_wake))
        self.language_select = Select()
        for code, name in settings.LANGUAGES.items():
            self.language_select.add_option(value=code, label=name, default=(code == current_language))
        # The saved token is never shown back: the field is always a clean
        # slate, leaving it blank keeps the current token.
        placeholder = settings.Localize("mdl_setup_spotify_keep", guild_id=self.key_id) if has_token else "client_id:client_secret"
        self.spotify_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("lbl_setup_spotify_token", guild_id=self.key_id), required=False, max_length=200, placeholder=placeholder)
        # Add inputs.
        self.add_item(Label(text=settings.Localize("lbl_setup_wake_word", guild_id=self.key_id), description=settings.Localize("mdl_setup_wake_desc", guild_id=self.key_id), component=self.wake_select))
        self.add_item(Label(text=settings.Localize("lbl_setup_language", guild_id=self.key_id), description=settings.Localize("mdl_setup_language_desc", guild_id=self.key_id), component=self.language_select))
        self.add_item(self.spotify_input)

    async def on_submit(self, interaction: discord.Interaction):
        wake_word = self.wake_select.values[0] if self.wake_select.values else actions.DEFAULT_WAKE_WORD
        settings.SetInfo(self.key_id, "setup/wake_word", wake_word)
        language = self.language_select.values[0] if self.language_select.values else settings.LANG
        settings.SetInfo(self.key_id, "setup/language", language if language != settings.LANG else None)
        # Blank keeps the currently saved token unchanged.
        spotify_token = self.spotify_input.value.strip()
        if spotify_token:
            settings.SetInfo(self.key_id, "setup/spotify_token", spotify_token)
        # The wake phrases feed the voice recognizers, reload them.
        speech.RefreshGuild(self.key_id)
        # Re-render the music message in the new language.
        await voice.UpdateMusicMessage(interaction.guild)
        await interaction.response.edit_message(embed=SetupEmbed(interaction.guild), view=SetupView(self.ctx, settings.Localize("lbl_setup_saved", guild_id=self.key_id)))
        ...

#endregion
