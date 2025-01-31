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
from discord.ext import voice_recv


from discord import app_commands
from discord.ext import commands, tasks, voice_recv

#region Settings

BUFFER_DURATION = 30  # Duration of the buffer in seconds
SAMPLE_RATE = 48000  # Discord uses 48kHz
CHANNELS = 2  # Stereo audio
BYTES_PER_SAMPLE = 2  # 16-bit PCM (2 bytes per sample)
BUFFER_SIZE = BUFFER_DURATION * SAMPLE_RATE * CHANNELS * BYTES_PER_SAMPLE

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
guild_voices = {}
last_timestamp = {}

#endregion

#region Connection

async def Connect(ctx:discord.Interaction, force:bool = False):
    """Connects to the user's current channel and start listening ports."""
    # Initialize variables.
    global guild_voices, last_timestamp
    # Check if already connected to any guild's voice channel.
    voice_client = ctx.guild.voice_client
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
    def recorder_callback(user: discord.User, data):
        try:
            # Initialize circular buffer for each user
            if ctx.guild_id not in last_timestamp:
                last_timestamp[ctx.guild_id] = time.time()
            
            if user not in guild_voices[ctx.guild_id]:
                guild_voices[ctx.guild_id][user] = deque(maxlen=BUFFER_SIZE)
                last_timestamp[user] = time.time()

            current_time = time.time()
            elapsed_time = current_time - last_timestamp[user]
            last_timestamp[user] = current_time

            # Expected frame size based on elapsed time
            expected_frame_count = int(SAMPLE_RATE * elapsed_time * CHANNELS)
            actual_frame_count = len(data.pcm) // BYTES_PER_SAMPLE

            # Add silence only if a significant gap is detected
            silence_frame_count = max(0, expected_frame_count - actual_frame_count)
            threshold_frame_count = int(0.02 * SAMPLE_RATE * CHANNELS)  # Allow 20 ms tolerance

            if silence_frame_count > threshold_frame_count:
                silence_chunk = b'\x00' * silence_frame_count * BYTES_PER_SAMPLE
                guild_voices[ctx.guild_id][user].extend(silence_chunk)

            # Append actual audio data
            guild_voices[ctx.guild_id][user].extend(data.pcm)

        except Exception as ex:
            print(f"Error in voice callback: {ex}")
    # Connect to voice channel and start listeners.
    voice_client = await ctx.user.voice.channel.connect(cls=voice_recv.VoiceRecvClient)
    voice_client.listen(voice_recv.BasicSink(recorder_callback))
    # Return true if connected successfully.
    return settings.ConditionalMessage(True, "connected")

async def Disconnect(guild:discord.Guild) -> bool:
    """Disconnects from a guild channel and stops listening ports."""
    # Initialize variables.
    global guild_voices
    # Check if already connected to any guild's voice channel.
    voice_client:discord.VoiceClient = guild.voice_client
    if not voice_client or not voice_client.is_connected():
        # Return false if already not connected.
        return False
    # Disconnect from voice channel.
    await voice_client.disconnect()
    # Clear guild recorded voice bytes to preserve memory.
    guild_voices[guild.id] = {}
    # Return true if disconnected successfully.
    return True

#endregion

#region Replay

async def SaveReplay(ctx: discord.Interaction, seconds: int = 5, pitch: int = 1) -> discord.File:
    # Initialize variables
    global guild_voices
    PITCH = max(0.5, min(pitch, 1.5))  # Change to specified pitch
    PITCH = (SAMPLE_RATE * PITCH) - SAMPLE_RATE  # Get pitch bitrate

    # Number of samples to keep for the specified duration
    requested_samples = SAMPLE_RATE * CHANNELS * seconds
    max_recorded_samples = max(len(bytes(buffer)) // BYTES_PER_SAMPLE for buffer in guild_voices[ctx.guild_id].values())
    
    # Cap the replay duration to the actual recorded duration
    effective_samples = min(requested_samples, max_recorded_samples)
    
    # Process the last portion of audio for every user
    all_audio = []
    for user, buffer in guild_voices[ctx.guild_id].items():
        pcm_data = numpy.frombuffer(bytes(buffer), dtype=numpy.int16)
        
        # Trim to the last effective sample count
        if len(pcm_data) > effective_samples:
            pcm_data = pcm_data[-effective_samples:]
        
        all_audio.append(pcm_data)
    
    # Mix all users' audio by averaging the PCM values
    if all_audio:
        filename = f"rec_{ctx.guild_id}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.wav"
        
        with io.BytesIO() as audio_buffer:
            # Pad all audio arrays to max length with zeros (silence)
            max_length = max(map(len, all_audio))
            padded_audio = [numpy.pad(audio, (0, max_length - len(audio)), mode='constant') for audio in all_audio]
            
            # Mix all users' audio by averaging the PCM values
            mixed_audio = numpy.mean(padded_audio, axis=0).astype(numpy.int16)
            
            # Write the mixed audio to the memory buffer as a .wav file
            with wave.open(audio_buffer, 'wb') as wav_file:
                wav_file.setnchannels(CHANNELS)
                wav_file.setsampwidth(BYTES_PER_SAMPLE)
                wav_file.setframerate(SAMPLE_RATE + PITCH)
                wav_file.writeframes(mixed_audio.tobytes())
            
            # Return the generated file
            audio_buffer.seek(0)
            file = discord.File(audio_buffer, filename)
            return file

    return None

#endregion

#region Play

async def PlayAudio(ctx:discord.Interaction, url:str):
    global ytdl, ffmpeg_settings
    # Extract audio information and play
    voice_client:voice_recv.VoiceRecvClient = ctx.guild.voice_client
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

#endregion