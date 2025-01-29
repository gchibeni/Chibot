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
    @command(name="auth", description = settings.Localize("auth_description"))
    async def authy(self, ctx: discord.Interaction):
        await ctx.response.send_message(view=AuthView(ctx), ephemeral=True, delete_after=840)

#endregion

#region Elements

class AuthView(View):
    def __init__(self, ctx:discord.Interaction, warning:str = None, **kwargs):
        super().__init__(**kwargs)
        # Variables.
        is_private = ctx.channel.type == discord.ChannelType.private
        key_id = f"user-{ctx.user.id}" if is_private else ctx.guild_id
        # Create elements.
        if warning is not None:
            warning_button = Button(label=warning, style=discord.ButtonStyle.grey, row=1, disabled=True)
            self.add_item(warning_button)
        select_view = Select(placeholder="SELECT AUTH", row=2)
        add_button = Button(label="ADD", style=discord.ButtonStyle.green, row=3)
        remove_button = Button(label="REMOVE", style=discord.ButtonStyle.red, row=3)
        # Fetch authenticators.
        auths = settings.GetInfo(key_id, "authenticators")
        def reload_auths():
            # Fetch authenticators.
            auths = settings.GetInfo(key_id, "authenticators")
            select_view.options.clear()
            if not auths:
                select_view.disabled = True
                select_view.add_option(value="null", label="None")
                return
            else:
                count : int = 0
                for name,values in auths.items():
                    select_view.add_option(value=name, label=name, description=values["description"])
                    count += 1
        reload_auths()
        # Define callbacks.

        async def select_callback(interaction:discord.Interaction):
            selected = select_view.values[0]
            for option in select_view.options:
                if str(option.value) == str(selected):
                    totp = pyotp.TOTP(auths[option.label]["secret"])
                    auth_code = totp.now()
                    time_remaining = totp.interval - (time.time() % totp.interval)
                    select_view.placeholder = f"{option.label}  ({int(time_remaining)}s)  ➜  {auth_code}"
            if warning:
                self.remove_item(warning_button)
            reload_auths()
            await interaction.response.edit_message(view=self)

        async def add_callback(interaction:discord.Interaction):
            add_modal = AddAuthModal(ctx, title=settings.Localize("auth_add_title"))
            await interaction.response.send_modal(add_modal)

        async def remove_callback(interaction:discord.Interaction):
            if select_view.values:
                selected_auth = select_view.values[0]
                remove_modal = RemoveAuthModal(ctx, selected_auth, title=settings.Localize("auth_add_title"))
                await interaction.response.send_modal(remove_modal)
            else:
                await interaction.response.edit_message(view=AuthView(ctx,warning=settings.Localize("auth_not_selected")))
        
        # Set callbacks.
        select_view.callback = select_callback
        add_button.callback = add_callback
        remove_button.callback = remove_callback
        # Add elements.
        self.add_item(select_view)
        admin = True if is_private else ctx.user.guild_permissions.administrator
        if admin:
            self.add_item(add_button)
            self.add_item(remove_button)

class AddAuthModal(Modal):
    def __init__(self, ctx:discord.Interaction, **kwargs):
        super().__init__(**kwargs)
        self.ctx = ctx
        self.is_private = ctx.channel.type == discord.ChannelType.private
        self.key_id = f"user-{ctx.user.id}" if self.is_private else ctx.guild_id
    
    # Create inputs.
    name_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("auth_m_name_label"), required=True, placeholder="----", min_length=3, max_length=10)
    desc_input = TextInput(style=discord.TextStyle.paragraph, label=settings.Localize("auth_m_desc_label"), required=False, placeholder="----", max_length=35)
    secret_input = TextInput( style=discord.TextStyle.short, label=settings.Localize("auth_m_secret_label"), required=True, placeholder="---- ---- ---- ---- ---- ---- ---- ----", min_length=16, max_length=64)

    async def on_submit(self, interaction: discord.Interaction):
        input_name = str(self.children[0].value).upper()
        input_desc = str(self.children[1].value)
        input_secret = str(self.children[2].value).lower().replace(" ", "")
        limit = settings.AUTH_LIMIT
        # Check if auth code is valid.
        if not settings.isValidAuth(input_secret):
            await interaction.response.edit_message(view=AuthView(self.ctx, settings.Localize("auth_invalid_code")))
            return
        # Check guild limit.
        auth_count = settings.GetInfo(self.key_id, "authenticators")
        if auth_count and len(auth_count) >= limit:
            await interaction.response.edit_message(view=AuthView(self.ctx, settings.Localize("auth_limit", input_name, limit)))
            return
        # Add auth to guild list.
        auth_data = { "secret":input_secret, "description":input_desc }
        settings.SetInfo(self.key_id, f"authenticators/{input_name}", auth_data)
        await interaction.response.edit_message(view=AuthView(self.ctx, settings.Localize("auth_added", input_name)))
        ...

class RemoveAuthModal(Modal):
    def __init__(self, ctx:discord.Interaction, selected_auth:str, **kwargs):
        super().__init__(**kwargs)
        self.ctx = ctx
        self.selected_auth = selected_auth
        self.is_private = ctx.channel.type == discord.ChannelType.private
        self.key_id = f"user-{ctx.user.id}" if self.is_private else ctx.guild_id
    
    # Create inputs.
    confirm_label= settings.Localize("auth_m_remove_label")
    confirm_text = settings.Localize("auth_m_confirm")
    confirm_input = discord.ui.TextInput(style=discord.TextStyle.short, label=confirm_label, required=True, placeholder=confirm_text, min_length=len(confirm_text), max_length=len(confirm_text))

    async def on_submit(self, interaction: discord.Interaction):
        # Get variables.
        confirm_input = str(self.children[0].value).lower()
        selected_auth = self.selected_auth
        # Check if confirmation was correct.
        if confirm_input != self.confirm_text.lower():
            await interaction.response.edit_message(view=AuthView(self.ctx, settings.Localize("auth_wrong_confirmation")))
            return
        #Check if any auth was found.
        auth:str = settings.GetInfo(self.key_id, f"authenticators/{selected_auth}")
        if auth is None:
            await interaction.response.edit_message(view=AuthView(self.ctx, settings.Localize("auth_not_found", selected_auth)))
            return
        # Delete matching auth.
        settings.SetInfo(self.key_id, f"authenticators/{selected_auth}", None)
        await interaction.response.edit_message(view=AuthView(self.ctx, settings.Localize("auth_removed", selected_auth)))
        ...

#endregion