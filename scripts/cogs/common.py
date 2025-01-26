
from scripts import settings, voice
import discord
from discord.ext import commands
from discord.commands import slash_command, default_permissions, guild_only, option, SlashCommandGroup
from discord.ui import Button, View

import asyncio
import wave
import os
import io
import random
import numpy as np
from datetime import datetime
from collections import deque

def setup(bot: commands.Bot):
    bot.add_cog(commands_common(bot))

class commands_common(commands.Cog):
    def __init__(self, bot: commands.Cog):
        self.bot = bot

    # STATUS ────────────────
    @slash_command(name="status", description = "-")
    async def status(self, ctx:discord.ApplicationContext):
        await ctx.send(settings.Localize("bot_status", settings.maintenance, settings.lang), ephemeral=True, delete_after=2)
    
    # AVATAR ────────────────
    @slash_command(name="avatar", description = "Fetch the avatar of any member")
    @option("member", description="Target member", required=True)
    async def avatar(self, ctx:discord.ApplicationContext, member:discord.Member):
        await ctx.defer(ephemeral=True)
        embeded = discord.Embed(description=settings.Localize("fetched_avatar", member.mention)).set_image(url=member.display_avatar.url)
        await ctx.followup.send(embed=embeded, ephemeral=True)
    
    # FLIP ────────────────
    @slash_command(name="flip", description = "-")
    @option("hidden", description="-", required=False, default=False)
    async def flip(self, ctx:discord.ApplicationContext, hidden:bool):
        # Common variables.
        await ctx.defer(ephemeral=hidden)
        # Generate view and first value.
        view = View()
        flipped = random.randint(0, 1)
        def flipped_name(value):
            return 'HEAD' if value == 0 else 'TAIL'
        def flipped_emoji(value):
            return '<a:heads:1163294205033062400>' if value == 0 else '<a:tails:1163293766791204874>'
        # Create buttons.
        flip = Button(label="FLIP", style=discord.ButtonStyle.grey)
        button = Button(label="", style=discord.ButtonStyle.blurple, emoji=flipped_emoji(flipped))
        display = Button(label=f'➜  {ctx.user.display_name} flipped {flipped_name(flipped)}!', style=discord.ButtonStyle.grey)
        # Set callback functions.
        async def button_callback(interaction:discord.Interaction):
            flipped = random.randint(0, 1)
            button.emoji = flipped_emoji(flipped)
            display.label = f'➜  {ctx.user.display_name} flipped {flipped_name(flipped)}!'
            await interaction.response.edit_message(view=view)
        # Set button callbacks.
        flip.callback = button.callback = display.callback = button_callback
        # Add buttons.
        view.add_item(flip)
        view.add_item(button)
        view.add_item(display)
        # Send view.
        await ctx.followup.send(view=view, ephemeral=hidden)

    # ROLL ────────────────
    @slash_command(name="roll", description = "-")
    @option("number", description="-", required=False, default=20, min_value=2)
    @option("hidden", description="-", required=False, default=False)
    async def roll(self, ctx:discord.ApplicationContext, number:int, hidden:bool):
        await ctx.defer(ephemeral=hidden)
        # Generate view and first value.
        view = View()
        rolled = random.randint(1, number)
        # Create buttons.
        roll = Button(label=F"ROLL", style=discord.ButtonStyle.grey)
        button = Button(label=rolled, style=discord.ButtonStyle.blurple)
        display = Button(label=f'➜  {ctx.user.display_name} rolled a D{number}!', style=discord.ButtonStyle.grey)
        # Set callback function.
        async def button_callback(interaction:discord.Interaction):
            rolled = random.randint(1, number)
            button.label = rolled
            display.label = f'➜  {interaction.user.display_name} rolled a D{number}!'
            await interaction.response.edit_message(view=view)
        # Set button callbacks.
        roll.callback = button.callback = display.callback = button_callback
        # Add buttons.
        view.add_item(roll)
        view.add_item(button)
        view.add_item(display)
        # Send view.
        await ctx.followup.send(view=view, ephemeral=hidden)

    # ROULETTE ────────────────
    @slash_command(name="roulette", description = "-")
    @guild_only()
    @option("hidden", description="-", required=False, default=False)
    async def roulette(self, ctx:discord.ApplicationContext, hidden:bool):
        await ctx.defer(ephemeral=hidden)
        # Generate view and dead value.
        view = View()
        dead_value = random.randint(0,5)
        # Create buttons.
        shoot = Button(label="SHOOT", style=discord.ButtonStyle.grey)
        button = Button(label="6", style=discord.ButtonStyle.blurple)
        dead = Button(label="➜  Russian roulette", style=discord.ButtonStyle.grey)
        # Set callback function.
        async def button_callback(interaction:discord.Interaction):
            button_value = int(button.label) - 1
            if (dead_value == button_value):
                button.label = "☠️"
                dead.label = f'➜  {interaction.user.display_name} died!'
                button.style = discord.ButtonStyle.danger
                button.disabled = True
                shoot.disabled = True
                dead.disabled = True
            else:
                button.label = button_value
                dead.label = f'➜  {interaction.user.display_name} survived!'
            await interaction.response.edit_message(view=view)
        # Set button callbacks.
        shoot.callback = button.callback = dead.callback = button_callback
        # Add buttons.
        view.add_item(shoot)
        view.add_item(button)
        view.add_item(dead)
        # Send view.
        await ctx.followup.send(view=view, ephemeral=hidden)

    # ANON ────────────────
    @slash_command(name="anon", description = "-")
    @option("message", description="Anonymouse message", required=True)
    @option("member", description="Direct message target member", required=False, default = None)
    async def anon(self, ctx:discord.ApplicationContext, message:str, member:discord.Member):
        await ctx.defer(ephemeral=True)
        embeded = discord.Embed(description=message).set_footer(icon_url='https://i.gifer.com/L7sU.gif', text='➜ Sent anonymously')
        # Send message anonymously.
        if member is None:
            await ctx.send(embed=embeded)
        else:
            await member.send(embed=embeded)
        # Send confirmation.
        await ctx.followup.send(settings.Localize("anon_message_sent"), ephemeral=True, delete_after=2)

    # REMINDER ────────────────
    @slash_command(name="reminder", description = "-")
    async def remind_me(self, ctx:discord.ApplicationContext):
        await ctx.send_response("Reminder", ephemeral=True)
    
    # PULL/BRING ────────────────
    @slash_command(name="pull", description = "-")
    @guild_only()
    async def pull(self, ctx:discord.ApplicationContext):
        await voice.Connect(ctx)
        await ctx.send_response("Pull", ephemeral=True)

    # REPLAY ────────────────
    @slash_command(name="replay", description = "-")
    @guild_only()
    async def replay(self, ctx:discord.ApplicationContext, seconds:int = 15, pitch:int = 1):
        # TODO: Limit how many times the guild can use the replay command per second (1/2s).        
        await ctx.defer(ephemeral=True)
        # Try to connect to voice channel.
        connection = await voice.Connect(ctx)
        if not connection:
            # Send error message.
            await ctx.followup.send(settings.Localize(connection.message), ephemeral=True)
            return
        # If just joined, send message that he started recording.
        if connection.message != "already_connected":
            await ctx.followup.send(settings.Localize("started_recording"), ephemeral=True)
            return
        # Save replay and 
        file = await voice.SaveReplay(ctx, seconds, pitch)
        await ctx.delete_original_response()
        if file is not None:
            await ctx.channel.send(settings.Localize("recording_complete"), file=file)
            return
        await ctx.followup.send(settings.Localize("recording_failed"), ephemeral=True)