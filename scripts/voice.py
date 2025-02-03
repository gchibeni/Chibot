from scripts import settings
import yt_dlp
import wave
import os
import io
import numpy
import time
import discord
from datetime import datetime
from collections import deque
from discord.ext.voice_recv import VoiceData, VoiceRecvClient, BasicSink
import collections
import re
from pydub import AudioSegment

#region Global

BUFFER_DURATION = 30  # Duration of the buffer in seconds
SAMPLE_RATE = 48000  # Discord uses 48kHz
CHANNELS = 2  # Stereo audio
BYTES_PER_SAMPLE = 2  # 16-bit PCM (2 bytes per sample)
BUFFER_SIZE = BUFFER_DURATION * 1000

ffmpeg_settings = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn -bufsize 8192",  # No video, set buffer size
}

# Configure youtube_dl to get audio from URL
ytdl_settings = {
    "format": "bestaudio/best",  # Get the best available audio format
    "quiet": True,  # Suppress output to the console
    "no_warnings": True,  # Suppress warnings
    "noplaylist": True,  # Ignore playlists
    "default_search": "ytsearch",  # Allow direct search queries
    "postprocessors": [{
        "key": "FFmpegExtractAudio",
        "preferredcodec": "mp3",  # Convert audio to MP3
        "preferredquality": "192",  # Audio quality (192kbps)
    }],
}

ytdl = yt_dlp.YoutubeDL(ytdl_settings)


class RecordData():
    def __init__(self):
        self.start_timestamp = time.time()
        self.segments:dict[discord.User, AudioSegment] = {}
        self.timestamps:dict[discord.User, float] = {}
        ...

    def AddChunk(self, user: discord.User, pcm_data: bytes):
        """
        Increment received audio chunk to user buffer.
        """
        # Initialize buffer for each user.
        if user not in self.segments:
            self.segments[user] = AudioSegment.silent(duration=0, frame_rate=SAMPLE_RATE)
            self.timestamps[user] = self.start_timestamp
        # Get elapsed time.
        last_timestamp = self.timestamps[user]
        elapsed_time = min((time.time() - last_timestamp) * 1000, BUFFER_SIZE)
        # Generate audio chunk.
        audio_chunk = AudioSegment(pcm_data, sample_width=BYTES_PER_SAMPLE, frame_rate=SAMPLE_RATE, channels=CHANNELS)
        silence = AudioSegment.silent(duration=elapsed_time, frame_rate=SAMPLE_RATE)
        # Add silence if threshold is crossed.
        threshold = int(20 * CHANNELS) # 20ms
        if len(silence) > threshold:
            audio_chunk = silence + audio_chunk
        # Update user buffer.
        self.segments[user] += audio_chunk
        if len(self.segments[user]) > BUFFER_SIZE:
            # Optimize and limit user's buffer size.
            self.segments[user] = self.segments[user][-BUFFER_SIZE:]
        # Update user's last timestamp.
        self.timestamps[user] = time.time()
        ...

    def FinalAudio(self, seconds: int = 5, pitch: float = 1):
        """
        Generate final audio file.
        """
        # Initialize output buffer.
        output_buffer = io.BytesIO()
        # Generate base audio segment for final audio.
        elapsed_time = min((time.time() - self.start_timestamp) * 1000, BUFFER_SIZE)
        combined_audio = AudioSegment.silent(duration=elapsed_time, frame_rate=SAMPLE_RATE)
        # Merge and overlay each user's buffer.
        for user, segment in self.segments.items():
            # Generate remaining final silence chunk.
            user_elapsed_time = min((time.time() - self.timestamps[user]) * 1000, BUFFER_SIZE)
            silence = AudioSegment.silent(duration=user_elapsed_time, frame_rate=SAMPLE_RATE)
            # Generate audio padded with silence.
            padded_audio = segment + silence
            if len(padded_audio) > BUFFER_SIZE:
                # Optimize and limit user's buffer size.
                padded_audio = padded_audio[-BUFFER_SIZE:]
            # Overlay buffers together.
            combined_audio = combined_audio.overlay(padded_audio, position=0)
        # Apply pitch if specified.
        if pitch != 1:
            combined_audio = combined_audio._spawn(combined_audio.raw_data, overrides={
                "frame_rate": int(combined_audio.frame_rate * pitch)
            }).set_frame_rate(SAMPLE_RATE)
        # Trim audio to specified duration in milliseconds.
        duration = seconds * 1000
        if len(combined_audio) > duration:
            combined_audio = combined_audio[-duration:]
        # Export and return final result.
        combined_audio.export(output_buffer, format="wav")
        output_buffer.seek(0)
        return output_buffer
        ...

record_data:dict[str, RecordData] = {}

#endregion

#region Connection

async def Connect(ctx:discord.Interaction, force:bool = False):
    """Connects to the user's current channel and start listening ports."""
    # Initialize variables.
    global record_data
    # Check if already connected to any guild's voice channel.
    voice_client:discord.VoiceClient = ctx.guild.voice_client
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
    # Initialize guild buffer
    record_data[ctx.guild_id] = RecordData()
    # Connect to voice channel and start listeners.
    voice_client = await ctx.user.voice.channel.connect(cls=VoiceRecvClient)
    voice_client.listen(BasicSink(RecorderCallback))
    # Return true if connected successfully.
    return settings.ConditionalMessage(True, "connected")
    ...

async def Disconnect(guild:discord.Guild) -> bool:
    """Disconnects from a guild channel and stops listening ports."""
    # Initialize variables.
    global record_data
    # Check if already connected to any guild's voice channel.
    voice_client:discord.VoiceClient = guild.voice_client
    # Clear guild recorded voice bytes to preserve memory.
    ClearRecordData(guild)
    if not voice_client or not voice_client.is_connected():
        # Return false if already not connected.
        return False
    # Disconnect from voice channel.
    await voice_client.disconnect()
    # Return true if disconnected successfully.
    return True
    ...

#endregion

#region Replay

def RecorderCallback(user: discord.User, data: VoiceData):
    try:
        record_data[data.source.guild.id].AddChunk(user, data.pcm)
    except:
        print("Voice - Error performing recorder callback.")

async def SaveReplay(ctx: discord.Interaction, seconds: int = 5, pitch: float = 1) -> discord.File:
    global record_data
    clean_guild_name = re.sub(r'[^a-zA-Z0-9]', '', ctx.guild.name)
    filename = f"Rec_{clean_guild_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
    audio_buffer = record_data[ctx.guild_id].FinalAudio(seconds, pitch)
    file = discord.File(audio_buffer, filename)
    return file
    ...

async def ClearRecordData(guild:discord.Guild, disconnected:bool = True):
    # Clear guild recorded voice bytes to preserve memory.
    #voice_client:VoiceRecvClient = guild.voice_client
    #voice_client.stop_listening() # Needs to stop listening when changing channels as not to cause errors.
    #voice_client.listen(BasicSink(RecorderCallback)) # Needs to start listening again after finishing reconnecting.
    record_data[guild.id] = None if disconnected else RecordData()
    ...

#endregion

#region Play

async def PlayAudio(ctx:discord.Interaction, url:str):
    global ytdl, ffmpeg_settings
    # Extract audio information and play
    voice_client:discord.VoiceClient = ctx.guild.voice_client
    try:
        info = ytdl.extract_info(url, download=False)
        info = get_audio_info(info)
        audio_url = info["url"]
        media = discord.FFmpegPCMAudio(audio_url, **ffmpeg_settings)
        voice_client.play(media, after=OnFinishPlaying)
        voice_client.source = discord.PCMVolumeTransformer(voice_client.source, 1)
        await ctx.followup.send(f"Playing: {info["title"]}", ephemeral=True)
    except Exception as e:
        await ctx.followup.send(f"Error: {str(e)}", ephemeral=True)
    ...

def OnFinishPlaying(error):
    # Play next media in queue.
    print(f"\nAUDIO - finished playing.\nErrors: {error}\n")
    ...

def get_audio_info(info):
    # Find an audio-only format with a valid URL
    if "entries" in info:  # Handle search results
        info = info["entries"][0]
    return info
    for fmt in info.get("formats", []):
        if fmt.get("acodec") != "none" and fmt.get("vcodec") == "none":
            return fmt.get("url")
    raise Exception("No valid audio format found.")
    ...

#endregion