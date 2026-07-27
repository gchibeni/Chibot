from scripts import settings, voice, elements
import discord
from discord.ext import commands
from discord.app_commands import describe, guild_only, command, Range
import asyncio

#region Initialization

async def setup(bot: commands.Bot):
    await bot.add_cog(commands_music(bot))

class commands_music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

#endregion

#region Commands

    # Every media action is a top-level command, so admins can set separate
    # Integrations permissions for each one.

    # PLAY ────────────────
    @command(name="play", description = settings.Localize("cmd_play"))
    @guild_only()
    @describe(search=settings.Localize("cmd_play_search"))
    @describe(next=settings.Localize("cmd_play_next"))
    async def play(self, ctx: discord.Interaction, search:str = "", next:bool = False):
        await self._play(ctx, search, next=next)

    # PUSH ────────────────
    @command(name="push", description = settings.Localize("cmd_push"))
    @guild_only()
    @describe(search=settings.Localize("cmd_play_search"))
    async def push(self, ctx: discord.Interaction, search:str):
        await self._play(ctx, search, push=True)

    # PAUSE ────────────────
    @command(name="pause", description = settings.Localize("cmd_pause"))
    @guild_only()
    async def pause(self, ctx: discord.Interaction):
        await ctx.response.defer(ephemeral=True)
        if voice.PauseMusic(ctx.guild):
            await voice.UpdateMusicMessage(ctx.guild)
            await ctx.followup.send(settings.Localize("lbl_music_paused", guild_id=ctx.guild_id), ephemeral=True)
        else:
            await ctx.followup.send(settings.Localize("lbl_music_nothing_playing", guild_id=ctx.guild_id), ephemeral=True)

    # RESUME ────────────────
    @command(name="resume", description = settings.Localize("cmd_resume"))
    @guild_only()
    async def resume(self, ctx: discord.Interaction):
        await ctx.response.defer(ephemeral=True)
        if voice.ResumeMusic(ctx.guild):
            await voice.UpdateMusicMessage(ctx.guild)
            await ctx.followup.send(settings.Localize("lbl_music_resumed", guild_id=ctx.guild_id), ephemeral=True)
        else:
            await ctx.followup.send(settings.Localize("lbl_music_nothing_paused", guild_id=ctx.guild_id), ephemeral=True)

    # SKIP ────────────────
    @command(name="skip", description = settings.Localize("cmd_skip"))
    @guild_only()
    async def skip(self, ctx: discord.Interaction):
        await self._skip(ctx)

    # NEXT ────────────────
    @command(name="next", description = settings.Localize("cmd_next"))
    @guild_only()
    async def next(self, ctx: discord.Interaction):
        await self._skip(ctx)

    # PREV ────────────────
    @command(name="prev", description = settings.Localize("cmd_prev"))
    @guild_only()
    async def prev(self, ctx: discord.Interaction):
        await ctx.response.defer(ephemeral=True)
        if await voice.PlayPrev(ctx.guild):
            await ctx.followup.send(settings.Localize("lbl_music_prev", guild_id=ctx.guild_id), ephemeral=True)
        else:
            await ctx.followup.send(settings.Localize("lbl_music_no_prev", guild_id=ctx.guild_id), ephemeral=True)

    # STOP ────────────────
    @command(name="stop", description = settings.Localize("cmd_stop"))
    @guild_only()
    async def stop(self, ctx: discord.Interaction):
        await ctx.response.defer(ephemeral=True)
        if await voice.StopMusic(ctx.guild):
            await ctx.followup.send(settings.Localize("lbl_music_stopped", guild_id=ctx.guild_id), ephemeral=True)
        else:
            await ctx.followup.send(settings.Localize("lbl_music_not_connected", guild_id=ctx.guild_id), ephemeral=True)

    # QUEUE ────────────────
    @command(name="queue", description = settings.Localize("cmd_queue"))
    @guild_only()
    async def queue(self, ctx: discord.Interaction):
        await ctx.response.defer(ephemeral=True)
        await ctx.followup.send(embed=voice.BuildMusicEmbed(ctx.guild), ephemeral=True)

    # CLEAR ────────────────
    @command(name="clear", description = settings.Localize("cmd_clear"))
    @guild_only()
    async def clear(self, ctx: discord.Interaction):
        await ctx.response.defer(ephemeral=True)
        await voice.ClearQueue(ctx.guild, ctx.user)
        await ctx.followup.send(settings.Localize("lbl_music_cleared", guild_id=ctx.guild_id), ephemeral=True)

    # SCRUB ────────────────
    @command(name="scrub", description = settings.Localize("cmd_scrub"))
    @guild_only()
    @describe(position=settings.Localize("cmd_scrub_position"))
    async def scrub(self, ctx: discord.Interaction, position:str):
        await ctx.response.defer(ephemeral=True)
        seconds = voice.ParseTimestamp(position)
        if seconds is None:
            await ctx.followup.send(settings.Localize("lbl_music_invalid_time", guild_id=ctx.guild_id), ephemeral=True)
            return
        if await voice.Scrub(ctx.guild, seconds):
            minutes, secs = divmod(int(max(seconds, 0)), 60)
            await ctx.followup.send(settings.Localize("lbl_music_scrubbed", f"{minutes}:{secs:02d}", guild_id=ctx.guild_id), ephemeral=True)
        else:
            await ctx.followup.send(settings.Localize("lbl_music_nothing_playing", guild_id=ctx.guild_id), ephemeral=True)

    # SHUFFLE ────────────────
    @command(name="shuffle", description = settings.Localize("cmd_shuffle"))
    @guild_only()
    async def shuffle(self, ctx: discord.Interaction):
        await ctx.response.defer(ephemeral=True)
        if await voice.ShuffleQueue(ctx.guild):
            await ctx.followup.send(settings.Localize("lbl_music_shuffled", guild_id=ctx.guild_id), ephemeral=True)
        else:
            await ctx.followup.send(settings.Localize("lbl_music_queue_empty", guild_id=ctx.guild_id), ephemeral=True)

    # REORDER ────────────────
    @command(name="reorder", description = settings.Localize("cmd_move"))
    @guild_only()
    @describe(source=settings.Localize("cmd_move_from"))
    @describe(destination=settings.Localize("cmd_move_to"))
    async def reorder(self, ctx: discord.Interaction, source:Range[int,1], destination:Range[int,1]):
        await ctx.response.defer(ephemeral=True)
        if await voice.MoveMedia(ctx.guild, source, destination):
            await ctx.followup.send(settings.Localize("lbl_music_moved", source, destination, guild_id=ctx.guild_id), ephemeral=True)
        else:
            await ctx.followup.send(settings.Localize("lbl_music_invalid_index", guild_id=ctx.guild_id), ephemeral=True)

    # CONTROLS ────────────────
    @command(name="controls", description = settings.Localize("cmd_controls"))
    @guild_only()
    async def controls(self, ctx: discord.Interaction):
        await ctx.response.defer(ephemeral=True)
        # Personal control panel: only the buttons the caller may press.
        allowed = await elements.AllowedButtonCommands(self.bot, ctx.guild, ctx.user, ctx.channel_id)
        view = elements.MusicMessageView(ctx.guild, allowed=allowed)
        if not view.children:
            await ctx.followup.send(settings.Localize("lbl_no_permission", guild_id=ctx.guild_id), ephemeral=True)
            return
        await ctx.followup.send(view=view, ephemeral=True)

    # DOWNLOAD ────────────────
    @command(name="download", description = settings.Localize("cmd_download"))
    @guild_only()
    async def download(self, ctx: discord.Interaction, search:str = ""):
        await ctx.response.defer()
        file = await asyncio.to_thread(voice.Download, ctx, search)
        title = f"{file["title"]}"
        await ctx.followup.send(settings.Localize("lbl_download_complete", title, guild_id=ctx.guild_id), file=file["file"])

#endregion

#region Utils

    async def _play(self, ctx: discord.Interaction, search:str, next:bool = False, push:bool = False):
        await ctx.response.defer(ephemeral=True)
        # Try to connect to voice channel.
        connection = await voice.TryConnect(ctx)
        if not connection:
            # Send error message.
            await ctx.followup.send(settings.Localize(connection.message, guild_id=ctx.guild_id), ephemeral=True)
            return
        # Without a prompt, resume paused media or just join, like before.
        if not search.strip():
            if voice.ResumeMusic(ctx.guild):
                await voice.UpdateMusicMessage(ctx.guild)
                await ctx.followup.send(settings.Localize("lbl_music_resumed", guild_id=ctx.guild_id), ephemeral=True)
            else:
                await ctx.followup.send(settings.Localize("lbl_music_joined", guild_id=ctx.guild_id), ephemeral=True)
            return
        # Send a fast response, resolving media can take a while.
        await ctx.followup.send(settings.Localize("lbl_music_adding", guild_id=ctx.guild_id), ephemeral=True)
        count, error = await voice.QueueMedia(ctx.guild, search.strip(), ctx.user, next=next, push=push)
        if error:
            await ctx.edit_original_response(content=settings.Localize(error, guild_id=ctx.guild_id))
            return
        await ctx.edit_original_response(content=settings.Localize("lbl_music_added", count, guild_id=ctx.guild_id))

    async def _skip(self, ctx: discord.Interaction):
        await ctx.response.defer(ephemeral=True)
        if await voice.PlayNext(ctx.guild):
            await ctx.followup.send(settings.Localize("lbl_music_skipped", guild_id=ctx.guild_id), ephemeral=True)
        else:
            await ctx.followup.send(settings.Localize("lbl_music_nothing_playing", guild_id=ctx.guild_id), ephemeral=True)

#endregion
