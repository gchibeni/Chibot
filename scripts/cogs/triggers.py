from scripts import settings, speech
import discord
from discord.ext import commands
from discord.app_commands import default_permissions, guild_only, command
from discord.ui import Button, View, Select, Modal, TextInput, Label

#region Initialization

async def setup(bot: commands.Bot):
    await bot.add_cog(commands_triggers(bot))

class commands_triggers(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

#endregion

#region Commands

    # TRIGGERS ────────────────
    @command(name="triggers", description = settings.Localize("cmd_triggers"))
    @guild_only()
    @default_permissions(administrator=True)
    async def triggers(self, ctx: discord.Interaction):
        if not ctx.user.guild_permissions.administrator:
            await ctx.response.send_message(settings.Localize("lbl_no_permission"), ephemeral=True)
            return
        await ctx.response.send_message(view=TriggersView(ctx), ephemeral=True, delete_after=840)

#endregion

#region Elements

MODES = ["text", "voice", "both"]
PLAY_MODES = ["random", "sequence", "one"]

def SanitizePhrase(phrase:str) -> str:
    """Normalize a trigger phrase for storage and matching."""
    return " ".join(phrase.replace("/", " ").lower().split())

class TriggersView(View):
    def __init__(self, ctx:discord.Interaction, warning:str = None, **kwargs):
        super().__init__(**kwargs)
        # Variables.
        key_id = ctx.guild_id
        # Create elements.
        if warning is not None:
            warning_button = Button(label=warning, style=discord.ButtonStyle.grey, row=1, disabled=True)
            self.add_item(warning_button)
        select_view = Select(placeholder=settings.Localize("lbl_trigger_select"), row=2)
        add_button = Button(label=settings.Localize("lbl_trigger_add"), style=discord.ButtonStyle.green, row=3)
        # Disabled until a trigger is selected.
        edit_button = Button(label=settings.Localize("lbl_trigger_edit"), style=discord.ButtonStyle.blurple, row=3, disabled=True)
        remove_button = Button(label=settings.Localize("lbl_trigger_remove"), style=discord.ButtonStyle.red, row=3, disabled=True)
        # Fetch triggers.
        def reload_triggers():
            triggers = settings.GetInfo(key_id, "triggers")
            select_view.options.clear()
            if not triggers:
                select_view.disabled = True
                select_view.add_option(value="null", label="None")
                return
            for title, data in triggers.items():
                mode = data.get("mode", "text")
                play = data.get("play", "random")
                phrases = len(data.get("phrases") or [title])
                count = len(data.get("actions", []))
                description = f"{mode.capitalize()} • {play.capitalize()} • {phrases} trigger{'s' if phrases != 1 else ''}, {count} action{'s' if count != 1 else ''}"
                select_view.add_option(value=title, label=title, description=description)
        reload_triggers()
        # Define callbacks.

        async def select_callback(interaction:discord.Interaction):
            selected = select_view.values[0]
            trigger = settings.GetInfo(key_id, f"triggers/{selected}")
            embedded = None
            if trigger:
                select_view.placeholder = selected
                mode = trigger.get("mode", "text").capitalize()
                play = trigger.get("play", "random").capitalize()
                phrases = "\n".join(f"` {line} `" for line in trigger.get("phrases") or [selected])
                actions = "\n".join(f"` {line} `" for line in trigger.get("actions", []))
                embedded = discord.Embed(description=f"**{selected}**  •  {mode}  •  {play}\n**Triggers:**\n{phrases}\n**Actions:**\n{actions}")
            reload_triggers()
            edit_button.disabled = trigger is None
            remove_button.disabled = trigger is None
            await interaction.response.edit_message(embed=embedded, view=self)

        async def add_callback(interaction:discord.Interaction):
            add_modal = TriggerModal(ctx, title=settings.Localize("mdl_trigger_add_title"))
            await interaction.response.send_modal(add_modal)

        async def edit_callback(interaction:discord.Interaction):
            if select_view.values:
                selected = select_view.values[0]
                trigger = settings.GetInfo(key_id, f"triggers/{selected}")
                if trigger:
                    edit_modal = TriggerModal(ctx, title_key=selected, trigger=trigger, title=settings.Localize("mdl_trigger_edit_title"))
                    await interaction.response.send_modal(edit_modal)
                    return
            await interaction.response.edit_message(embed=None, view=TriggersView(ctx, warning=settings.Localize("lbl_item_none_selected")))

        async def remove_callback(interaction:discord.Interaction):
            if select_view.values:
                selected = select_view.values[0]
                remove_modal = RemoveTriggerModal(ctx, selected, title=settings.Localize("mdl_trigger_remove_title"))
                await interaction.response.send_modal(remove_modal)
            else:
                await interaction.response.edit_message(embed=None, view=TriggersView(ctx, warning=settings.Localize("lbl_item_none_selected")))

        # Set callbacks.
        select_view.callback = select_callback
        add_button.callback = add_callback
        edit_button.callback = edit_callback
        remove_button.callback = remove_callback
        # Add elements.
        self.add_item(select_view)
        self.add_item(add_button)
        self.add_item(edit_button)
        self.add_item(remove_button)

class TriggerModal(Modal):
    def __init__(self, ctx:discord.Interaction, title_key:str = None, trigger:dict = None, **kwargs):
        super().__init__(**kwargs)
        self.ctx = ctx
        self.key_id = ctx.guild_id
        self.editing_title = title_key
        trigger = trigger or {}
        current_mode = trigger.get("mode", "text")
        current_play = trigger.get("play", "random")
        phrases = trigger.get("phrases") or ([title_key] if title_key else [])
        # Create inputs.
        self.title_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("mdl_trigger_title"), required=True, min_length=2, max_length=40, placeholder="Clip saver", default=title_key)
        self.mode_select = Select(placeholder=settings.Localize("mdl_trigger_mode"))
        for mode in MODES:
            label = settings.Localize(f"lbl_trigger_mode_{mode}")
            self.mode_select.add_option(value=mode, label=label, default=(mode == current_mode))
        self.play_select = Select(placeholder=settings.Localize("mdl_trigger_play"))
        for play in PLAY_MODES:
            label = settings.Localize(f"lbl_trigger_play_{play}")
            self.play_select.add_option(value=play, label=label, default=(play == current_play))
        self.phrases_input = TextInput(style=discord.TextStyle.paragraph, label=settings.Localize("mdl_trigger_phrases"), required=True, max_length=600, placeholder="clip that\nsalva isso\n%call tocar música", default="\n".join(phrases) or None)
        self.actions_input = TextInput(style=discord.TextStyle.paragraph, label=settings.Localize("mdl_trigger_actions"), required=True, max_length=1000, placeholder="/replay 30\nNice clip, @self!\n%disconnect @self", default="\n".join(trigger.get("actions", [])) or None)
        # Add inputs.
        self.add_item(self.title_input)
        self.add_item(Label(text=settings.Localize("mdl_trigger_mode"), description=settings.Localize("mdl_trigger_mode_desc"), component=self.mode_select))
        self.add_item(self.phrases_input)
        self.add_item(Label(text=settings.Localize("mdl_trigger_play"), description=settings.Localize("mdl_trigger_play_desc"), component=self.play_select))
        self.add_item(self.actions_input)

    async def on_submit(self, interaction: discord.Interaction):
        input_title = " ".join(self.title_input.value.replace("/", " ").split())
        input_mode = self.mode_select.values[0] if self.mode_select.values else "text"
        input_play = self.play_select.values[0] if self.play_select.values else "random"
        input_phrases = [SanitizePhrase(line) for line in self.phrases_input.value.splitlines() if SanitizePhrase(line)]
        input_actions = [line.strip() for line in self.actions_input.value.splitlines() if line.strip()]
        limit = settings.TRIGGER_LIMIT
        # Check inputs.
        if not input_title or not input_phrases or not input_actions:
            await interaction.response.edit_message(embed=None, view=TriggersView(self.ctx, settings.Localize("lbl_empty_content")))
            return
        # Check guild limit when adding a new trigger.
        triggers = settings.GetInfo(self.key_id, "triggers") or {}
        is_new = input_title not in triggers and self.editing_title is None
        if is_new and len(triggers) >= limit:
            await interaction.response.edit_message(embed=None, view=TriggersView(self.ctx, settings.Localize("lbl_limit_reached", limit)))
            return
        # Remove the old entry when the title was renamed.
        if self.editing_title and self.editing_title != input_title:
            settings.SetInfo(self.key_id, f"triggers/{self.editing_title}", None)
        # Save trigger to guild list.
        trigger_data = { "mode":input_mode, "play":input_play, "phrases":input_phrases, "actions":input_actions }
        settings.SetInfo(self.key_id, f"triggers/{input_title}", trigger_data)
        speech.RefreshGuild(self.key_id)
        await interaction.response.edit_message(embed=None, view=TriggersView(self.ctx, settings.Localize("lbl_item_added", input_title)))
        ...

class RemoveTriggerModal(Modal):
    def __init__(self, ctx:discord.Interaction, selected_trigger:str, **kwargs):
        super().__init__(**kwargs)
        self.ctx = ctx
        self.selected_trigger = selected_trigger
        self.key_id = ctx.guild_id

    # Create inputs.
    confirm_text = settings.Localize("lbl_confirm")
    confirm_label = settings.Localize("lbl_type_confirmation", confirm_text)
    confirm_input = TextInput(style=discord.TextStyle.short, label=confirm_label, required=True, min_length=len(confirm_text), max_length=len(confirm_text))

    async def on_submit(self, interaction: discord.Interaction):
        # Check if confirmation was correct.
        if str(self.confirm_input.value).lower() != self.confirm_text.lower():
            await interaction.response.edit_message(embed=None, view=TriggersView(self.ctx, settings.Localize("lbl_wrong_confirmation")))
            return
        # Check if the trigger still exists.
        trigger = settings.GetInfo(self.key_id, f"triggers/{self.selected_trigger}")
        if trigger is None:
            await interaction.response.edit_message(embed=None, view=TriggersView(self.ctx, settings.Localize("lbl_item_not_found", self.selected_trigger)))
            return
        # Delete matching trigger.
        settings.SetInfo(self.key_id, f"triggers/{self.selected_trigger}", None)
        speech.RefreshGuild(self.key_id)
        await interaction.response.edit_message(embed=None, view=TriggersView(self.ctx, settings.Localize("lbl_item_removed", self.selected_trigger)))
        ...

#endregion
