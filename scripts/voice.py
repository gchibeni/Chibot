from scripts import settings
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
        return settings.ConditionalMessage(False, "not_connected")
    # Return false if already connected and not in the same channel.
    if connected and not same_channel and not force:
        return settings.ConditionalMessage(False, "already_connected")
    # Return false if already connected and in the same channel.
    elif connected and same_channel:
        return settings.ConditionalMessage(True, "already_connected")
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
    return settings.ConditionalMessage(True, "connected")

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

async def SaveReplay(ctx:discord.Interaction, seconds:int = 5, pitch:int = 1) -> discord.File:
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
        # Create a memory buffer for the audio data
        with io.BytesIO() as audio_buffer:
            # Pad all audio arrays to the max length with zeros (silence)
            max_length = max(map(len, all_audio))
            padded_audio = [numpy.pad(audio, (0, max_length - len(audio)), mode='constant') for audio in all_audio]
            # Mix all users' audio by averaging the padded PCM values
            mixed_audio = numpy.mean(padded_audio, axis=0).astype(numpy.int16)
            # Write the mixed audio to the memory buffer as a .wav file
            with wave.open(audio_buffer, 'wb') as wav_file:
                wav_file.setnchannels(CHANNELS)  # Set as stereo or mono
                wav_file.setsampwidth(2)         # 2 bps (16-bit PCM)
                wav_file.setframerate(SAMPLE_RATE + PITCH)  # Set sample bitrate
                wav_file.writeframes(mixed_audio.tobytes())
            # Move to the start of the buffer before sending
            audio_buffer.seek(0)
            print(f"Audio saved as {filename}")
            file = discord.File(audio_buffer, filename)
            return file
    return None