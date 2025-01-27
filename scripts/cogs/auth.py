from scripts import settings
import discord
from discord.ext import commands
from discord.app_commands import default_permissions, describe, dm_only, guild_only, command, Range
import pyotp
import time

#region Initialization

async def setup(bot: commands.Bot):
    await bot.add_cog(commands_authy(bot))
    await bot.add_cog(commands_auth(bot))

#endregion

#region Commands

class commands_authy(commands.Cog):
    def __init__(self, bot: commands.Cog):
        self.bot = bot
    
    # AUTHY ────────────────
    @discord.app_commands.command(name="authy", description = settings.Localize("authy_description"))
    @guild_only()
    @describe(name=settings.Localize("auth_name_describe"))
    async def authy(self, ctx: discord.Interaction, name:Range[str,3,35]):
        await ctx.response.defer(thinking=True, ephemeral=True)
        # Check parameters.
        if len(name) < 3:
            await ctx.followup.send(settings.Localize("auth_small_name"), ephemeral=True, delete_after=5)
            return
        if len(name) > 35:
            await ctx.followup.send(settings.Localize("auth_big_name"), ephemeral=True, delete_after=5)
            return
        # Check if auth is valid.
        auth_secret:str = settings.GetInfo(ctx.guild_id, f"authenticators/{name}")
        auth_secret = auth_secret.lower().replace(" ", "")
        if auth_secret is None:
            await ctx.followup.send(settings.Localize("auth_not_found"), ephemeral=True, delete_after=5)
            return
        if not settings.isValidAuth(auth_secret):
            await ctx.followup.send(settings.Localize("auth_invalid_code"), ephemeral=True, delete_after=5)
            return
        # Send code to user.
        totp = pyotp.TOTP(auth_secret)
        auth_code = totp.now()
        time_remaining = totp.interval - (time.time() % totp.interval)
        await ctx.followup.send(settings.Localize("auth_found", auth_code), ephemeral=True, delete_after=time_remaining)
        ...

class commands_auth(commands.GroupCog, group_name="auth"):
    def __init__(self, bot: commands.Cog):
        self.bot = bot
    
    # ADD ────────────────
    # Show add module (max 25)
    @command(name="add", description = settings.Localize("auth_add_description"))
    @guild_only()
    @describe(name=settings.Localize("auth_name_describe"))
    @describe(code=settings.Localize("auth_code_describe"))
    async def auth_add(self, ctx: discord.Interaction, name:str = None, code:str = None):
        # Check parameters.
        if id is None or code is None:
            auth_modal = AuthAddModal(title=settings.Localize("auth_add_title"))
            await ctx.send_modal(auth_modal)
            return
        if len(name) < 3:
            await ctx.send_response(settings.Localize("auth_small_name"), ephemeral=True, delete_after=5)
            return
        if len(name) > 35:
            await ctx.send_response(settings.Localize("auth_big_name"), ephemeral=True, delete_after=5)
            return
        # Check if auth code is valid.
        if not settings.isValidAuth(code):
            await ctx.send_response(settings.Localize("auth_invalid_code"), ephemeral=True, delete_after=5)
            return
        # Add auth to guild list.
        settings.SetInfo(ctx.guild_id, f"authenticators/{name}", code)
        await ctx.send_response(settings.Localize("auth_added", name), ephemeral=True, delete_after=5)
        ...

    # DEL ────────────────
    # Show selectable list (max 25)
    @command(name="remove", description = settings.Localize("auth_remove_description"))
    @guild_only()
    @describe(name=settings.Localize("auth_name_describe"))
    async def auth_remove(self, ctx: discord.Interaction, name:str):
        await ctx.response.defer(thinking=True, ephemeral=True)
        # Check parameters.
        if len(name) < 3 or len(name) > 35:
            await ctx.followup.send(settings.Localize("auth_not_found"), ephemeral=True, delete_after=5)
            return
        # Check if any auth was found.
        auth_secret:str = settings.GetInfo(ctx.guild_id, f"authenticators/{name}")
        auth_secret = auth_secret.lower().replace(" ", "")
        if auth_secret is None:
            await ctx.followup.send(settings.Localize("auth_not_found"), ephemeral=True, delete_after=5)
            return
        # Delete matching auth.
        settings.SetInfo(ctx.guild_id, f"authenticators/{name}", None)
        await ctx.followup.send(settings.Localize("auth_removed", auth_secret), ephemeral=True)
        ...

    # LIST ────────────────
    # Show list (max 25)
    @command(name="list", description = settings.Localize("auth_list_description"))
    @guild_only()
    async def auth_list(self, ctx: discord.Interaction):
        await ctx.response.defer(thinking=True, ephemeral=True)
        # Check if any auth was found.
        auths = settings.GetInfo(ctx.guild_id, "authenticators")
        if not auths:
            await ctx.followup.send(settings.Localize("auth_not_found"), ephemeral=True, delete_after=5)
            return
        # List all authenticators.
        list_str = ''; count : int = 0
        for auth in auths:
            list_str += f'\n```#{count:02d} : {auth}```'; count += 1
        # Create embeded.
        embeded = discord.Embed(description=list_str).set_footer(text=settings.Localize("auth_index_list_label"))
        await ctx.followup.send(embed=embeded, ephemeral=True)
        ...

#endregion

#region Modals

class AuthAddModal(discord.ui.Modal):    
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_item(discord.ui.TextInput(
            style=discord.TextStyle.short,
            label=settings.Localize("auth_name_label"),
            required=True,
            placeholder="----",
            min_length=3,
            max_length=35,
        ))
        self.add_item(discord.ui.TextInput(
            style=discord.TextStyle.short,
            label=settings.Localize("auth_code_label"),
            required=True,
            placeholder="---- ---- ---- ---- ---- ---- ---- ----",
            min_length=16,
            max_length=64
        ))
        
    async def callback(self, ctx: discord.Interaction):
        # Get variables.
        input_name = self.children[0].value.lower().replace(" ", "")
        input_code = self.children[1].value.lower().replace(" ", "")
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

#endregion