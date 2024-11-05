import random
import os
import json
import math
import discord
from discord import app_commands
from discord.ext import commands, tasks
import yt_dlp
import pyotp

#region Variables

maintenance = False
lang = "en"

# Configure youtube_dl to get audio from URL
ytdl_settings = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }]
}

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

async def ChangeGuildIcon(bot: commands.Bot):
    # # Check if the bot is connected to a guild (server)
    # for guild in bot.guilds:
    #     # Get a list of image files in the ICON_DIRECTORY
    #     icons = [file for file in os.listdir(ICON_DIRECTORY) if file.endswith(('.png', '.jpg', '.jpeg'))]
    #     if not icons:
    #         print("No images found in the icons directory.")
    #         return

    #     # Select an icon file randomly
    #     icon_path = os.path.join(ICON_DIRECTORY, icons[0])
        
    #     # Open and read the icon image file
    #     with open(icon_path, "rb") as icon_file:
    #         icon_data = icon_file.read()
    #         try:
    #             # Edit the guild (server) icon
    #             await guild.edit(icon=icon_data)
    #             print(f"Server icon changed for {guild.name} to {icon_path}")
    #         except Exception as e:
    #             print(f"Failed to change server icon for {guild.name}: {e}")

    #     # Rotate the icon list to select a new one next time
    #     icons.append(icons.pop(0))
    pass

#endregion

#region Info

def SetInfo(guild:int, key:str, value) -> json:
    # Check paramenters.
    if not guild:
        return None
    if not key:
        return None
    # Try getting existent info.
    data:json = {}
    filePath = 'settings.json'
    guildId = f'{guild}'
    exists = os.path.isfile(f'./{filePath}')
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

def GetInfo(guild, key, default = None):
    # Check parameters.
    if not guild:
        return None
    # Try getting existing info.
    data:json = {}
    filePath = 'guilds.json'
    guildId = f'{guild}'
    exists = os.path.isfile(f'./{filePath}')
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
        return data[guild]
    # Duplicate to get last token.
    lastToken = data[guildId]
    tokens = key.split("/")
    # Loop through all tokens except the last one
    for token in tokens[:-1]:
        if token not in lastToken:
            # Return default if key was not found.
            return default
        lastToken = lastToken[token]
    
    if tokens[-1]:
        # Return key value.
        return lastToken[tokens[-1]]
    else:
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
        if lang in data:
            return ReplaceArguments(data[keyLower][lang], *args)
        elif "en" in lang:
            return ReplaceArguments(data[keyLower]["en"], *args)
    return f"({keyLower}) - Localization not found."

def ReplaceArguments(template:str, *args) -> str:
    for i, arg in enumerate(args, start=1):
        placeholder = f"<arg{i}>"
        template = template.replace(placeholder, str(arg))
    return template

#endregion