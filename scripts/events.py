from scripts import settings, voice
import os
import discord
from discord import app_commands
from discord.ext import commands, tasks
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
            # Foreach server check if there are icon changes.
            await settings.RotateGuildsIcons(bot)
            ...

        @bot.event
        async def on_ready():
            # Initialize all cogs.
            await bot.wait_until_ready()
            cogs = []
            for filename in os.listdir("./scripts/cogs"):
                if (filename.endswith('.py')):
                    await bot.load_extension(f'scripts.cogs.{filename[:-3]}')
                    cogs.append(filename[:-3])
            print(f"\n{Fore.GREEN}─── STATUS ───\n> Cogs started: \"{", ".join(cogs)}\"\n> Connected as: \"{bot.user}\"\n──────────────{Fore.RESET}\n")
            check_updates.start()
            await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="🫵"))
            ...

        @bot.event
        async def on_member_join(member:discord.Member):
            # Responds when a user joins the server.
            channel = discord.utils.get(member.guild.text_channels, name='general')  # Change to your channel name
            if channel:
                await channel.send(f'Welcome to the server, {member.mention}! Feel free to introduce yourself!')
            ...

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
            is_owner = await bot.is_owner(message.author)
            # Check if guild message or private.
            if not guild:
                directed = "Private DM"
            else:
                directed = guild.name
                # Check if called sync command on guild.
                if is_owner and content.lower().startswith("!sync here"):
                    force = content.lower().endswith(" force")
                    clear = content.lower().endswith(" clear")
                    force_str = "" if not force else "(FORCING)"
                    print (f"\n\n{Fore.YELLOW}> {force_str} SYNCING COMMANDS IN GUILD... ({guild.name}){Fore.RESET}")
                    await message.delete()
                    if not clear:
                        await sync(guild, force)
                    else:
                        await sync_clear(guild)
            # Check if called sync command anywhere.
            if is_owner and content.lower().startswith("!sync all"):
                print ("\n\n> SYNCING COMMANDS EVERYWHERE...")
                await message.delete()
                await sync()

            # Check triggers.
            # (Implement trigger checking here)

            # AI answers here.
            # (Implement AI answers here)
            
            # Print message log.
            if not content:
                content = '── EMPTY MESSAGE or embedded MESSAGE ── ]]]'
            print(f'⎾ {directed} ||| {channel} ⏋ ⤵')
            print(f'< {author.id} ||| {author.display_name}> <M>: {content}')
            ...
        
        @bot.event
        async def on_app_command_completion(ctx:discord.Interaction, command:discord.app_commands.Command):
            try:
                # Get variables.
                author = ctx.user
                command = ctx.command
                guild = ctx.guild.name
                channel = ctx.channel.name
                # Print message log.
                if command.name != "anon":
                    print(f'⎾ {guild} ||| {channel} ⏋ ⤵')
                    print(f'< {author.id} ||| {author.display_name}> <C>: Used {command.name} < < < <')
            except: return
            ...

        @bot.event
        async def on_voice_state_update(member:discord.Member, before:discord.VoiceState, after:discord.VoiceState):
            changed_channel = before.channel is not None and before.channel != after.channel
            disconnected = after.channel is None
            if member.id == bot.user.id:
                if changed_channel and not disconnected:
                    #await voice.ClearRecordData(before.channel.guild, False)
                    await voice.Disconnect(before.channel.guild)
                    print("Bot - Changed channel.")
                elif disconnected:
                    await voice.ClearRecordData(before.channel.guild)
                    print("Bot - Disconnected from channel.")
            ...
        
        async def sync(guild:discord.Guild = None, force:bool = False):
            if guild is not None:
                # Sync commands locally.
                if force:
                    commands = await bot.tree.fetch_commands(guild=guild)
                    print(f"{Fore.YELLOW}> Waiting to reset {len(commands)} commands...{Fore.RESET}\n\n")
                    for command in commands:
                        await command.delete()
                bot.tree.copy_global_to(guild=guild)
                synced = await bot.tree.sync(guild=guild)
            else:
                # Sync commands globally.
                synced = await bot.tree.sync()
            # Show confirmation.
            try:
                print(f"{Fore.YELLOW}> Successfully synced {len(synced)} commands.{Fore.RESET}\n\n")
            except Exception as e:
                print(f"{Fore.RED}> Could not sync commands.\nError: {e}{Fore.RESET}\n\n")
            ...

        async def sync_clear(guild:discord.Guild = None):
            if guild is not None:
                # Sync commands locally.
                bot.tree.copy_global_to(guild=guild)
                bot.tree.clear_commands(guild=guild)
                await bot.tree.sync(guild=guild)
            else:
                ...
            print(f"{Fore.YELLOW}> Successfully cleared guild commands.{Fore.RESET}\n\n")
            ...