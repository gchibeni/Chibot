from scripts import settings
import discord
from discord.ext import commands
from discord import app_commands
import pyotp

#region Initialization

async def setup(bot: commands.Bot):
    print("Cog added - Auth")
    bot.tree.add_command(commands_auth(name="auth", description="-", guild_ids=[295732646535757828]))
    await bot.add_cog(commands_authy(bot))

#endregion

#region Commands

class commands_authy(commands.Cog):
    def __init__(self, bot: commands.Cog):
        self.bot = bot
    
    # AUTHY ────────────────
    @app_commands.command(name="authy", description = settings.Localize("authy_description"))
    @app_commands.guilds(295732646535757828)
    @app_commands.guild_only()
    @app_commands.describe(name=settings.Localize("auth_name_describe"))
    async def authy(self, ctx: discord.Interaction, name:str):
        # Check parameters.
        if len(name) < 3:
            await ctx.response.send_message(settings.Localize("auth_small_name"), ephemeral=True)
            return
        if len(name) > 35:
            await ctx.response.send_message(settings.Localize("auth_big_name"), ephemeral=True)
            return
        # Check if auth is valid.
        auth_secret:str = settings.GetInfo(ctx.guild_id, f"authenticators/{name}")
        auth_secret = auth_secret.lower().replace(" ", "")
        if auth_secret is None:
            await ctx.response.send_message(settings.Localize("auth_not_found"), ephemeral=True)
            return
        if settings.isValidAuth(auth_secret):
            await ctx.response.send_message(settings.Localize("auth_invalid_code"), ephemeral=True)
            return
        # Send code to user.
        auth_code = pyotp.TOTP(auth_secret).now()
        await ctx.response.send_message(settings.Localize("auth_found", auth_code), ephemeral=True)

class commands_auth(app_commands.Group):
    # ADD ────────────────
    @app_commands.command(name="add", description = settings.Localize("auth_add_description"))
    @app_commands.guilds(295732646535757828)
    @app_commands.guild_only()
    @app_commands.describe(name=settings.Localize("auth_name_describe"), code = settings.Localize("auth_code_describe"))
    async def auth_add(self, ctx: discord.Interaction, name:str = None, code:str = None):
        # Check parameters.
        if id is None or code is None:
            auth_modal = AuthAddModal()
            await ctx.response.send_modal(auth_modal)
            return
        if len(name) < 3:
            await ctx.response.send_message(settings.Localize("auth_small_name"), ephemeral=True)
            return
        if len(name) > 35:
            await ctx.response.send_message(settings.Localize("auth_big_name"), ephemeral=True)
            return
        # Check if auth code is valid.
        if not settings.isValidAuth(code):
            await ctx.response.send_message(settings.Localize("auth_invalid_code"), ephemeral=True)
            return
        # Add auth to guild list.
        settings.SetInfo(ctx.guild_id, f"authenticators/{name}", code)
        await ctx.response.send_message(settings.Localize("auth_added", name), ephemeral=True)
        ...

    # DEL ────────────────
    @app_commands.command(name="remove", description = settings.Localize("auth_remove_description"))
    @app_commands.guilds(295732646535757828)
    @app_commands.guild_only()
    @app_commands.describe(name=settings.Localize("auth_name_describe"))
    async def auth_remove(self, ctx: discord.Interaction, name:str):
        # Check parameters.
        if len(name) < 3 or len(name) > 35:
            await ctx.response.send_message(settings.Localize("auth_not_found"), ephemeral=True)
            return
        # Check if any auth was found.
        auth_secret:str = settings.GetInfo(ctx.guild_id, f"authenticators/{name}")
        auth_secret = auth_secret.lower().replace(" ", "")
        if auth_secret is None:
            await ctx.response.send_message(settings.Localize("auth_not_found"), ephemeral=True)
            return
        # Delete matching auth.
        settings.SetInfo(ctx.guild_id, f"authenticators/{name}", None)
        await ctx.response.send_message(settings.Localize("auth_removed", auth_secret), ephemeral=True)
        ...

    # LIST ────────────────
    @app_commands.command(name="list", description = settings.Localize("auth_list_description"))
    @app_commands.guilds(295732646535757828)
    @app_commands.guild_only()
    async def auth_list(self, ctx: discord.Interaction):
        # Check if any auth was found.
        auths = settings.GetInfo(ctx.guild_id, "authenticators")
        if not auths:
            await ctx.response.send_message(settings.Localize("auth_not_found"), ephemeral=True)
            return
        # List all authenticators.
        list_str = ''; count : int = 0
        for auth in auths:
            list_str += f'\n```#{count:02d} : {auth}```'; count += 1
        # Create embeded.
        embeded = discord.Embed(description=list_str).set_footer(text=settings.Localize("auth_index_list_label"))
        await ctx.response.send_message(embed=embeded, ephemeral=True)
        ...

#endregion

#region Modals

class AuthAddModal(discord.ui.Modal, title=settings.Localize("auth_add_title")):
    m_name = discord.ui.TextInput(
        style=discord.TextStyle.short,
        label=settings.Localize("auth_name_label"),
        required=True,
        placeholder="----",
        min_length=3,
        max_length=35,
    )
    
    m_code = discord.ui.TextInput(
        style=discord.TextStyle.short,
        label=settings.Localize("auth_code_label"),
        required=True,
        placeholder="---- ---- ---- ---- ---- ---- ---- ----",
        min_length=16,
        max_length=64
    )

    async def on_submit(self, ctx: discord.Interaction):
        # Get variables.
        input_name = self.m_name.value.lower().replace(" ", "")
        input_code = self.m_code.value.lower().replace(" ", "")
        guild = ctx.guild_id
        limit = 20
        # Check if auth code is valid.
        if not settings.isValidAuth(input_code):
            await ctx.response.send_message(settings.Localize("auth_invalid_code"), ephemeral=True)
            return
        # Check guild limit.
        authInfo = settings.GetInfo(guild, "authenticators")
        if authInfo and len(authInfo) >= limit:
            await ctx.response.send_message(settings.Localize("auth_limit", input_name, limit))
            return
        # Add auth to guild list.
        settings.SetInfo(guild, f"authenticators/{input_name}", input_code)
        await ctx.response.send_message(settings.Localize("auth_added", input_name), ephemeral=True)
        ...
    
    async def on_error(self, ctx: discord.Interaction, error):
        await ctx.response.send_message(settings.Localize("error"), ephemeral=True)
        ...

#endregion