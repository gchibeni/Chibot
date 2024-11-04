from scripts import settings
import os
import discord
from discord.ext import commands, tasks
from discord import app_commands
from colorama import Fore, init
from datetime import datetime

async def setup(bot: commands.Bot):
    init(autoreset=True)
    bot_events(bot)

class bot_events(commands.Bot):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        @tasks.loop(seconds=1)
        async def check_updates():
            #print(f'\rChecking for updates...\n', end='', flush=True)
            # Check all reminders.
            # Foreach server check if there are avatar changes.
            pass

        @bot.event
        async def on_ready():
            # Initialize all cogs.
            await bot.wait_until_ready()
            for filename in os.listdir("./scripts/cogs"):
                if (filename.endswith('.py')):
                    await bot.load_extension(f'scripts.cogs.{filename[:-3]}')
            await bot.tree.sync(guild=discord.Object(id=295732646535757828))
            #tree.add_command(triggerGroup)
            print(f'\n{Fore.GREEN}─── STATUS ─── Application is up and running!\n[─ Connected as: \"{bot.user}\" ─]{Fore.RESET}\n')
            check_updates.start()

        @bot.event
        async def on_member_join(member):
            # Responds when a user joins the server.
            channel = discord.utils.get(member.guild.text_channels, name='general')  # Change to your channel name
            if channel:
                await channel.send(f'Welcome to the server, {member.mention}! Feel free to introduce yourself!')

        @bot.event
        async def on_message(message: discord.Message):
            author = message.author
            # Avoid responding to itself.
            if author == bot.user:
                return
            # Get variables.
            directed = ""
            guild = message.guild
            content = message.content
            channel = message.channel.id
            # Check if guild message or private.
            if not guild:
                directed = "Private DM"
            else:
                directed = guild.name

            # Check triggers.
            # (Implement trigger checking here)

            # AI answers here.
            # (Implement AI answers here)
            
            # Print message log.
            if not content:
                content = '── EMPTY MESSAGE or EMBEDED MESSAGE ── ]]]'
            print(f'⎾ {directed} ||| {channel} ⏋ ⤵')
            print(f'< {author.id} ||| {author.display_name}> <M>: {content}')

        @bot.event
        async def on_command_error(ctx,error):
            return
        
        @bot.event
        async def on_app_command_completion(ctx: discord.Interaction, command: app_commands.Command):
            try:
                # Get variables.
                author = ctx.user
                command = ctx.command
                guild = ctx.guild.name
                channel = ctx.channel.name
                # Print message log.
                if command != "anon":
                    print(f'⎾ {guild} ||| {channel} ⏋ ⤵')
                    print(f'< {author.id} ||| {author.display_name}> <C>: Used {command.name} < < < <')
            except: return
        
        @bot.event
        async def on_typing(channel:discord.abc.Messageable, user: discord.User, when: datetime.date):
            return
            await channel.send("I can see you typing")

        @bot.event
        async def on_voice_state_update(member:discord.Member, before:discord.VoiceState, after:discord.VoiceState):
            print("Voice state updated")