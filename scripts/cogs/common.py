from scripts import settings, voice
import discord
from discord.ext import commands
from discord import app_commands
from discord.app_commands import default_permissions, describe, dm_only, guild_only, private_channel_only, command, Range
from discord.ui import Button, View, Select, Modal
import random

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
        await ctx.response.send_message(settings.Localize("lbl_status", settings.MAINTENANCE, settings.LANG), ephemeral=True, delete_after=2)

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
        await ctx.response.send_modal(AnonModal(ctx, user, title=settings.Localize("mdl_anon_title")))

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
        # Generate view and first value.
        view = View()
        flipped = random.randint(0, 1)
        def flipped_name(value):
            return settings.Localize("lbl_flip_head") if value == 0 else settings.Localize("lbl_flip_tail")
        def flipped_emoji(value):
            return settings.Localize("lbl_flip_head_emoji") if value == 0 else settings.Localize("lbl_flip_tail_emoji")
        # Create buttons.
        flip = Button(label=settings.Localize("lbl_flip_title"), style=discord.ButtonStyle.grey, custom_id=str(ctx.user.id))
        button = Button(label="", style=discord.ButtonStyle.blurple, emoji=flipped_emoji(flipped), custom_id=flipped_name(flipped))
        display = Button(label=settings.Localize("lbl_flip_display", ctx.user.display_name, flipped_name(flipped)), style=discord.ButtonStyle.grey, custom_id="0")
        lock = Button(label="", style=discord.ButtonStyle.grey, emoji="🔒")
        # Set callback functions.
        async def button_callback(interaction:discord.Interaction):
            if button.disabled:
                await interaction.response.defer()
                return
            flipped = random.randint(0, 1)
            repeated = int(display.custom_id) # Repeat count.
            if flip.custom_id == str(interaction.user.id) and button.custom_id == flipped_name(flipped):
                repeated = repeated + 1
                button.label = f"x{repeated}"
            else:
                repeated = 0
            display.custom_id = str(repeated) # Save repeat count.
            flip.custom_id = str(interaction.user.id) # Save last user.
            button.custom_id = flipped_name(flipped) # Save last value.
            button.label = "" if repeated == 0 else f"x{repeated}"
            button.emoji = flipped_emoji(flipped)
            display.label = settings.Localize("lbl_flip_display", interaction.user.display_name, flipped_name(flipped))
            await interaction.response.edit_message(view=view)
        async def lock_callback(interaction:discord.Interaction):
            if button.disabled:
                await interaction.response.defer()
                return
            flip.disabled = button.disabled = display.disabled = True
            view.remove_item(lock)
            await interaction.response.edit_message(view=view)
        # Set button callbacks.
        flip.callback = button.callback = display.callback = button_callback
        lock.callback = lock_callback
        # Add buttons.
        view.add_item(flip)
        view.add_item(button)
        view.add_item(display)
        view.add_item(lock)
        # Send view.
        await ctx.followup.send(view=view, ephemeral=hidden)

    # ROLL ────────────────
    @command(name="roll", description = settings.Localize("cmd_roll"))
    @describe(number=settings.Localize("cmd_roll_number"))
    @describe(hidden=settings.Localize("lbl_hidden"))
    async def roll(self, ctx:discord.Interaction, number:Range[int, 2] = 20, hidden:bool = False):
        await ctx.response.defer(thinking=True, ephemeral=hidden)
        # Generate view and first value.
        view = View()
        rolled = random.randint(1, number)
        # Create buttons.
        roll = Button(label=settings.Localize("lbl_roll_title"), style=discord.ButtonStyle.grey)
        button = Button(label=rolled, style=discord.ButtonStyle.blurple)
        display = Button(label=settings.Localize("lbl_roll_display", ctx.user.display_name, number), style=discord.ButtonStyle.grey)
        lock = Button(label="", style=discord.ButtonStyle.grey, emoji="🔒")
        # Set callback function.
        async def button_callback(interaction:discord.Interaction):
            if button.disabled:
                await interaction.response.defer()
                return
            rolled = random.randint(1, number)
            button.label = rolled
            display.label = settings.Localize("lbl_roll_display", interaction.user.display_name, number)
            await interaction.response.edit_message(view=view)
        async def lock_callback(interaction:discord.Interaction):
            if button.disabled:
                await interaction.response.defer()
                return
            roll.disabled = button.disabled = display.disabled = True
            view.remove_item(lock)
            await interaction.response.edit_message(view=view)
        # Set button callbacks.
        roll.callback = button.callback = display.callback = button_callback
        lock.callback = lock_callback
        # Add buttons.
        view.add_item(roll)
        view.add_item(button)
        view.add_item(display)
        view.add_item(lock)
        # Send view.
        await ctx.followup.send(view=view, ephemeral=hidden)

    # ROULETTE ────────────────
    @command(name="roulette", description = "-")
    @describe(hidden=settings.Localize("lbl_hidden"))
    async def roulette(self, ctx:discord.Interaction, hidden:bool = False):
        await ctx.response.defer(thinking=True, ephemeral=hidden)
        # Generate view and dead value.
        view = View()
        dead_value = random.randint(0,5)
        # Create buttons.
        shoot = Button(label=settings.Localize("lbl_roulette_title"), style=discord.ButtonStyle.grey)
        button = Button(label="6", style=discord.ButtonStyle.blurple)
        dead = Button(label=settings.Localize("lbl_roulette_display"), style=discord.ButtonStyle.grey)
        # Set callback function.
        async def button_callback(interaction:discord.Interaction):
            if button.disabled:
                await interaction.response.defer()
                return
            button_value = int(button.label) - 1
            if (dead_value == button_value):
                button.label = "☠️"
                dead.label = settings.Localize("lbl_roulette_died", interaction.user.display_name)
                button.style = discord.ButtonStyle.danger
                button.disabled = True
                shoot.disabled = True
                dead.disabled = True
            else:
                button.label = button_value
                dead.label = settings.Localize("lbl_roulette_survived", interaction.user.display_name)
            await interaction.response.edit_message(view=view)
        # Set button callbacks.
        shoot.callback = button.callback = dead.callback = button_callback
        # Add buttons.
        view.add_item(shoot)
        view.add_item(button)
        view.add_item(dead)
        # Send view.
        await ctx.followup.send(view=view, ephemeral=hidden)

#endregion

#region Voice

    # REPLAY ────────────────
    @command(name="replay", description = settings.Localize("cmd_replay"))
    @guild_only()
    @describe(seconds=settings.Localize("cmd_replay_seconds"))
    @describe(pitch=settings.Localize("cmd_replay_pitch"))
    async def replay(self, ctx:discord.Interaction, seconds:Range[int,5] = 15, pitch:Range[float, 0, 2] = 1):
        # TODO: Limit how many times the guild can use the replay command per second (1/5s).
        await ctx.response.defer(thinking=True, ephemeral=True)
        # Try to connect to voice channel.
        connection = await voice.TryConnect(ctx)
        if not connection:
            # Send error message.
            await ctx.followup.send(settings.Localize(connection.message), ephemeral=True)
            return
        # If just joined, send message that he started recording.
        if connection.message != "already_connected":
            await ctx.followup.send(settings.Localize("lbl_replay_started"), ephemeral=True)
            return
        # Save replay and 
        file = await voice.SaveReplay(ctx, seconds, pitch)
        await ctx.delete_original_response()
        if file is not None:
            await ctx.channel.send(settings.Localize("lbl_replay_complete"), file=file)
            return
        await ctx.followup.send(settings.Localize("lbl_replay_failed"), ephemeral=True)

#endregion

#region Elements

class AnonModal(Modal):
    def __init__(self, ctx:discord.Interaction, user:discord.User, **kwargs):
        super().__init__(**kwargs)
        self.ctx = ctx
        self.user = user
        if user is None:
            target_name = ctx.channel.name
            target_id = ""
        else:
            target_name = user.display_name
            target_id = f"(@{user.global_name})" 
        anon_label = settings.Localize("mdl_anon_target", target_name, target_id)
        # Create inputs.
        self.message_input = discord.ui.TextInput(style=discord.TextStyle.long, label=anon_label, required=True, min_length=4, max_length=280)
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
         # Send confirmation.
        await interaction.response.send_message(settings.Localize("lbl_anon_sent"), ephemeral=True)
        embedded = discord.Embed(description=self.message_input.value).set_footer(icon_url='https://i.gifer.com/L7sU.gif', text=settings.Localize("lbl_anon_footer"))
        # Send message anonymously.
        if self.user is None:
            await interaction.channel.send(embed=embedded)
        else:
            await self.user.send(embed=embedded)

#endregion