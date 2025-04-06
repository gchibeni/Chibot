from scripts import settings, voice, elements
import os
import discord
from discord.ui import View, Button, Select
from discord.ext import commands, tasks
from colorama import Fore, init
import asyncio

#region Initialization

async def setup(bot: commands.Bot):
    init(autoreset=True)
    bot_events(bot)

class bot_events(commands.Bot):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tasks = {}

#endregion

#region Events

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
            guild = member.guild
            voice_client = guild.voice_client
            changed_channel = before.channel is not None and before.channel != after.channel
            disconnected = after.channel is None
            if member.id == bot.user.id:
                # Check if bot changed channel.
                if changed_channel and not disconnected:
                    after_copy = after.channel
                    await voice.Disconnect(guild)
                    await voice.Connect(after_copy)
                    print("Bot - Changed channel.")
                elif disconnected:
                    voice.ClearRecordData(guild)
                    print("Bot - Disconnected from channel.")
            if voice_client and settings.AUTO_DISCONNECT:
                # Check if bot is alone.
                bot_channel:discord.VoiceChannel = voice_client.channel
                user_quantity = len(bot_channel.members)
                if before.channel and before.channel.id == bot_channel.id and user_quantity == 1:
                    start_checking(guild)
                elif after.channel and after.channel.id == bot_channel.id:
                    if user_quantity == 1:
                        start_checking(guild) 
                    else:
                        stop_checking(guild)
            ...

        @bot.event
        async def on_interaction(interaction:discord.Interaction):
            custom_id = interaction.data.get("custom_id")
            if not custom_id:
                return
            if custom_id.startswith("lock"):
                # Lock interaction.
                view = View.from_message(interaction.message)
                for item in view.children[:]:
                    if isinstance(item, Button) or isinstance(item, Select):
                        if item.custom_id == "lock":
                            view.remove_item(item)
                        else:
                            item.disabled = True
                await interaction.response.edit_message(view=view)
            if custom_id.startswith("flip"):
                # Flip interaction.
                await interaction.response.edit_message(view=elements.FlipView(interaction))
            if custom_id.startswith("roll"):
                # Roll interaction.
                await interaction.response.edit_message(view=elements.RollView(interaction))
            if custom_id.startswith("roulette"):
                # Roulette interaction.
                await interaction.response.edit_message(view=elements.RouletteView(interaction))
            if custom_id.startswith("play"):
                # Music message play interaction.
                print("play called")
            if custom_id.startswith("stop"):
                # Music message stop interaction.
                print("stop called")
            if custom_id.startswith("next"):
                # Music message next interaction.
                print("next called")
            if custom_id.startswith("prev"):
                # Music message prev interaction.
                print("prev called")
            if custom_id.startswith("clear"):
                # Music message clear interaction.
                print("clear called")
            if custom_id.startswith("download"):
                # Music message download interaction.
                print("download called")
            ...

#endregion

#region Functions

        def start_checking(guild:discord.Guild):
            """Start checking bot is alone in a voice chat before disconnecting automatically"""
            if guild not in self.tasks:
                self.tasks[guild] = None
            guild_task:asyncio.Task = self.tasks[guild]
            if guild_task and not guild_task.done():
                guild_task.cancel()
                self.tasks[guild] = None
            else:
                self.tasks[guild] = asyncio.create_task(check_users(guild))

        def stop_checking(guild:discord.Guild):
            """Stop checking bot is alone in a voice chat before disconnecting automatically"""
            if guild not in self.tasks:
                return
            guild_task:asyncio.Task = self.tasks[guild]
            if guild_task:
                guild_task.cancel()
                self.tasks[guild] = None
            ...

        async def check_users(guild:discord.Guild):
            """Check checking bot is alone in a voice chat before disconnecting automatically"""
            voice_client = guild.voice_client
            await asyncio.sleep(settings.DISCONNECT_AFTER)
            if voice_client:
                channel:discord.VoiceChannel = voice_client.channel
                user_quantity = len(channel.members)
                if user_quantity == 1:
                    await voice.Disconnect(guild)
                    self.tasks[guild] = None
            ...
        
        async def sync(guild:discord.Guild = None, force:bool = False):
            if guild is not None:
                # Sync commands locally.
                bot.tree.clear_commands(guild=guild)
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

#endregion