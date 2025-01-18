from scripts import settings, voice
import discord
from discord.ext import commands
from discord.commands import slash_command, default_permissions, guild_only

def setup(bot: commands.Bot):
    bot.add_cog(commands_music(bot))

class commands_music(commands.Cog):
    def __init__(self, bot: commands.Cog):
        self.bot = bot
    
    # PLAY ────────────────
    @slash_command(name="play", description = "-")
    @guild_only()
    async def play(self, ctx: discord.ApplicationContext, search:str = ""):
        await ctx.defer(ephemeral=True)
        # Try to connect to voice channel.
        connection = await voice.Connect(ctx)
        if not connection:
            # Send error message.
            await ctx.followup.send(settings.Localize(connection.message), ephemeral=True)
            return
        await voice.PlayAudio(ctx, search)

    # SKIP ────────────────
    @slash_command(name="skip", description = "-")
    @guild_only()
    async def skip(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        await ctx.followup.send("Skip", ephemeral=True)

    # PAUSE ────────────────
    @slash_command(name="pause", description = "-")
    @guild_only()
    async def pause(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        await ctx.followup.send("Pause", ephemeral=True)

    # STOP ────────────────
    @slash_command(name="stop", description = "-")
    @guild_only()
    async def stop(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        await ctx.followup.send("Stop", ephemeral=True)

    # SET MUSIC CHANNEL ────────────────
    @slash_command(name="musicmessage", description = "-")
    @guild_only()
    @default_permissions(administrator=True)
    async def music_message(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        await ctx.followup.send("Music Message", ephemeral=True)