from scripts import settings
import discord
from discord.ext import commands
from discord.app_commands import command
import pyotp
import time
from discord.ui import Button, View, Select, Modal, TextInput

#region Initialization

async def setup(bot: commands.Bot):
    await bot.add_cog(commands_auth(bot))

class commands_auth(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

#endregion

#region Commands

    # AUTHY ────────────────
    @command(name="auth", description = settings.Localize("cmd_auth"))
    async def authy(self, ctx: discord.Interaction):
        await ctx.response.send_message(view=AuthView(ctx), ephemeral=True)

    # The panel is driven by raw custom_ids so it never expires: the view
    # is rebuilt from the interaction itself, surviving bot restarts.
    @commands.Cog.listener("on_interaction")
    async def handle_components(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = (interaction.data or {}).get("custom_id") or ""
        if custom_id == "auth_select":
            values = interaction.data.get("values") or []
            selected = values[0] if values else None
            if not selected or selected == "null":
                await interaction.response.defer()
                return
            embedded = AuthCodeEmbed(AuthKey(interaction), selected)
            await interaction.response.edit_message(embed=embedded, view=AuthView(interaction, selected=selected))
        elif custom_id == "auth_add":
            if not IsAuthAdmin(interaction):
                await interaction.response.send_message(settings.Localize("lbl_no_permission", guild_id=interaction.guild_id), ephemeral=True)
                return
            await interaction.response.send_modal(AddAuthModal(interaction, title=settings.Localize("mdl_auth_add_title")))
        elif custom_id.startswith("auth_remove|"):
            if not IsAuthAdmin(interaction):
                await interaction.response.send_message(settings.Localize("lbl_no_permission", guild_id=interaction.guild_id), ephemeral=True)
                return
            selected = custom_id.split("|", 1)[1]
            await interaction.response.send_modal(RemoveAuthModal(interaction, selected, title=settings.Localize("mdl_auth_remove_title")))

#endregion

#region Elements

def AuthKey(ctx:discord.Interaction):
    """Authenticators are stored per user in DMs, per guild otherwise."""
    is_private = ctx.guild_id is None
    return f"user-{ctx.user.id}" if is_private else ctx.guild_id

def IsAuthAdmin(ctx:discord.Interaction) -> bool:
    """Managing authenticators takes admin in guilds, anyone in DMs."""
    if ctx.guild_id is None:
        return True
    return ctx.user.guild_permissions.administrator

def AuthCodeEmbed(key_id, selected:str) -> discord.Embed:
    """The expiration embed for a selected authenticator, or None."""
    auth = settings.GetInfo(key_id, f"authenticators/{selected}")
    if not auth:
        return None
    totp = pyotp.TOTP(auth["secret"])
    time_remaining = totp.interval - (time.time() % totp.interval)
    time_stamp = int(time.time() + time_remaining)
    return discord.Embed(description=settings.Localize("lbl_auth_expiration", time_stamp))

class AuthView(View):
    def __init__(self, ctx:discord.Interaction, selected:str = None, warning:str = None, **kwargs):
        kwargs.setdefault("timeout", None)
        super().__init__(**kwargs)
        # Variables.
        key_id = AuthKey(ctx)
        # Create elements.
        if warning is not None:
            warning_button = Button(label=warning, style=discord.ButtonStyle.grey, row=1, disabled=True)
            self.add_item(warning_button)
        select_view = Select(placeholder=settings.Localize("lbl_auth_select"), row=2, custom_id="auth_select")
        add_button = Button(label=settings.Localize("lbl_auth_add"), style=discord.ButtonStyle.green, row=3, custom_id="auth_add")
        # Disabled until an authenticator is selected. The selection rides
        # along in the custom_id so it survives restarts.
        remove_button = Button(label=settings.Localize("lbl_auth_remove"), style=discord.ButtonStyle.red, row=3, custom_id=f"auth_remove|{selected}", disabled=selected is None)
        # Fetch authenticators.
        auths = settings.GetInfo(key_id, "authenticators")
        if not auths:
            select_view.disabled = True
            select_view.add_option(value="null", label="None")
        else:
            for name, values in auths.items():
                select_view.add_option(value=name, label=name, description=values["description"])
        # Show the code of the selected authenticator.
        if selected and auths and selected in auths:
            totp = pyotp.TOTP(auths[selected]["secret"])
            select_view.placeholder = f"{selected}  ➜  {totp.now()}"
        # Add elements.
        self.add_item(select_view)
        if IsAuthAdmin(ctx):
            self.add_item(add_button)
            self.add_item(remove_button)

class AddAuthModal(Modal):
    def __init__(self, ctx:discord.Interaction, **kwargs):
        super().__init__(**kwargs)
        self.key_id = AuthKey(ctx)

    # Create inputs.
    name_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("mdl_auth_add_name"), required=True, min_length=3, max_length=10)
    desc_input = TextInput(style=discord.TextStyle.paragraph, label=settings.Localize("mdl_auth_add_desc"), required=False, max_length=35)
    secret_input = TextInput( style=discord.TextStyle.short, label=settings.Localize("mdl_auth_add_secret"), required=True, placeholder="---- ---- ---- ---- ---- ---- ---- ----", min_length=16, max_length=64)

    async def on_submit(self, interaction: discord.Interaction):
        input_name = self.name_input.value.strip()
        input_desc = self.desc_input.value
        input_secret = self.secret_input.value.lower().replace(" ", "")
        limit = settings.AUTH_LIMIT
        # Check if auth code is valid.
        if not settings.isValidAuth(input_secret):
            await interaction.response.edit_message(view=AuthView(interaction, warning=settings.Localize("lbl_invalid_code")))
            return
        # Check guild limit.
        auth_count = settings.GetInfo(self.key_id, "authenticators")
        if auth_count and len(auth_count) >= limit:
            await interaction.response.edit_message(view=AuthView(interaction, warning=settings.Localize("lbl_limit_reached", limit)))
            return
        # Add auth to guild list.
        auth_data = { "secret":input_secret, "description":input_desc }
        settings.SetInfo(self.key_id, f"authenticators/{input_name}", auth_data)
        await interaction.response.edit_message(view=AuthView(interaction, warning=settings.Localize("lbl_item_added", input_name)))
        ...

class RemoveAuthModal(Modal):
    def __init__(self, ctx:discord.Interaction, selected_auth:str, **kwargs):
        super().__init__(**kwargs)
        self.selected_auth = selected_auth
        self.key_id = AuthKey(ctx)

    # Create inputs.
    confirm_text = settings.Localize("lbl_confirm")
    confirm_label= settings.Localize("lbl_type_confirmation", confirm_text)
    confirm_input = discord.ui.TextInput(style=discord.TextStyle.short, label=confirm_label, required=True, min_length=len(confirm_text), max_length=len(confirm_text))

    async def on_submit(self, interaction: discord.Interaction):
        # Get variables.
        confirm_input = str(self.children[0].value).lower()
        selected_auth = self.selected_auth
        # Check if confirmation was correct.
        if confirm_input != self.confirm_text.lower():
            await interaction.response.edit_message(embed=None, view=AuthView(interaction, warning=settings.Localize("lbl_wrong_confirmation")))
            return
        #Check if any auth was found.
        auth:str = settings.GetInfo(self.key_id, f"authenticators/{selected_auth}")
        if auth is None:
            await interaction.response.edit_message(embed=None, view=AuthView(interaction, warning=settings.Localize("lbl_item_not_found", selected_auth)))
            return
        # Delete matching auth.
        settings.SetInfo(self.key_id, f"authenticators/{selected_auth}", None)
        await interaction.response.edit_message(embed=None, view=AuthView(interaction, warning=settings.Localize("lbl_item_removed", selected_auth)))
        ...

#endregion
