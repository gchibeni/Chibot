from scripts import settings
import discord
from discord.ext import commands, tasks, voice_recv
from discord import app_commands
import asyncio
import wave
import os
import io
import numpy as np
from datetime import datetime
from collections import deque

async def setup(bot: commands.Bot):
    await bot.add_cog(commands_common(bot))

class commands_common(commands.Cog):
    def __init__(self, bot: commands.Cog):
        self.bot = bot

    # STATUS ────────────────
    @app_commands.command(name="status", description = "-")
    async def status(self, ctx:discord.Interaction):
        await ctx.response.send_message(settings.Localize("bot_status", settings.maintenance, settings.lang), ephemeral=True, delete_after=2)

    # CLEAR ────────────────
    @app_commands.command(name="clear", description = "-")
    @app_commands.private_channel_only()
    async def clear(self, ctx:discord.Interaction):
        await ctx.response.send_message("Clear", ephemeral=True)
    
    # AVATAR ────────────────
    @app_commands.command(name="avatar", description = "-")
    async def avatar(self, ctx:discord.Interaction):
        await ctx.response.send_message("Avatar", ephemeral=True)
    
    # FLIP ────────────────
    @app_commands.command(name="flip", description = "-")
    async def flip(self, ctx:discord.Interaction):
        await ctx.response.send_message("Flip", ephemeral=True)

    # ROLL ────────────────
    @app_commands.command(name="roll", description = "-")
    async def roll(self, ctx:discord.Interaction):
        await ctx.response.send_message("Roll", ephemeral=True)

    # ANON ────────────────
    @app_commands.command(name="anon", description = "-")
    async def anon(self, ctx:discord.Interaction):
        await ctx.response.send_message("Anon", ephemeral=True)
        
    # REMINDME ────────────────
    @app_commands.command(name="remindme", description = "-")
    async def remind_me(self, ctx:discord.Interaction):
        await ctx.response.send_message("Remind me", ephemeral=True)
        
    # ROULETTE ────────────────
    @app_commands.command(name="roulette", description = "-")
    async def roulette(self, ctx:discord.Interaction):
        await settings.Disconnect(ctx.guild)
        await ctx.response.send_message("Roulette", ephemeral=True)
        
    # PULL/BRING ────────────────
    @app_commands.command(name="pull", description = "-")
    @app_commands.guild_only()
    async def pull(self, ctx:discord.Interaction):
        await settings.Connect(ctx)
        await ctx.response.send_message("Pull", ephemeral=True)

    # REPLAY ────────────────
    @app_commands.command(name="replay", description = "-")
    @app_commands.guild_only()
    async def replay(self, ctx:discord.Interaction, seconds:int = 15, pitch:int = 1):
        # TODO: Limit how many times the guild can use the replay command per second (1/2s).        
        await ctx.response.defer(thinking=True, ephemeral=True)
        # Try to connect to voice channel.
        connection = await settings.Connect(ctx)
        if not connection:
            # Send error message.
            await ctx.delete_original_response()
            await ctx.followup.send(settings.Localize(connection.message), ephemeral=True)
            return
        
        # If just joined, send message that he started recording.
        if connection.message != "already_connected":
            await ctx.delete_original_response()
            await ctx.followup.send(settings.Localize("started_recording"), ephemeral=True)
            return
        # Save replay and 
        await settings.SaveReplay(ctx, seconds, pitch)
        
