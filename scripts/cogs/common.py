from scripts import settings, voice, elements
import discord
from discord.ext import commands
from discord import app_commands
from discord.app_commands import default_permissions, describe, dm_only, guild_only, command, Range
from discord.ui import Button, View, Select, Modal
import random
import asyncio

#region Initialization

async def setup(bot: commands.Bot):
    await bot.add_cog(commands_common(bot))

class commands_common(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

#endregion

#region Utils

    # STATUS ────────────────
    @app_commands.command(name="status", description = settings.Localize("cmd_status"))
    async def status(self, ctx:discord.Interaction):
        await ctx.response.send_message(settings.Localize("lbl_status"), ephemeral=True, delete_after=2)
        # Create custom command test
        # Define dynamic parameters
        dynamic_params = { "arg1": "Dynamic parameter description", "arg2": "Another parameter dynamic description" }
        # Dynamically create the callback function
        async def custom_callback(interaction: discord.Interaction, arg1: str, arg2: str):
            await interaction.response.send_message(f"This test was a success!\n` {arg1} `\n` {arg2} `", ephemeral=True)
        # Create the dynamic command
        command_test = discord.app_commands.Command(name="test", description="A dynamic custom command", callback=custom_callback)
        # Attach parameter descriptions
        for param_name, param_desc in dynamic_params.items():
            command_test._params[param_name].description = param_desc
            command_test._params[param_name]._rename = f"{param_name}test"
            command_test._params[param_name].required = False
        self.bot.tree.clear_commands(guild=ctx.guild)
        self.bot.tree.add_command(command_test, guild=ctx.guild)
        await self.bot.tree.sync(guild=ctx.guild)

    # CLEAR ────────────────
    @command(name="clear", description = settings.Localize("cmd_clear"))
    @dm_only()
    async def clear(self, ctx:discord.Interaction):
        await ctx.response.defer(ephemeral=True)
        async for message in ctx.channel.history(limit=100):
            if message.author == self.bot.user:
                await message.delete()
        await ctx.followup.send(settings.Localize("lbl_dm_cleared"), ephemeral=True)

    # AVATAR ────────────────
    @command(name="avatar", description = settings.Localize("cmd_avatar"))
    @describe(user=settings.Localize("cmd_avatar_target"))
    @guild_only()
    async def avatar(self, ctx:discord.Interaction, user:discord.User):
        await ctx.response.defer(thinking=True, ephemeral=True)
        embedded = discord.Embed(description=settings.Localize("lbl_avatar_fetched", user.mention)).set_image(url=user.display_avatar.url)
        await ctx.followup.send(embed=embedded, ephemeral=True)

    # ANON ────────────────
    @command(name="anon", description = settings.Localize("cmd_anon"))
    @describe(user=settings.Localize("cmd_anon_target"))
    async def anon(self, ctx:discord.Interaction, user:discord.User = None):
        await ctx.response.send_modal(elements.AnonModal(ctx, user, title=settings.Localize("mdl_anon_title")))

    # REMINDER ────────────────
    @command(name="reminder", description = settings.Localize("cmd_reminder"))
    async def remind_me(self, ctx:discord.Interaction):
        await ctx.response.send_message("Reminder", ephemeral=True)

#endregion

#region Fun
    
    # FLIP ────────────────
    @command(name="flip", description = settings.Localize("cmd_flip"))
    @describe(hidden=settings.Localize("lbl_hidden"))
    async def flip(self, ctx:discord.Interaction, hidden:bool = False):
        # Common variables.
        await ctx.response.defer(thinking=True, ephemeral=hidden)
        view = elements.FlipView(ctx)
        await ctx.followup.send(view=view, ephemeral=hidden)

    # ROLL ────────────────
    @command(name="roll", description = settings.Localize("cmd_roll"))
    @describe(number=settings.Localize("cmd_roll_number"))
    @describe(hidden=settings.Localize("lbl_hidden"))
    async def roll(self, ctx:discord.Interaction, number:Range[int, 2] = 20, hidden:bool = False):
        await ctx.response.defer(thinking=True, ephemeral=hidden)
        # Generate view and first value.
        view = elements.RollView(ctx, number)
        await ctx.followup.send(view=view, ephemeral=hidden)

    # ROULETTE ────────────────
    @command(name="roulette", description = "-")
    @describe(hidden=settings.Localize("lbl_hidden"))
    async def roulette(self, ctx:discord.Interaction, hidden:bool = False):
        await ctx.response.defer(thinking=True, ephemeral=hidden)
        # Generate view and dead value.
        view = elements.RouletteView(ctx)
        await ctx.followup.send(view=view, ephemeral=hidden)

#endregion

#region Voice

    # REPLAY ────────────────
    @command(name="replay", description = settings.Localize("cmd_replay"))
    @guild_only()
    @describe(seconds=settings.Localize("cmd_replay_seconds"))
    @describe(pitch=settings.Localize("cmd_replay_pitch"))
    @describe(hidden=settings.Localize("lbl_hidden"))
    async def replay(self, ctx:discord.Interaction, seconds:Range[int,5] = 15, pitch:Range[float, 0.0, 2.0] = 1, hidden:bool = False):
        # TODO: Limit how many times the guild can use the replay command per second (1/5s).
        await ctx.response.defer(thinking=True, ephemeral=True)
        # Try to connect to voice channel.
        connection = await voice.TryConnect(ctx)
        if not connection:
            # Send error message.
            await ctx.followup.send(settings.Localize(connection.message), ephemeral=True)
            return
        # If just joined, send message that he started recording.
        if not connection.already_connected():
            await ctx.delete_original_response()
            return
        # Save and send replay file.
        seconds = min(seconds, settings.MAX_RECORDING_TIME)
        file = await asyncio.to_thread(voice.SaveReplay, ctx, seconds, pitch)
        #await ctx.delete_original_response()
        if file is not None:
            if not hidden:
                await ctx.delete_original_response()
                await ctx.channel.send(settings.Localize("lbl_replay_complete", seconds, pitch), file=file)
            else:
                await ctx.followup.send(settings.Localize("lbl_replay_complete", seconds, pitch), file=file, ephemeral=True)
            return
        await ctx.followup.send(settings.Localize("lbl_replay_failed"), ephemeral=True)

#endregion