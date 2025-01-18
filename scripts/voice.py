from scripts import settings
import discord
import yt_dlp
import wave
import os
import io
import numpy
import time
from datetime import datetime
from collections import deque

#region Settings

ffmpeg_settings = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",  # No video
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

#endregion

#region Recording

guild_voices = {}
last_timestamp = {}

async def Connect(ctx:discord.ApplicationContext, force:bool = False):
    """Connects to the user's current channel and start listening ports."""
    # Initialize variables.
    global guild_voices
    global last_timestamp
    BUFFER_SECONDS = 30 # Limit buffer to specified seconds.
    SAMPLE_RATE = 48000 # Standard audio sample rate for PCM.
    CHANNELS = 2 # Quantity of channels (Stereo or Mono).
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
    def callback(user: discord.User, data):
        try:
            # Initialize a circular buffer (deque) for each user.
            current_time = time.time()
            if ctx.guild_id not in last_timestamp:
                last_timestamp[ctx.guild_id] = time.time()
            if user not in guild_voices[ctx.guild_id]:
                guild_voices[ctx.guild_id][user] = deque(maxlen=SAMPLE_RATE * BUFFER_SECONDS * CHANNELS * 2)
                # Start user timestamp.
                start_silence = current_time - last_timestamp[ctx.guild_id]
                if start_silence >= 30:
                    last_timestamp[user] = current_time - 30
                else:
                    last_timestamp[user] = current_time - start_silence
            
            # Calculate the duration since the last callback for this user.
            elapsed_time = current_time - last_timestamp[user]
            last_timestamp[user] = current_time
            
            # Calculate the duration of the received PCM frame.
            pcm_frame_duration = len(data.pcm) / (SAMPLE_RATE * CHANNELS * 2)
            # Calculate the excess time beyond the current PCM frame.
            gap_duration = elapsed_time - pcm_frame_duration
            threshold = 1000 / SAMPLE_RATE
            # threshold = 0.015

            # Append silence only if the excess time exceeds the PCM frame duration.
            if gap_duration > threshold:
                # Calculate the number of silence frames needed.
                silence_frames = int(gap_duration * SAMPLE_RATE * CHANNELS * 2)
                # Ensure silence frames are a multiple of the sample size.
                silence_frames -= silence_frames % (CHANNELS * 2)
                # Append silence frames incrementally.
                silence_chunk_size = SAMPLE_RATE * CHANNELS * 2  # Silence chunk in frames (1 second worth of data)
                silence_chunk_size -= silence_chunk_size % (CHANNELS * 2)
                silence = b'\x00' * silence_chunk_size  # Generate silence (PCM zeros)
                while silence_frames > 0:
                    if silence_frames >= silence_chunk_size:
                        guild_voices[ctx.guild_id][user].extend(silence)
                        silence_frames -= silence_chunk_size
                    else:
                        # Append remaining silence if less than a full chunk.
                        guild_voices[ctx.guild_id][user].extend(b'\x00' * silence_frames)
                        silence_frames = 0
            # Append new PCM data to the user's buffer.
            guild_voices[ctx.guild_id][user].extend(data.pcm)
        except Exception as ex:
            print("VoiceRecv callback failed\n" + ex)
    # Connect to voice channel and start listeners.
    #voice_client = await ctx.user.voice.channel.connect(cls=voice_recv.VoiceRecvClient)
    #voice_client.listen(voice_recv.BasicSink(callback))
    #voice_client.listen(discord.sinks.MP3Sink())
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

async def SaveReplay(ctx:discord.ApplicationContext, seconds:int = 5, pitch:int = 1) -> discord.File:
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

async def PlayAudio(ctx:discord.ApplicationContext, url:str):
    global ytdl
    global ffmpeg_settings
    # Extract audio information and play
    voice_client:voice_recv.VoiceRecvClient = ctx.guild.voice_client
    try:
        info = ytdl.extract_info(url, download=False)
        info = get_audio_info(info)
        media = discord.FFmpegPCMAudio(info["url"], **ffmpeg_settings)
        voice_client.play(media, after=OnFinishPlaying)
        voice_client.source = discord.PCMVolumeTransformer(voice_client.source, 1)
        await ctx.followup.send(f"Playing: {info["title"]}", ephemeral=True)
    except Exception as e:
        await ctx.followup.send(f"Error: {str(e)}", ephemeral=True)

def OnFinishPlaying(error):
    # Play next media in queue.
    print("Audio finished playing")
    print(error)
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