import random
import os
import json
import math
import discord
import yt_dlp
import pyotp
import socket
import asyncio
import wave
import os
import io
import numpy

from discord import app_commands
from discord.ext import commands, tasks, voice_recv
from datetime import datetime, timezone, timedelta

from collections import deque

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

#endregion

#region Info

def SetInfo(guild_id:int, key:str, value) -> json:
    # Check paramenters.
    if not guild_id:
        return None
    if not key:
        return None
    # Try getting existent info.
    data:json = {}
    filePath = './settings.json'
    guildId = f'{guild_id}'
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

    # 50 20 6 10 16 30 60

def GetInfo(guild_id:int, key:str, default = None) -> json:
    # Check parameters.
    if not guild_id:
        return None
    # Try getting existing info.
    data:json = {}
    filePath = './settings.json'
    guildId = f'{guild_id}'
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

#region Recording

guild_voices = {}

async def Connect(ctx:discord.Interaction, force:bool = False):
    """Connects to the user's current channel and start listening ports."""
    # Initialize variables.
    global guild_voices
    BUFFER_SECONDS = 30 # Limit buffer to specified seconds.
    SAMPLE_RATE = 48000 # Standard audio sample rate for PCM.
    CHANNELS = 2 # Quantity of channels (Stereo or Mono).
    # Check if already connected to any guild's voice channel.
    voice_client:voice_recv.VoiceRecvClient = discord.utils.get(ctx.client.voice_clients, guild=ctx.guild)
    connected = voice_client and voice_client.is_connected()
    same_channel = False if not voice_client else voice_client.channel.id == ctx.user.voice.channel.id
    # Check if bot is not connected to any voice channel.
    if ctx.user.voice is None:
        # Return false if user is not connected to any channel.
        return ConditionalMessage(False, "not_connected")
    # Return false if already connected and not in the same channel.
    if connected and not same_channel and not force:
        return ConditionalMessage(False, "already_connected")
    # Return false if already connected and in the same channel.
    elif connected and same_channel:
        return ConditionalMessage(True, "already_connected")
    # Start reconnection if forced to.
    elif connected and force:
        await Disconnect(ctx.guild)
    # Stores the pcm audio per guild and user.
    guild_voices = {}
    guild_voices[ctx.guild_id] = {}
    # Register each user's voice PCM.
    def callback(user: discord.User, data: voice_recv.VoiceData):
        # TODO: Also include the datetime/time mark of the last time the user spoke,
        # then add silence for every interval the user did not speak.
        try:
            # Initialize a circular buffer (deque) for each user.
            if user not in guild_voices[ctx.guild_id]:
                guild_voices[ctx.guild_id][user] = deque(maxlen=SAMPLE_RATE * BUFFER_SECONDS * CHANNELS * 2)
            # Append new PCM data to the user's buffer.
            guild_voices[ctx.guild_id][user].extend(data.pcm)
        except:
            print("VoiceRecv callback failed")
    # Connect to voice channel and start listeners.
    voice_client = await ctx.user.voice.channel.connect(cls=voice_recv.VoiceRecvClient)
    voice_client.listen(voice_recv.BasicSink(callback))
    # Return true if connected successfully.
    return ConditionalMessage(True, "connected")

async def Disconnect(guild:discord.Guild) -> bool:
    """Disconnects from a guild channel and stops listening ports."""
    # Initialize variables.
    global guild_voices
    # Check if already connected to any guild's voice channel.
    voice_client:voice_recv.VoiceRecvClient = guild.voice_client
    if not voice_client or not voice_client.is_connected():
        # Return false if already not connected.
        return False
    # Stop all listening ports.
    voice_client.stop_listening()
    # Disconnect from voice channel.
    await voice_client.disconnect()
    # Clear guild recorded voice bytes to preserve memory.
    guild_voices[guild.id] = {}
    # Return true if disconnected successfully.
    return True

async def SaveReplay(ctx:discord.Interaction, seconds:int = 5, pitch:int = 1):
    # Initialize variables.
    global guild_voices
    SAMPLE_RATE = 48000 # Standard audio sample rate for PCM.
    CHANNELS = 2 # Quantity of channels (Stereo or Mono).
    PITCH = max(0.5, min(pitch, 1.5)) # Change to specified pitch.
    PITCH = (SAMPLE_RATE * PITCH) - SAMPLE_RATE # Get pitch bitrate.

    # Number of samples to keep for the specified duration.
    num_samples_to_keep = SAMPLE_RATE * CHANNELS * seconds

    # Process the last specified length of audio of every user.
    all_audio = []
    for user, buffer in guild_voices[ctx.guild_id].items():
        # Convert the buffer to a numpy array.
        pcm_data = numpy.frombuffer(bytes(buffer), dtype=numpy.int16)
        # Trim to the last `num_samples_to_keep` samples.
        if len(pcm_data) > num_samples_to_keep:
            pcm_data = pcm_data[-num_samples_to_keep:]
        all_audio.append(pcm_data)
    
    # Mix all users' audio by avaraging the PCM values.
    if all_audio:
        # File name to save the audio.
        filename = f"rec_{ctx.guild_id}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.wav"
        # Pad all audio arrays to the max length with zeros (silence).
        max_length = max(map(len, all_audio))
        padded_audio = [numpy.pad(audio, (0, max_length - len(audio)), mode='constant') for audio in all_audio]
        # Mix all users' audio by averaging the padded PCM values
        mixed_audio = numpy.mean(padded_audio, axis=0).astype(numpy.int16)
        
        with wave.open(f"./recs/{filename}", 'wb') as wav_file:
            wav_file.setnchannels(CHANNELS) # Set as stereo or mono.
            wav_file.setsampwidth(2) # 2 bps (16-bit PCM).
            wav_file.setframerate(SAMPLE_RATE + PITCH) # Set sample bitrate.
            wav_file.writeframes(mixed_audio.tobytes())
        
        print(f"Audio saved as {filename}")
        discord_file = discord.File(f"./recs/{filename}", )
        await ctx.delete_original_response()
        await ctx.channel.send("Recording complete. Audio saved on Desktop.", file=discord_file)
        
        os.remove(f"./recs/{filename}")
    else:
        await ctx.response.edit_message("Could not finish recording.")

class ConditionalMessage:
    def __init__(self, value: bool, message: str = ""):
        self.value = value
        self.message = message
    def __bool__(self):
        return self.value
    def __str__(self):
        return self.message

#endregion