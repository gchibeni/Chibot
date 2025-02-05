from scripts import settings, voice
import discord
from discord.ext import commands
from discord.app_commands import default_permissions, describe, dm_only, guild_only, command, Range

#region Initialization

async def setup(bot: commands.Bot):
    await bot.add_cog(commands_music(bot))

class commands_music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

#endregion

#region Commands

    # PLAY ────────────────
    @command(name="play", description = "-")
    @guild_only()
    async def play(self, ctx: discord.Interaction, search:str = ""):
        await ctx.response.defer(ephemeral=True)
        # Try to connect to voice channel.
        connection = await voice.TryConnect(ctx)
        if not connection:
            # Send error message.
            await ctx.followup.send(settings.Localize(connection.message), ephemeral=True)
            return
        await voice.PlayAudio(ctx, search)

    # SKIP ────────────────
    @command(name="skip", description = "-")
    @guild_only()
    async def skip(self, ctx: discord.Interaction):
        await ctx.response.defer(ephemeral=True)
        await ctx.followup.send("Skip", ephemeral=True)

    # PAUSE ────────────────
    @command(name="pause", description = "-")
    @guild_only()
    async def pause(self, ctx: discord.Interaction):
        await ctx.response.defer(ephemeral=True)
        await ctx.followup.send("Pause", ephemeral=True)

    # STOP ────────────────
    @command(name="stop", description = "-")
    @guild_only()
    async def stop(self, ctx: discord.Interaction):
        await ctx.response.defer(ephemeral=True)
        await ctx.followup.send("Stop", ephemeral=True)

    # SET MUSIC CHANNEL ────────────────
    @command(name="musicmessage", description = "-")
    @guild_only()
    @default_permissions(administrator=True)
    async def music_message(self, ctx: discord.Interaction):
        await ctx.response.defer(ephemeral=True)
        await ctx.followup.send("Music Message", ephemeral=True)

#endregion