from scripts import settings, voice
import discord
from discord.ext import commands, tasks
from discord import app_commands

async def setup(bot: commands.Bot):
    await bot.add_cog(commands_music(bot))

class commands_music(commands.Cog):
    def __init__(self, bot: commands.Cog):
        self.bot = bot
    
    # PLAY ────────────────
    @app_commands.command(name="play", description = "-")
    @app_commands.guild_only()
    async def play(self, ctx: discord.Interaction, search:str = ""):
        await ctx.response.defer(thinking=True, ephemeral=True)
        # Try to connect to voice channel.
        connection = await voice.Connect(ctx)
        if not connection:
            # Send error message.
            await ctx.delete_original_response()
            await ctx.followup.send(settings.Localize(connection.message), ephemeral=True)
            return
        await voice.PlayAudio(ctx, search)

    # SKIP ────────────────
    @app_commands.command(name="skip", description = "-")
    @app_commands.guild_only()
    async def skip(self, ctx: discord.Interaction):
        await ctx.response.send_message("Skip", ephemeral=True)

    # PAUSE ────────────────
    @app_commands.command(name="pause", description = "-")
    @app_commands.guild_only()
    async def pause(self, ctx: discord.Interaction):
        await ctx.response.send_message("Pause", ephemeral=True)

    # STOP ────────────────
    @app_commands.command(name="stop", description = "-")
    @app_commands.guild_only()
    async def stop(self, ctx: discord.Interaction):
        await ctx.response.send_message("Stop", ephemeral=True)

    # SET MUSIC CHANNEL ────────────────
    @app_commands.command(name="musicmessage", description = "-")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def music_message(self, ctx: discord.Interaction):
        await ctx.response.send_message("Music Message", ephemeral=True)

    # SPOTIFY AUTH ────────────────
    @app_commands.command(name="spotifyauth", description = "-")
    @app_commands.guild_only()
    @app_commands.checks.has_permissions(administrator=True)
    async def music_message(self, ctx: discord.Interaction):
        await ctx.response.send_message("Spotify Auth", ephemeral=True)