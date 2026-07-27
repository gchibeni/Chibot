from scripts import settings
import asyncio
import discord
from discord.ext import commands
from discord.app_commands import describe, guild_only, command
from discord.ui import Button, View, Select, Modal, TextInput, Label
from datetime import datetime, timedelta, timezone
import math
import re
import time

#region Initialization

async def setup(bot: commands.Bot):
    await bot.add_cog(commands_profiles(bot))

REMINDER_LIMIT = 25  # Reminders a user can have pending.
DAILY_VOICE_POINTS = 100  # First voice join of the day.
DAILY_TEXT_POINTS = 20  # First message of the day.
HOURLY_VOICE_POINTS = 20  # Each full hour spent in voice that day.

_voice_sessions:dict[tuple, float] = {}  # (guild_id, user_id) -> voice join time.
_delivery_wake:asyncio.Event = None  # Wakes the delivery loop on new items.

def _WakeDelivery():
    if _delivery_wake is not None:
        _delivery_wake.set()

class commands_profiles(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._delivery_task = None

    async def cog_load(self):
        global _delivery_wake
        _delivery_wake = asyncio.Event()
        self._delivery_task = asyncio.create_task(self._DeliveryLoop())

    async def cog_unload(self):
        if self._delivery_task is not None:
            self._delivery_task.cancel()

#endregion

#region Commands

    # REMIND ────────────────
    @command(name="remind", description = settings.Localize("cmd_remind"))
    @describe(when=settings.Localize("cmd_remind_when"))
    @describe(message=settings.Localize("cmd_remind_message"))
    async def remind(self, ctx: discord.Interaction, when:str, message:str = ""):
        due = ParseWhen(when, GetTimezone(ctx.user.id))
        if due is None:
            await ctx.response.send_message(settings.Localize("lbl_remind_invalid", guild_id=ctx.guild_id), ephemeral=True)
            return
        # Round up so truncation never fires a second early.
        due = math.ceil(due)
        # Without a message, open a composer like /schedule does.
        if not message.strip():
            await ctx.response.send_modal(RemindModal(ctx, int(due)))
            return
        if not AddReminder(ctx.user.id, int(due), message.strip()):
            await ctx.response.send_message(settings.Localize("lbl_limit_reached", REMINDER_LIMIT, guild_id=ctx.guild_id), ephemeral=True)
            return
        await ctx.response.send_message(settings.Localize("lbl_remind_set", int(due), guild_id=ctx.guild_id), ephemeral=True)

    # SCHEDULE ────────────────
    @command(name="schedule", description = settings.Localize("cmd_schedule"))
    @describe(when=settings.Localize("cmd_remind_when"))
    @describe(user=settings.Localize("cmd_schedule_user"))
    @describe(message=settings.Localize("cmd_schedule_message"))
    async def schedule(self, ctx: discord.Interaction, when:str, user:discord.User = None, message:str = ""):
        due = ParseWhen(when, GetTimezone(ctx.user.id))
        if due is None:
            await ctx.response.send_message(settings.Localize("lbl_remind_invalid", guild_id=ctx.guild_id), ephemeral=True)
            return
        # Round up so truncation never fires a second early.
        due = math.ceil(due)
        # Without a message, open a composer like /anon does.
        if not message.strip():
            await ctx.response.send_modal(ScheduleModal(ctx, int(due), user))
            return
        if not AddSchedule(ctx, int(due), user, message.strip()):
            await ctx.response.send_message(settings.Localize("lbl_limit_reached", REMINDER_LIMIT, guild_id=ctx.guild_id), ephemeral=True)
            return
        await ctx.response.send_message(settings.Localize("lbl_schedule_set", int(due), guild_id=ctx.guild_id), ephemeral=True)

    # PROFILE ────────────────
    @command(name="profile", description = settings.Localize("cmd_profile"))
    @guild_only()
    @describe(user=settings.Localize("cmd_profile_user"))
    async def profile(self, ctx: discord.Interaction, user:discord.Member = None):
        await ctx.response.defer(ephemeral=True)
        member = user or ctx.user
        is_self = member.id == ctx.user.id
        # Your own profile is editable, admins can edit anyone's.
        # followup.send rejects an explicit view=None, so it is omitted.
        if is_self or ctx.user.guild_permissions.administrator:
            await ctx.followup.send(embed=ProfileEmbed(member, is_self), view=ProfileView(ctx, member), ephemeral=True)
        else:
            await ctx.followup.send(embed=ProfileEmbed(member, is_self), ephemeral=True)

    # The edit button is raw-handled so the panel never expires. The
    # edited user's id rides in the custom_id, so admins can edit others.
    @commands.Cog.listener("on_interaction")
    async def handle_components(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component or interaction.guild is None:
            return
        custom_id = (interaction.data or {}).get("custom_id") or ""
        if custom_id.startswith("profile_edit"):
            target_id = interaction.user.id
            if "|" in custom_id:
                try:
                    target_id = int(custom_id.split("|", 1)[1])
                except ValueError:
                    pass
            if target_id != interaction.user.id and not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message(settings.Localize("lbl_no_permission", guild_id=interaction.guild_id), ephemeral=True)
                return
            target = interaction.guild.get_member(target_id)
            if target is None:
                await interaction.response.send_message(settings.Localize("lbl_item_not_found", guild_id=interaction.guild_id), ephemeral=True)
                return
            await interaction.response.send_modal(ProfileModal(interaction, target, title=settings.Localize("mdl_profile_title", guild_id=interaction.guild_id)))

#endregion

#region Rewards

    @commands.Cog.listener("on_message")
    async def reward_text(self, message: discord.Message):
        # First message of the day earns points.
        if message.guild is None or message.author.bot:
            return
        daily = _GetDaily(message.guild.id, message.author.id)
        if not daily.get("text"):
            daily["text"] = True
            _SaveDaily(message.guild.id, message.author.id, daily)
            _AddPoints(message.guild.id, message.author.id, DAILY_TEXT_POINTS)

    @commands.Cog.listener("on_voice_state_update")
    async def track_voice(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        key = (member.guild.id, member.id)
        joined = before.channel is None and after.channel is not None
        left = before.channel is not None and after.channel is None
        if joined:
            _voice_sessions[key] = time.time()
            # First voice join of the day earns points.
            daily = _GetDaily(member.guild.id, member.id)
            if not daily.get("voice"):
                daily["voice"] = True
                _SaveDaily(member.guild.id, member.id, daily)
                _AddPoints(member.guild.id, member.id, DAILY_VOICE_POINTS)
        elif left:
            start = _voice_sessions.pop(key, None)
            if start is not None:
                _AddVoiceTime(member, time.time() - start)

#endregion

#region Reminders

    async def _DeliveryLoop(self):
        """Sleep precisely until the next due reminder or schedule, waking
        early whenever a new item is added, then deliver."""
        await self.bot.wait_until_ready()
        while True:
            try:
                wait = self._NextDue() - time.time()
                if wait > 0:
                    try:
                        # Cap the sleep so external edits are still noticed.
                        await asyncio.wait_for(_delivery_wake.wait(), timeout=min(wait, 30))
                        _delivery_wake.clear()
                        continue  # A new item arrived: recompute the wait.
                    except asyncio.TimeoutError:
                        pass
                await self._DeliverDue()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"Reminders - Delivery loop error.\nErrors: {e}\n")
                await asyncio.sleep(5)

    def _NextDue(self) -> float:
        """The earliest pending due time, or a short poll interval."""
        due_times = []
        reminders = settings.GetInfo("reminders", None) or {}
        for items in reminders.values():
            if isinstance(items, list):
                due_times += [item.get("due", 0) for item in items]
        schedules = settings.GetInfo("schedules", "items") or []
        due_times += [item.get("due", 0) for item in schedules]
        return min(due_times) if due_times else time.time() + 30

    async def _DeliverDue(self):
        """Deliver due reminders by DM and due scheduled messages."""
        now = time.time()
        reminders = settings.GetInfo("reminders", None) or {}
        for user_id, items in list(reminders.items()):
            if not isinstance(items, list):
                continue
            due_items = [item for item in items if item.get("due", 0) <= now]
            if not due_items:
                continue
            remaining = [item for item in items if item.get("due", 0) > now]
            settings.SetInfo("reminders", user_id, remaining or None)
            for item in due_items:
                try:
                    user = self.bot.get_user(int(user_id)) or await self.bot.fetch_user(int(user_id))
                    # Anon-style embed, footer showing how long ago it was set.
                    elapsed = FormatSpan(now - item.get("created", item.get("due", now)))
                    embedded = discord.Embed(description=item.get("message", ""))
                    embedded.set_footer(text=settings.Localize("lbl_remind_footer", elapsed))
                    await user.send(embed=embedded)
                except Exception as e:
                    print(f"Reminders - Could not deliver a reminder to {user_id}.\nErrors: {e}\n")
        # Deliver due scheduled messages.
        schedules = settings.GetInfo("schedules", "items") or []
        due_schedules = [item for item in schedules if item.get("due", 0) <= now]
        if due_schedules:
            remaining = [item for item in schedules if item.get("due", 0) > now]
            settings.SetInfo("schedules", "items", remaining or None)
        for item in due_schedules:
            try:
                embedded = discord.Embed(description=item.get("message", ""))
                embedded.set_footer(icon_url=item.get("author_avatar") or "https://i.gifer.com/L7sU.gif", text=settings.Localize("lbl_schedule_footer", item.get("author_name", "?"), guild_id=item.get("guild")))
                if item.get("target"):
                    target = self.bot.get_user(int(item["target"])) or await self.bot.fetch_user(int(item["target"]))
                    await target.send(embed=embedded)
                else:
                    channel = self.bot.get_channel(int(item["channel"])) or await self.bot.fetch_channel(int(item["channel"]))
                    await channel.send(embed=embedded)
            except Exception as e:
                print(f"Schedules - Could not deliver a scheduled message.\nErrors: {e}\n")

#endregion

#region Utils

# Common timezones for the profile dropdown: stored value is the UTC
# offset in hours. Fixed offsets, so DST shifts are not tracked.
TIMEZONE_OPTIONS = [
    ("-11", "SST — Samoa (UTC-11)"),
    ("-10", "HST — Hawaii (UTC-10)"),
    ("-9", "AKST — Alaska (UTC-9)"),
    ("-8", "PST — Pacific (UTC-8)"),
    ("-7", "MST — Mountain (UTC-7)"),
    ("-6", "CST — Central (UTC-6)"),
    ("-5", "EST — Eastern (UTC-5)"),
    ("-4", "AST — Atlantic (UTC-4)"),
    ("-3", "BRT — Brasília (UTC-3)"),
    ("-2", "GST — South Georgia (UTC-2)"),
    ("-1", "AZOT — Azores (UTC-1)"),
    ("0", "UTC / GMT — London (UTC+0)"),
    ("1", "CET — Central Europe (UTC+1)"),
    ("2", "EET — Eastern Europe (UTC+2)"),
    ("3", "MSK — Moscow (UTC+3)"),
    ("4", "GST — Gulf (UTC+4)"),
    ("5", "PKT — Pakistan (UTC+5)"),
    ("5.5", "IST — India (UTC+5:30)"),
    ("7", "ICT — Indochina (UTC+7)"),
    ("8", "HKT — Hong Kong (UTC+8)"),
    ("9", "JST — Japan (UTC+9)"),
    ("10", "AEST — Australia East (UTC+10)"),
    ("12", "NZST — New Zealand (UTC+12)"),
]

# Discord only exposes the user's language, not their timezone, so the
# locale is used as a best-effort default until the user picks one.
LOCALE_TIMEZONES = {
    "pt-BR": -3, "en-US": -5, "es-419": -6, "en-GB": 0, "de": 1, "fr": 1,
    "es-ES": 1, "it": 1, "nl": 1, "pl": 1, "sv-SE": 1, "cs": 1, "hr": 1,
    "hu": 1, "da": 1, "no": 1, "fi": 2, "el": 2, "ro": 2, "uk": 2,
    "bg": 2, "lt": 2, "tr": 3, "ru": 3, "hi": 5.5, "th": 7, "vi": 7,
    "id": 7, "zh-CN": 8, "zh-TW": 8, "ja": 9, "ko": 9,
}

RELATIVE_UNITS = { "y":31536000, "mo":2592000, "w":604800, "d":86400, "h":3600, "m":60, "s":1 }
RELATIVE_PATTERN = re.compile(r"(\d+)(mo|[ywdhms])")

# Named timezones accepted inside /remind and /schedule times.
TIMEZONE_ABBREVIATIONS = {
    "sst":-11, "hst":-10, "akst":-9, "pst":-8, "pdt":-7, "mst":-7, "mdt":-6,
    "cst":-6, "cdt":-5, "est":-5, "edt":-4, "ast":-4, "brt":-3, "art":-3,
    "azot":-1, "utc":0, "gmt":0, "wet":0, "bst":1, "cet":1, "cest":2,
    "eet":2, "eest":3, "msk":3, "gst":4, "pkt":5, "ist":5.5, "ict":7,
    "wib":7, "hkt":8, "sgt":8, "awst":8, "jst":9, "kst":9, "acst":9.5,
    "aest":10, "aedt":11, "nzst":12,
}

def ParseWhen(text:str, tz_offset:float) -> float:
    """Parse a reminder/schedule time into a unix timestamp, or None.

    The text is a mix of space-separated tokens, in any order:
    - relative spans: "10s", "1h20m", "5d", "1y" (d/w/mo/y shift days)
    - "today" / "tomorrow" (tomorrow alone defaults to 6am)
    - clock times: "19:20", "9am", "9:30pm"
    - a timezone: "brt", "pst"... or a @user mention (their timezone)
    Examples: "tomorrow 9am", "5d 9am", "9pm brt", "tomorrow 9am @user"."""
    tokens = text.strip().lower().split()
    if not tokens:
        return None
    offset = tz_offset
    day_seconds = 0  # Whole-day shifts (tomorrow, 5d, 1w...).
    span_seconds = 0  # Sub-day shifts (10s, 1h20m...).
    clock = None
    has_day = False
    saw_tomorrow = False
    for token in tokens:
        mention = re.fullmatch(r"<@!?(\d+)>", token)
        if mention:
            # Clock times are read in the mentioned user's timezone.
            offset = GetTimezone(int(mention.group(1)))
            continue
        if token == "today":
            has_day = True
            continue
        if token == "tomorrow":
            day_seconds += 86400
            has_day = saw_tomorrow = True
            continue
        if token in TIMEZONE_ABBREVIATIONS:
            offset = TIMEZONE_ABBREVIATIONS[token]
            continue
        match = re.fullmatch(r"(\d{1,2}):(\d{2})", token)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            if hour > 23 or minute > 59:
                return None
            clock = (hour, minute)
            continue
        match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?(am|pm)", token)
        if match:
            hour = int(match.group(1)) % 12 + (12 if match.group(3) == "pm" else 0)
            minute = int(match.group(2) or 0)
            if hour > 23 or minute > 59:
                return None
            clock = (hour, minute)
            continue
        if re.fullmatch(r"(?:\d+(?:mo|[ywdhms]))+", token):
            for value, unit in RELATIVE_PATTERN.findall(token):
                if unit in ("y", "mo", "w", "d"):
                    day_seconds += int(value) * RELATIVE_UNITS[unit]
                    has_day = True
                else:
                    span_seconds += int(value) * RELATIVE_UNITS[unit]
            continue
        return None
    now = time.time()
    # "tomorrow" alone keeps its old meaning: 6am the next local day.
    if clock is None and saw_tomorrow and span_seconds == 0:
        clock = (6, 0)
    if clock is None:
        total = day_seconds + span_seconds
        return now + total if total > 0 else None
    # Anchor the clock time on the shifted day, in the resolved timezone.
    local_now = datetime.fromtimestamp(now, tz=timezone.utc) + timedelta(hours=offset)
    target = (local_now + timedelta(seconds=day_seconds)).replace(hour=clock[0], minute=clock[1], second=0, microsecond=0)
    target += timedelta(seconds=span_seconds)
    if target <= local_now and not has_day:
        target += timedelta(days=1)
    return now + (target - local_now).total_seconds()

def AddReminder(user_id:int, due:int, message:str) -> bool:
    """Store a reminder; False when the user hit the limit."""
    reminders = settings.GetInfo("reminders", f"{user_id}") or []
    if len(reminders) >= REMINDER_LIMIT:
        return False
    reminders.append({ "due":int(due), "message":message, "created":int(time.time()) })
    settings.SetInfo("reminders", f"{user_id}", reminders)
    _WakeDelivery()
    return True

def FormatSpan(seconds:float) -> str:
    """Compact span like "10d", "3h" or "20s", using the largest unit."""
    seconds = max(int(seconds), 0)
    for unit, size in (("y", 31536000), ("mo", 2592000), ("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"

def AddSchedule(ctx:discord.Interaction, due:int, target:discord.User, message:str) -> bool:
    """Store a scheduled message; False when the author hit the limit.
    Without a target user it posts back to the invoking channel."""
    items = settings.GetInfo("schedules", "items") or []
    if len([item for item in items if item.get("author") == ctx.user.id]) >= REMINDER_LIMIT:
        return False
    items.append({
        "due": int(due),
        "message": message,
        "guild": ctx.guild_id,
        "channel": None if target else ctx.channel_id,
        "target": target.id if target else None,
        "author": ctx.user.id,
        "author_name": ctx.user.display_name,
        "author_avatar": ctx.user.display_avatar.url,
    })
    settings.SetInfo("schedules", "items", items)
    _WakeDelivery()
    return True

def GetTimezone(user_id:int) -> float:
    """The user's UTC offset in hours. Users without one follow the bot
    host machine's local timezone."""
    try:
        stored = settings.GetInfo(f"user-{user_id}", "profile/timezone")
        if stored is not None:
            return float(stored)
    except (TypeError, ValueError):
        pass
    return datetime.now().astimezone().utcoffset().total_seconds() / 3600

def _GetDaily(guild_id:int, user_id:int) -> dict:
    """Today's reward flags, reset when the stored day changed."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily = settings.GetInfo(guild_id, f"profiles/{user_id}/daily") or {}
    if daily.get("date") != today:
        daily = { "date":today }
    return daily

def _SaveDaily(guild_id:int, user_id:int, daily:dict):
    settings.SetInfo(guild_id, f"profiles/{user_id}/daily", daily)

def _AddPoints(guild_id:int, user_id:int, amount:int):
    points = settings.GetInfo(guild_id, f"profiles/{user_id}/points") or 0
    settings.SetInfo(guild_id, f"profiles/{user_id}/points", int(points) + amount)

def _AddVoiceTime(member:discord.Member, seconds:float):
    """Add a finished voice session to the month total and reward every
    new full hour spent in voice today."""
    guild_id, user_id = member.guild.id, member.id
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    total = settings.GetInfo(guild_id, f"profiles/{user_id}/voice/{month}") or 0
    settings.SetInfo(guild_id, f"profiles/{user_id}/voice/{month}", int(total + seconds))
    daily = _GetDaily(guild_id, user_id)
    daily["seconds"] = int(daily.get("seconds", 0) + seconds)
    hours = daily["seconds"] // 3600
    rewarded = daily.get("hours_rewarded", 0)
    if hours > rewarded:
        daily["hours_rewarded"] = hours
        _AddPoints(guild_id, user_id, (hours - rewarded) * HOURLY_VOICE_POINTS)
    _SaveDaily(guild_id, user_id, daily)

def GetVoiceSeconds(member:discord.Member) -> int:
    """Voice seconds this month, including the running session."""
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    total = settings.GetInfo(member.guild.id, f"profiles/{member.id}/voice/{month}") or 0
    start = _voice_sessions.get((member.guild.id, member.id))
    if start is not None:
        total += time.time() - start
    return int(total)

#endregion

#region Elements

def ProfileEmbed(member:discord.Member, is_self:bool) -> discord.Embed:
    guild_id = member.guild.id
    profile = settings.GetInfo(f"user-{member.id}", "profile") or {}
    points = settings.GetInfo(guild_id, f"profiles/{member.id}/points") or 0
    seconds = GetVoiceSeconds(member)
    hours, minutes = int(seconds // 3600), int(seconds % 3600 // 60)
    roles = [role.mention for role in reversed(member.roles) if role != member.guild.default_role]
    embedded = discord.Embed(title=member.display_name)
    embedded.set_thumbnail(url=member.display_avatar.url)
    embedded.add_field(name=settings.Localize("lbl_profile_joined", guild_id=guild_id), value=f"<t:{int(member.joined_at.timestamp())}:D>" if member.joined_at else "—", inline=True)
    embedded.add_field(name=settings.Localize("lbl_profile_voice", guild_id=guild_id), value=f"{hours}h {minutes}m", inline=True)
    embedded.add_field(name=settings.Localize("lbl_profile_points", guild_id=guild_id), value=f"{points}", inline=True)
    embedded.add_field(name=settings.Localize("lbl_profile_title", guild_id=guild_id), value=profile.get("title") or "—", inline=True)
    # Birthdays can be hidden from other users.
    birthday = profile.get("birthday")
    if birthday and (is_self or not profile.get("hide_birthday")):
        embedded.add_field(name=settings.Localize("lbl_profile_birthday", guild_id=guild_id), value=birthday, inline=True)
    embedded.add_field(name=settings.Localize("lbl_profile_roles", guild_id=guild_id), value=" ".join(roles) if roles else "—", inline=False)
    return embedded

class ProfileView(View):
    def __init__(self, ctx:discord.Interaction, target:discord.Member, warning:str = None, **kwargs):
        kwargs.setdefault("timeout", None)
        super().__init__(**kwargs)
        if warning is not None:
            warning_button = Button(label=warning, style=discord.ButtonStyle.grey, row=1, disabled=True)
            self.add_item(warning_button)
        edit_button = Button(label=settings.Localize("lbl_profile_edit", guild_id=ctx.guild_id), style=discord.ButtonStyle.blurple, row=2, custom_id=f"profile_edit|{target.id}")
        self.add_item(edit_button)

class RemindModal(Modal):
    """Message composer for /remind when no message was given."""
    def __init__(self, ctx:discord.Interaction, due:int, **kwargs):
        kwargs.setdefault("title", settings.Localize("mdl_remind_title", guild_id=ctx.guild_id))
        super().__init__(**kwargs)
        self.due = due
        self.message_input = TextInput(style=discord.TextStyle.long, label=settings.Localize("mdl_schedule_label", guild_id=ctx.guild_id), required=True, min_length=1, max_length=2000)
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not AddReminder(interaction.user.id, self.due, self.message_input.value.strip()):
            await interaction.response.send_message(settings.Localize("lbl_limit_reached", REMINDER_LIMIT, guild_id=interaction.guild_id), ephemeral=True)
            return
        await interaction.response.send_message(settings.Localize("lbl_remind_set", self.due, guild_id=interaction.guild_id), ephemeral=True)

class ScheduleModal(Modal):
    """Message composer for /schedule when no message was given."""
    def __init__(self, ctx:discord.Interaction, due:int, target:discord.User = None, **kwargs):
        kwargs.setdefault("title", settings.Localize("mdl_schedule_title", guild_id=ctx.guild_id))
        super().__init__(**kwargs)
        self.due = due
        self.target = target
        self.message_input = TextInput(style=discord.TextStyle.long, label=settings.Localize("mdl_schedule_label", guild_id=ctx.guild_id), required=True, min_length=1, max_length=2000)
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not AddSchedule(interaction, self.due, self.target, self.message_input.value.strip()):
            await interaction.response.send_message(settings.Localize("lbl_limit_reached", REMINDER_LIMIT, guild_id=interaction.guild_id), ephemeral=True)
            return
        await interaction.response.send_message(settings.Localize("lbl_schedule_set", self.due, guild_id=interaction.guild_id), ephemeral=True)

class ProfileModal(Modal):
    def __init__(self, ctx:discord.Interaction, target:discord.Member, **kwargs):
        super().__init__(**kwargs)
        self.target = target
        guild_id = ctx.guild_id
        profile = settings.GetInfo(f"user-{target.id}", "profile") or {}
        # Discord never exposes the real timezone: fall back to a guess
        # from the client language when users edit their own profile.
        current_timezone = profile.get("timezone")
        if current_timezone is None and target.id == ctx.user.id:
            current_timezone = LOCALE_TIMEZONES.get(str(ctx.locale))
        current_value = None if current_timezone is None else f"{float(current_timezone):g}"
        # Create inputs.
        self.birthday_input = TextInput(style=discord.TextStyle.short, label=settings.Localize("mdl_profile_birthday", guild_id=guild_id), required=False, max_length=10, placeholder="dd/mm/yyyy", default=profile.get("birthday"))
        self.timezone_select = Select()
        for value, label in TIMEZONE_OPTIONS:
            self.timezone_select.add_option(value=value, label=label, default=(value == current_value))
        self.hide_select = Select()
        self.hide_select.add_option(value="show", label=settings.Localize("lbl_profile_show", guild_id=guild_id), default=not profile.get("hide_birthday"))
        self.hide_select.add_option(value="hide", label=settings.Localize("lbl_profile_hidden", guild_id=guild_id), default=bool(profile.get("hide_birthday")))
        # Add inputs.
        self.add_item(self.birthday_input)
        self.add_item(Label(text=settings.Localize("mdl_profile_timezone", guild_id=guild_id), description=settings.Localize("mdl_profile_timezone_desc", guild_id=guild_id), component=self.timezone_select))
        self.add_item(Label(text=settings.Localize("mdl_profile_hide", guild_id=guild_id), component=self.hide_select))

    async def on_submit(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        warning = None
        # Validate the birthday.
        birthday = self.birthday_input.value.strip()
        if birthday:
            parts = birthday.split("/")
            valid = len(parts) in (2, 3) and all(part.isdigit() for part in parts)
            if valid:
                year = int(parts[2]) if len(parts) == 3 else 2000
                valid = settings.IsValidDate(int(parts[0]), int(parts[1]), year)
            if not valid:
                warning = settings.Localize("lbl_profile_invalid_birthday", guild_id=guild_id)
                birthday = None
        # The timezone comes from the dropdown, keeping the stored value
        # when nothing was selected.
        offset = settings.GetInfo(f"user-{self.target.id}", "profile/timezone")
        if self.timezone_select.values:
            offset = float(self.timezone_select.values[0])
        # Save the target's profile (own, or anyone's when edited by an admin).
        key = f"user-{self.target.id}"
        settings.SetInfo(key, "profile/birthday", birthday or None)
        settings.SetInfo(key, "profile/timezone", offset)
        settings.SetInfo(key, "profile/hide_birthday", True if self.hide_select.values and self.hide_select.values[0] == "hide" else None)
        await interaction.response.edit_message(embed=ProfileEmbed(self.target, True), view=ProfileView(interaction, self.target, warning))

#endregion
