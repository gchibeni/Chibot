import os
import json
import math
from typing import Union
import discord
import pyotp
import socket
import os
from discord.ext import commands
from datetime import datetime, timedelta
import re

#region Variables

LANG = "en" # Same lang code as on locale.json.
AUTH_LIMIT = 12 # 25 is discord's list limit.
TEMPLATE_LIMIT = 24 # 25 is discord's list limit.
TRIGGER_LIMIT = 24 # 25 is discord's list limit.
COMMAND_LIMIT = 24 # 25 is discord's list limit.
THEME_LIMIT = 24 # 25 is discord's list limit.
AUTO_DISCONNECT = True # Check if alone before auto disconnecting.
DISCONNECT_AFTER = 15 # Time in seconds before auto disconnecting.

#endregion

#region Utils

def ConvertSize(size_bytes):
   if size_bytes == 0:
       return "0B"
   size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
   i = int(math.floor(math.log(size_bytes, 1024)))
   p = math.pow(1024, i)
   s = round(size_bytes / p, 2)
   return "%s %s" % (s, size_name[i])

def isValidAuth(auth_secret:str) -> bool:
    # Check if the secret has a valid length.
    if len(auth_secret) not in [16, 32, 64]:
        print("invalid code 1")
        return False
    # Try generating code to ensure its usable.
    try:
        totp = pyotp.TOTP(auth_secret)
        totp.now()
        return True
    except:
        print("invalid code 3")
        return False
    ...

def IsValidDate(day, month, year):
    try:
        # Try getting date time.
        datetime(day=day, month=month, year=year)
        return True
    except:
        return False

def IsOnline(host="8.8.8.8", port=53, timeout=3):
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except socket.error:
        return False

async def ChangeGuildIcon(guild_id:int, icon_name:str, bot: commands.Bot):
    # Check if icon is already in use.
    # Preventing changing icon everytime to the sameone.
    current_icon = GetInfo(guild_id, "current_icon")
    if current_icon == icon_name:
        # print("Guild - Icon already in use.")
        return
    # Check folders and fetch icons.
    path = f'./guilds/{guild_id}/icons'
    os.makedirs(path, exist_ok=True)
    icons = [file for file in os.listdir(path) if file.startswith(icon_name) and file.endswith(('.png', '.jpg', '.jpeg'))]
    if not icons:
        # print("Guild - Icon image not found in the directory.")
        return
    # Select first and only icon found.
    icon_path = os.path.join(path, icons[0])

    # Fetch specified guild.
    guild:discord.Guild = bot.get_guild(guild_id)
    if not guild:
        # print ("Guild - No guild with specified id found.")
        return

    # Open and read the icon image file.
    with open(icon_path, "rb") as icon_file:
        icon_data = icon_file.read()
        try:
            # Edit the guild icon.
            await guild.edit(icon=icon_data)
            SetInfo(guild_id, "current_icon", icon_name)
            print(f"Guild - Guild icon changed for \"{guild.name}\" to \"{icon_name}\"")
        except:
            print(f"Guild - Failed to change guild icon for \"{guild.name}\"")

async def RotateGuildsIcons(bot: commands.Bot):
    # Check if the bot is connected to a guild (server)
    for guild in bot.guilds:
        guild_icons = GetInfo(guild.id, "icons")

        # Check if guild has an icon queue.
        if not guild_icons:
            # print(f"Guild ({guild.name})  - No avatars found for this guild.")
            continue

        # Fetch current time and year
        current_time = datetime.now()
        current_year = current_time.year
        current_hour = current_time.hour

        next_avatar = None
        min_date_difference = timedelta.max
        
        # Find next avatar to be used.
        for date_id, avatar_data in guild_icons.items():
            avatar_date_str = f'{date_id}-{current_year}'
            avatar_date = datetime.strptime(avatar_date_str, f"%d-%m-%Y")
            date_difference = abs(avatar_date - current_time)
            if (date_difference > timedelta(0) and date_difference < min_date_difference):
                min_date_difference = date_difference
                next_avatar = (date_id, avatar_data)
        
        if not next_avatar:
            # print(f"Guild - ({guild.name}) No avatar was picked.")
            continue
        
        avatar_icon = next_avatar[1]["icon"]
        avatar_sleep = next_avatar[1]["sleep"]
        avatar_wake = next_avatar[1]["wake"]
        can_sleep = avatar_sleep and avatar_wake
        is_sleep_time = current_hour >= avatar_sleep or current_hour < avatar_wake

        if can_sleep and is_sleep_time:
            avatar_icon = f'{avatar_icon}_sleep'
        await ChangeGuildIcon(guild.id, avatar_icon, bot)

def IsValidDate(day, month, year):
    try:
        # Try getting date time.
        datetime(day=day, month=month, year=year)
        return True
    except:
        return False

def GetHTTP(url:str, image:bool = False) -> str:
    if not url:
        return None
    # Regular expression for validating a URL
    url = url if url.startswith("http") else f"https://{url}"
    is_valid = IsValidUrl(url) if not image else IsValidUrlImage(url)
    return url if is_valid else None

def IsValidUrl(url: str) -> bool:
    if not url:
        return False
    regex = re.compile(
        r'^(?:http|https)://' # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]*[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' # domain
        r'localhost|' # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|' # ipv4
        r'\[?[A-F0-9]*:[A-F0-9:]+\]?)' # ipv6
        r'(?::\d+)?' # port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE) # path
    return re.match(regex, url) is not None

def IsValidUrlImage(url: str) -> bool:
    if not url:
        return False
    # Regex to check if the URL ends with valid image extensions
    image_extensions = r'.*(?:\.png|\.jpg|\.jpeg|\.gif)$'
    return re.match(image_extensions, url, re.IGNORECASE) is not None and IsValidUrl(url)

def IsValidEmbed(embed: discord.Embed) -> bool:
    return any([
        embed.title,
        embed.description,
        embed.fields,
        embed.footer.text if embed.footer else None,
        embed.image.url if embed.image else None,
        embed.thumbnail.url if embed.thumbnail else None,
    ])

def EmbedClean(embed:discord.Embed, check_valid:bool = False) -> discord.Embed:
    # Fetch or generate embed.
    new_embed = discord.Embed()
    embed = embed or discord.Embed()
    # Copy values.
    new_embed.title = embed.title or ""
    new_embed.description = embed.description or ""
    new_embed.url = GetHTTP(embed.url) or None
    new_embed.colour = embed.colour or None
    new_embed.set_image(url=GetHTTP(embed.image.url, True) or None)
    new_embed.set_thumbnail(url=GetHTTP(embed.thumbnail.url, True) or None)
    new_embed.set_footer(text=embed.footer.text or "",
    icon_url=GetHTTP(embed.footer.icon_url, True) or None
    )
    new_embed.set_author(
        name=embed.author.name or "",
        url=GetHTTP(embed.author.url) or None,
        icon_url=GetHTTP(embed.author.icon_url, True) or None
        )
    # Check and save.

    if check_valid and not IsValidEmbed(new_embed):
        new_embed.description = "ㅤ"
    return new_embed

def Remap(value, in_min, in_max, out_min, out_max):
    return (value - in_min) / (in_max - in_min) * (out_max - out_min) + out_min

#endregion

#region Info

def SetInfo(id:int, key:str, value) -> json:
    # Check paramenters.
    if not id:
        return None
    if not key:
        return None
    # Try getting existent info.
    data:json = {}
    filePath = './settings.json'
    guildId = f'{id}'
    exists = os.path.isfile(filePath)
    if exists:
        with open(filePath, 'r+', encoding='utf-8') as file:
            try: data = json.load(file)
            except: data = {}
    # Check if guild settings exists.
    if guildId not in data:
        data[guildId] = {}
    # Duplicate to get last token.
    lastToken = data[guildId]
    tokens = key.split("/")
    # Loop through all tokens except the last one.
    for token in tokens[:-1]:
        if token not in lastToken:
            lastToken[token] = {}
        lastToken = lastToken[token]
    # Set the final value for the last token.
    if value is None:
        lastToken.pop(tokens[-1], None)
    else:
        lastToken[tokens[-1]] = value
    # Save file.
    jdata = json.dumps(data, indent=2)
    with open(filePath, 'w+', encoding='utf-8') as file: file.write(jdata)
    # Return json data.
    return data
    ...

def GetInfo(id:int, key:str, default = None) -> Union[None, dict, str]:
    # Check parameters.
    if not id:
        return None
    # Try getting existing info.
    data:json = {}
    filePath = './settings.json'
    guildId = f'{id}'
    exists = os.path.isfile(filePath)
    # Try getting existent info.
    if exists:
        with open(filePath, 'r+', encoding='utf-8') as file:
            try: data = json.load(file)
            except: data = {}
    # Check if guild settings exists.
    if guildId not in data:
        data[guildId] = {}
        return default
    if not key:
        return data[guildId]
    # Duplicate to get last token.
    lastToken = data[guildId]
    tokens = key.split("/")
    # Loop through all tokens except the last one
    for token in tokens[:-1]:
        if token not in lastToken:
            # Return default if key was not found.
            return default
        lastToken = lastToken[token]
    
    try:
        if tokens[-1]:
            
            # Return key value.
            return lastToken[tokens[-1]]
        else:
            return None
    except:
        return None
    ...

#endregion

#region Localization

def Localize(key:str, *args) -> str:
    data:json = {}
    filePath = 'locale.json'
    exists = os.path.isfile(f'./{filePath}')
    if exists:
        with open(filePath, 'r+', encoding='utf-8') as file:
            try: data = json.load(file)
            except: data = {}

    keyLower:str = key.lower()
    if keyLower in data:
        if LANG in data:
            return ReplaceArguments(data[keyLower][LANG], *args)
        elif "en" in LANG:
            return ReplaceArguments(data[keyLower]["en"], *args)
    return f"({keyLower})"

def ReplaceArguments(template:str, *args) -> str:
    for i, arg in enumerate(args, start=1):
        placeholder = f"<arg{i}>"
        template = template.replace(placeholder, str(arg))
    return template

#endregion

#region Classes

class ConditionalMessage:
    def __init__(self, value: bool, message: str = ""):
        self.value = value
        self.message = message
    def __bool__(self):
        return self.value
    def __str__(self):
        return self.message
    def not_connected(self):
        return self.message == "not_connected"
    def already_connected(self):
        return self.message == "already_connected"
    def connected(self):
        return self.message == "connected"

#endregion
