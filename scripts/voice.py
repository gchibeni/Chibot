import discord.voice_state
from scripts import runtime, settings, speech
import yt_dlp
import asyncio
import base64
import difflib
import logging
import unicodedata
from concurrent.futures import ThreadPoolExecutor
import davey
import io
import json
import os
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import numpy
import discord
from datetime import datetime
from discord.ext.voice_recv import VoiceData, VoiceRecvClient, BasicSink
from discord.ext.voice_recv import opus as voice_recv_opus
from discord.ext.voice_recv.rtp import OPUS_SILENCE
import re
from pydub import AudioSegment
import random

#region Global

BUFFER_SIZE = settings.MAX_RECORDING_TIME * 1000 # Duration of the buffer in milliseconds.
SAMPLE_RATE = 48000  # Discord uses 48kHz.
CHANNELS = 2  # Stereo audio.
BYTES_PER_SAMPLE = 2  # 16-bit PCM (2 bytes per sample).
FRAME_BYTES = CHANNELS * BYTES_PER_SAMPLE  # One stereo sample frame.
TRIM_SLACK_MS = 30_000  # Let frame stores overshoot BUFFER_SIZE by this much so trims stay rare.
DECODER_WARMUP_MS = 1500  # Frames decoded before a replay window to warm the decoder up.
DAVE_MAGIC_MARKER = b'\xfa\xfa'  # Trailer libdave appends to every E2EE frame.

# Discord relays harmless RTCP sender reports every second and voice_recv
# logs each one at INFO; same for unknown-but-harmless gateway payload
# fields. Keep both loggers to warnings only.
logging.getLogger("discord.ext.voice_recv.reader").setLevel(logging.WARNING)
logging.getLogger("discord.ext.voice_recv.gateway").setLevel(logging.WARNING)

class _VoiceRetryFilter(logging.Filter):
    """Discord regularly kills the first voice handshake with close code
    4006 ("session no longer valid"); discord.py retries within a second
    and succeeds. Hide only that expected retry — anything else, including
    a persistent failure, still logs in full."""
    def filter(self, record) -> bool:
        if record.exc_info and "Retrying" in record.getMessage():
            error = record.exc_info[1]
            if isinstance(error, discord.errors.ConnectionClosed) and getattr(error, "code", None) == 4006:
                return False
        return True
logging.getLogger("discord.voice_state").addFilter(_VoiceRetryFilter())

FFMPEG = runtime.ffmpeg_executable()  # System ffmpeg, or the bundled fallback.
AudioSegment.converter = FFMPEG  # pydub shells out for anything but WAV.

ffmpeg_settings = {
    "executable": FFMPEG,
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn -bufsize 8192",  # No video, set buffer size
}

ytdl_settings = {
    "ffmpeg_location": FFMPEG,
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

# Streaming needs no postprocessors: media plays straight from the extracted
# url, nothing is converted or written to disk.
ytdl_stream_settings = {key: value for key, value in ytdl_settings.items() if key != "postprocessors"}

# Downloads prefer m4a: it plays everywhere (including Discord's inline
# player) without a slow transcode, so the extension matches the content.
ytdl_download_settings = dict(ytdl_stream_settings)
ytdl_download_settings["format"] = "bestaudio[ext=m4a]/bestaudio/best"

STREAM_TTL = 3600  # Seconds a resolved stream url is trusted before re-extracting.
PLAYLIST_LIMIT = 100  # Most media accepted from one playlist link.

# Queue-time extraction expands playlists, but flat: one request lists every
# entry's title and url without resolving the videos themselves.
ytdl_queue_settings = dict(ytdl_stream_settings)
ytdl_queue_settings.update({
    "noplaylist": False,
    "extract_flat": "in_playlist",
    "playlist_items": f"1:{PLAYLIST_LIMIT}",
})

class MediaData():
    def __init__(self, url:str, title:str, user_name:str = "", user_avatar:str = None):
        self.url:str = url  # Watch page url or "ytsearch1:..." prompt.
        self.title:str = title
        self.user_name:str = user_name  # Requester display name.
        self.user_avatar:str = user_avatar  # Requester avatar url.
        self.stream_url:str = None  # Direct audio stream url, resolved lazily.
        self.resolved_at:float = 0  # When the stream url was extracted.
        self.duration:float = 0  # Media length in seconds, when known.
        self.ext:str = None  # Audio container of the stream, when known.

    def IsResolved(self) -> bool:
        """Whether the media holds a stream url fresh enough to play."""
        return bool(self.stream_url) and time.monotonic() - self.resolved_at <= STREAM_TTL

class GuildData():
    def __init__(self):
        self.start_timestamp = time.monotonic()
        self.lock = threading.Lock()
        # Raw opus frames per user, as (arrival_ms, rtp timestamp, frame)
        # tuples. Frames stay encoded until a replay is built (the way
        # Craig records): a live decoder shared with the receive pipeline
        # bakes every hiccup permanently into PCM, while stored frames
        # are decoded fresh on demand, so one bad frame can never damage
        # the audio around it. Opus is also ~50x smaller than PCM.
        self.packets:dict[discord.User, list] = {}
        self.queue:list[MediaData] = []  # Upcoming media.
        self.history:list[MediaData] = []  # Already played media, for /prev.
        self.current:MediaData = None  # Media currently playing.
        self.requeued:bool = False  # Skip the history push after a /prev stop.
        self.seeking:bool = False  # A scrub restart, not a media end.
        self.play_started:float = 0  # When the current media started.
        self.play_offset:float = 0  # Seconds skipped by the last scrub.
        self.paused_at:float = None  # When playback was paused, if paused.
        self.paused_total:float = 0  # Seconds spent paused so far.
        ...

    def _now_ms(self) -> float:
        """Milliseconds elapsed since the recording started."""
        return (time.monotonic() - self.start_timestamp) * 1000

    def AddOpusPacket(self, user: discord.User, opus_frame: bytes, rtp_timestamp:int = None):
        """Store one raw opus frame on the user's timeline. Cheap enough
        to run on the voice receive thread: one append, occasional trim."""
        with self.lock:
            now_ms = self._now_ms()
            store = self.packets.setdefault(user, [])
            store.append((now_ms, rtp_timestamp, opus_frame))
            # Trim old frames in batches instead of every packet.
            if store[0][0] < now_ms - BUFFER_SIZE - TRIM_SLACK_MS:
                cutoff = now_ms - BUFFER_SIZE
                keep = 0
                while keep < len(store) and store[keep][0] < cutoff:
                    keep += 1
                del store[:keep]

    def GetReplay(self, seconds: int = 15, pitch: float = 1):
        """Generate a replay file by decoding the stored opus frames.

        Each user gets a fresh decoder and a private PCM track. Positions
        come from the frames' RTP timestamps, which count 48kHz samples:
        all placement math stays in whole samples, so consecutive frames
        land exactly adjacent (float rounding here used to shift writes
        by a sample and crackle). Jitter, reordering and late releases
        land where they were spoken; silence becomes exact zero-filled
        spans; a frame that fails to decode costs 20ms and nothing else."""
        # Snapshot the frames in the window under the lock, mix outside it
        # so recording never stalls. The lead-in frames before the window
        # warm the decoder up without being written.
        with self.lock:
            now_ms = self._now_ms()
            window_ms = int(min(seconds * 1000, BUFFER_SIZE, now_ms))
            window_start_ms = now_ms - window_ms
            snapshot:dict = {}
            for user, store in self.packets.items():
                frames = [entry for entry in store if entry[0] >= window_start_ms - DECODER_WARMUP_MS]
                if frames:
                    snapshot[user] = frames
        # Accumulate in int32 and clip once at the end: pairwise saturating
        # adds distort progressively with each extra speaker.
        window_samples = window_ms * SAMPLE_RATE // 1000
        window_start_samples = int(window_start_ms * SAMPLE_RATE / 1000)
        mix = numpy.zeros(window_samples * CHANNELS, dtype=numpy.int32)
        for user, frames in snapshot.items():
            track = bytearray(window_samples * FRAME_BYTES)
            decoder = discord.opus.Decoder()
            anchor = None  # (rtp timestamp, media sample) pair anchoring the stream.
            for arrival_ms, rtp_timestamp, opus_frame in frames:
                try:
                    pcm = decoder.decode(opus_frame, fec=False)
                except Exception:
                    continue
                chunk_samples = len(pcm) // FRAME_BYTES
                arrival_samples = max(0, int(arrival_ms * SAMPLE_RATE / 1000) - chunk_samples)
                # Anchor the RTP clock to the media timeline, re-anchoring
                # when the stream resets or drifts seconds away.
                position = None
                if isinstance(rtp_timestamp, int):
                    if anchor is not None:
                        position = anchor[1] + (rtp_timestamp - anchor[0])
                    if position is None or abs(position - arrival_samples) > 2 * SAMPLE_RATE:
                        position = arrival_samples
                        anchor = (rtp_timestamp, arrival_samples)
                else:
                    position = arrival_samples
                # Write at the exact sample offset; overlaps overwrite.
                offset = (position - window_start_samples) * FRAME_BYTES
                if offset < 0:
                    # Starts before the window: clip what falls outside.
                    if -offset >= len(pcm):
                        continue
                    pcm = pcm[-offset:]
                    offset = 0
                if offset >= len(track):
                    continue
                end = min(offset + len(pcm), len(track))
                track[offset:end] = pcm[:end - offset]
            mix += numpy.frombuffer(bytes(track), dtype=numpy.int16)
        output = numpy.clip(mix, -32768, 32767).astype(numpy.int16).tobytes()
        combined_audio = AudioSegment(output, sample_width=BYTES_PER_SAMPLE, frame_rate=SAMPLE_RATE, channels=CHANNELS)
        # Apply pitch if specified.
        if pitch != 1:
            if pitch < 1:
                pitch = settings.Remap(pitch, 0, 1, 0.5, 1)
            combined_audio = combined_audio._spawn(combined_audio.raw_data, overrides={
                "frame_rate": int(combined_audio.frame_rate * pitch)
            }).set_frame_rate(SAMPLE_RATE)
        # Export and return final result.
        output_buffer = io.BytesIO()
        combined_audio.export(output_buffer, format="wav")
        output_buffer.seek(0)
        return output_buffer
        ...

class OverlayMixSource(discord.AudioSource):
    """Wraps a playing audio source and mixes one-shot PCM clips (like the
    wake acknowledgment) on top of it. With no base source it plays just
    the clips and ends. Clips can be added from any thread."""
    FRAME = 3840  # One 20ms stereo 48kHz frame.

    def __init__(self, base:discord.AudioSource = None):
        self.base = base
        self._overlays:list = []  # [pcm bytes, read offset] pairs.
        self._lock = threading.Lock()

    def add(self, pcm:bytes):
        if pcm:
            with self._lock:
                self._overlays.append([pcm, 0])

    def read(self) -> bytes:
        frame = self.base.read() if self.base is not None else b""
        with self._lock:
            if not self._overlays:
                return frame
            mixed = numpy.frombuffer(frame.ljust(self.FRAME, b"\x00") if frame else bytes(self.FRAME), dtype=numpy.int16).astype(numpy.int32)
            for overlay in self._overlays:
                chunk = overlay[0][overlay[1]:overlay[1] + self.FRAME]
                if chunk:
                    samples = numpy.frombuffer(chunk, dtype=numpy.int16)
                    mixed[:len(samples)] += samples
                overlay[1] += self.FRAME
            self._overlays = [overlay for overlay in self._overlays if overlay[1] < len(overlay[0])]
        return numpy.clip(mixed, -32768, 32767).astype(numpy.int16).tobytes()

    def cleanup(self):
        if self.base is not None:
            self.base.cleanup()

guild_data:dict[int, GuildData] = {}
_bot:discord.Client = None  # Set on the first voice connection.
_health:dict[int, dict] = {}  # Per-guild recording pipeline health markers.
_watchdog_task:asyncio.Task = None  # Background task that self-heals recording.
_overlay_sources:dict[int, OverlayMixSource] = {}  # Active music mixers per guild.
_ack_only:set = set()  # Guilds where only the wake acknowledgment is playing.
_music_backup:dict[int, tuple] = {}  # Music state kept across disconnects.
_cleared_by:dict[int, tuple] = {}  # Who last cleared the queue, until new media arrives.

# The stock jitter buffer (prefsize=1) holds each packet until a later one
# arrives, which delays the tail of every speech burst — but it also
# reorders out-of-order packets, and skipping it corrupted the opus decode
# ("corrupted stream" bursts, glitchy replays). It stays stock: replay
# chunks are placed by their RTP timestamps, so late tails land at the
# right spot on the timeline anyway.

# When a lost packet blocks the buffer head, the stock implementation
# flushes the buffer and DISCARDS all but the first packet, cutting audio
# after every gap. Release just the head and keep the rest instead.
def _patched_get_next_packet(self, timeout):
    buffer = self._buffer
    packet = buffer.pop(timeout=timeout)
    if packet is None:
        if not buffer._buffer:
            return None
        packet = buffer._pop()
        buffer._last_tx_seq = packet.sequence
        buffer._prefill = 0
        buffer._update_has_item()
        return packet
    elif not packet:
        packet = self._make_fakepacket()
    return packet
voice_recv_opus.PacketDecoder._get_next_packet = _patched_get_next_packet

# Recording pipeline health. "rtp" marks decrypted packets arriving from a
# known member, "pcm" marks decoded audio landing in the replay buffer. When
# packets keep arriving but no audio lands for a while, the pipeline is
# broken (a desynced E2EE session, a dead decode thread...) and the watchdog
# steps in: restart the listener, rebuild the DAVE session, reconnect.
RTP_FRESH_SECONDS = 5  # Packets seen this recently mean someone is transmitting.
PCM_STALL_SECONDS = 10  # Transmission without recorded audio for this long = stalled.
RECOVER_GRACE_SECONDS = 20  # Time given to each recovery step before escalating.

def _HealthFor(guild_id:int) -> dict:
    health = _health.get(guild_id)
    if health is None:
        health = _health[guild_id] = { "rtp":0.0, "pcm":0.0, "dave_fail":0.0, "opus_fail":0.0, "stage":0, "hold_until":0.0 }
    return health

def _ResetHealth(guild_id:int):
    """Clear the activity markers, keeping the recovery backoff."""
    _HealthFor(guild_id).update({ "rtp":0.0, "pcm":0.0, "dave_fail":0.0, "opus_fail":0.0, "stage":0 })

# The sink runs in opus mode (decode=False), so voice_recv's own decoder
# never runs: replay decodes fresh from the stored frames, and the live
# decode for the voice recognizers happens in RecorderCallback with
# per-user decoders whose errors cost one frame, never the pipeline.

def EnableDaveDecryption(voice_client:VoiceRecvClient):
    """Add DAVE E2EE decryption to voice_recv's receive pipeline.

    Discord enforces the DAVE end-to-end encryption protocol on voice
    (mandatory since March 2026, close code 4017 otherwise). discord.py
    2.7+ maintains the DAVE session, but voice_recv only removes the
    transport encryption, leaving the E2EE layer on received frames.
    This wraps the packet decryptor to also decrypt the DAVE layer with
    discord.py's own session before frames reach the opus decoder.
    """
    decryptor = voice_client._reader.decryptor
    transport_decrypt = decryptor.decrypt_rtp
    last_error_log = [0.0]
    health = _HealthFor(voice_client.guild.id)
    def decrypt_rtp(packet) -> bytes:
        data = transport_decrypt(packet)
        # Only packets from mapped members count as incoming voice: video
        # and screenshare ssrcs never map, and must not look like speech
        # to the stall detector.
        user_id = voice_client._get_id_from_ssrc(packet.ssrc)
        if user_id is not None and data != OPUS_SILENCE:
            health["rtp"] = time.monotonic()
        connection = voice_client._connection
        session = connection.dave_session
        # Frames without the DAVE trailer are plain opus, sent while E2EE
        # is off, the MLS group is still forming, or during transitions.
        if session is None or data == OPUS_SILENCE or not data.endswith(DAVE_MAGIC_MARKER):
            return data
        # A frame carrying the E2EE trailer must NEVER reach an opus
        # decoder undecrypted: some such frames fail the decode loudly
        # ("corrupted stream"), the rest decode into garbage noise. Even
        # when the announced protocol version is 0 (mid-transition or
        # desynced), the session may still hold the keys, so always try.
        if user_id is None:
            # No user mapped to this ssrc yet, so the frame cannot be
            # decrypted. Report silence so the packet is skipped quietly.
            return OPUS_SILENCE
        try:
            return session.decrypt(user_id, davey.MediaType.audio, data)
        except Exception as e:
            # A frame with the DAVE trailer that fails to decrypt is
            # corrupt or from a key epoch the bot does not have. Feeding
            # it to the opus decoder produces noise, so drop it instead,
            # logging at most once per 5s.
            health["dave_fail"] = time.monotonic()
            if time.monotonic() - last_error_log[0] > 5:
                last_error_log[0] = time.monotonic()
                print(f"Voice - DAVE decryption failed for user {user_id}.\nErrors: {e}\n")
            return OPUS_SILENCE
    decryptor.decrypt_rtp = decrypt_rtp

#endregion

#region Connection

async def TryConnect(ctx:discord.Interaction, force:bool = False):
    """Try connecting to the user's current channel."""
    # Initialize variables.
    global guild_data
    # Check if user is connected to any voice channel.
    if ctx.user.voice is None:
        # Return false if user is not connected to any channel.
        return settings.ConditionalMessage(False, "not_connected")
    # Check if already connected to any guild's voice channel.
    voice_client:discord.VoiceClient = ctx.guild.voice_client
    connected = voice_client and voice_client.is_connected()
    same_channel = False if not voice_client else voice_client.channel.id == ctx.user.voice.channel.id
    # Return false if already connected and not in the same channel.
    if connected and not same_channel and not force:
        return settings.ConditionalMessage(False, "already_connected")
    # Return false if already connected and in the same channel.
    elif connected and same_channel:
        # Self-heal: restart the recording pipeline if it ever stopped.
        EnsureListening(ctx.guild)
        return settings.ConditionalMessage(True, "already_connected")
    # Start reconnection if forced to.
    elif connected and force:
        await Disconnect(ctx.guild)
    # Connect to voice channel.
    await Connect(ctx.user.voice.channel)
    # Return true if connected successfully.
    return settings.ConditionalMessage(True, "connected")
    ...

async def Connect(channel:discord.VoiceChannel):
    """Connect to channel and start listening."""
    global _bot
    guild = channel.guild
    # Connect first: a failed handshake attempt briefly flaps the voice
    # state, and the disconnect handler would wipe a buffer created early.
    voice_client = await channel.connect(cls=VoiceRecvClient)
    _bot = voice_client.client
    # Initialize guild buffer and start listeners.
    guild_data[guild.id] = GuildData()
    _ResetHealth(guild.id)
    _StartListening(voice_client, guild)
    _EnsureWatchdog()
    # Restore the music state a disconnect stashed away.
    backup = _music_backup.pop(guild.id, None)
    if backup is not None:
        data = guild_data[guild.id]
        data.queue, data.history = backup
        await UpdateMusicMessage(guild)
    ...

def _StartListening(voice_client:VoiceRecvClient, guild:discord.Guild):
    """Start the replay recorder, DAVE decryption and voice triggers.
    The guild is bound here because VoiceData.source can be a bare User
    without one."""
    # decode=False: the sink receives raw opus frames. Replay stores them
    # as-is and decodes fresh on demand; the live decode for the voice
    # recognizers runs in RecorderCallback with per-user decoders.
    voice_client.listen(BasicSink(lambda user, data: RecorderCallback(guild, user, data), decode=False))
    EnableDaveDecryption(voice_client)
    speech.RegisterGuild(voice_client.client, guild)

def EnsureListening(guild:discord.Guild):
    """Restart the recording pipeline if it stopped while connected, so
    replay and voice triggers always run whenever the bot is in a channel."""
    voice_client = guild.voice_client
    if not isinstance(voice_client, VoiceRecvClient) or not voice_client.is_connected():
        return
    if guild_data.get(guild.id) is None:
        guild_data[guild.id] = GuildData()
    if not voice_client.is_listening():
        print(f"Voice - Restarting the recording pipeline for \"{guild.name}\".")
        _StartListening(voice_client, guild)

def _EnsureWatchdog():
    """Start the pipeline watchdog task once, on the bot's event loop."""
    global _watchdog_task
    if _bot is None:
        return
    if _watchdog_task is None or _watchdog_task.done():
        _watchdog_task = _bot.loop.create_task(_WatchdogLoop())

async def _WatchdogLoop():
    """Detect and repair a broken recording pipeline while connected.

    voice_recv has several ways to go silently deaf: its router thread dies
    on any internal error and stops listening, and a desynced DAVE (E2EE)
    session fails to decrypt every frame until the group is rejoined. Both
    look the same from outside: packets keep arriving, no audio is ever
    recorded. Check every few seconds and recover in stages."""
    while True:
        await asyncio.sleep(5)
        for guild_id in list(guild_data):
            try:
                await _CheckPipelineHealth(guild_id)
            except Exception as e:
                print(f"Voice - Watchdog error for guild {guild_id}.\nErrors: {e}\n")

def _DaveStatus(voice_client:VoiceRecvClient) -> str:
    """Best-effort DAVE session details for stall diagnostics."""
    try:
        connection = voice_client._connection
        session = connection.dave_session
        if session is None:
            return "no DAVE session"
        details = f"DAVE v{connection.dave_protocol_version}, ready={session.ready}"
        try:
            details += f", stats={session.get_decryption_stats()}"
        except Exception:
            pass
        return details
    except Exception:
        return "DAVE state unavailable"

async def _CheckPipelineHealth(guild_id:int):
    data = guild_data.get(guild_id)
    guild = _bot.get_guild(guild_id) if _bot else None
    if data is None or guild is None:
        return
    voice_client = guild.voice_client
    if not isinstance(voice_client, VoiceRecvClient) or not voice_client.is_connected():
        return
    # A dead reader or router thread: restart the listener in place.
    EnsureListening(guild)
    health = _HealthFor(guild_id)
    now = time.monotonic()
    if now < health["hold_until"]:
        return
    receiving = now - health["rtp"] < RTP_FRESH_SECONDS
    # Before any audio was recorded, the connection time is the baseline.
    last_pcm = max(health["pcm"], data.start_timestamp)
    stalled = now - last_pcm > PCM_STALL_SECONDS
    if not stalled:
        health["stage"] = 0  # Audio is flowing, the pipeline is healthy.
        return
    if not receiving:
        return  # Nobody is transmitting; nothing to judge.
    print(f"Voice - Recording stalled in \"{guild.name}\": packets arriving but no audio recorded "
          f"for {now - last_pcm:.0f}s ({_DaveStatus(voice_client)}).")
    if health["stage"] == 0:
        # Gentlest fix first: rebuild the E2EE session. The server answers
        # a fresh key package by re-adding the bot to the MLS group, which
        # resolves any key desync without dropping the connection.
        health["stage"] = 1
        health["hold_until"] = now + RECOVER_GRACE_SECONDS
        connection = voice_client._connection
        if connection.dave_protocol_version > 0:
            print(f"Voice - Rebuilding the DAVE session for \"{guild.name}\".")
            try:
                await connection.reinit_dave_session()
            except Exception as e:
                print(f"Voice - Could not rebuild the DAVE session.\nErrors: {e}\n")
        return
    # Last resort: a full reconnect rebuilds every layer. The music queue
    # survives through the disconnect stash; playback resumes if it was
    # active. The (already broken) replay buffer starts over.
    print(f"Voice - Reconnecting voice in \"{guild.name}\" to restore recording.")
    channel = voice_client.channel
    was_playing = IsPlaying(guild)
    health["hold_until"] = now + 60  # Backoff against reconnect loops.
    health["stage"] = 0
    try:
        await Disconnect(guild)
        await Connect(channel)
    except Exception as e:
        print(f"Voice - Recovery reconnect failed.\nErrors: {e}\n")
        return
    if was_playing and guild_data.get(guild_id) is not None and guild_data[guild_id].queue:
        await PlayNext(guild)

async def Disconnect(guild:discord.Guild) -> bool:
    """Disconnects from a guild channel and stops listening."""
    # Initialize variables.
    global guild_data
    # Check if already connected to any guild's voice channel.
    voice_client:VoiceRecvClient = guild.voice_client
    # Clear guild recorded voice bytes to preserve memory.
    ClearRecordData(guild)
    if not voice_client or not voice_client.is_connected():
        # Return false if already not connected.
        return False
    # Disconnect from voice channel.
    voice_client.stop_listening()
    await voice_client.disconnect()
    # Return true if disconnected successfully.
    return True
    ...

#endregion

#region Replay

_speech_decoders:dict[tuple, discord.opus.Decoder] = {}  # Live decoders, per (guild, user).
_recorder_error_log = [0.0]

def RecorderCallback(guild: discord.Guild, user: discord.User, data: VoiceData):
    """Store incoming opus frames for replay and decode a live copy for
    the voice trigger recognizers."""
    try:
        buffer = guild_data.get(guild.id)
        if buffer is None or user is None or data is None:
            return
        packet = getattr(data, "packet", None)
        # Only real voice packets are recorded: the silence and fake
        # packets voice_recv synthesizes carry timestamps off the
        # speaker's RTP clock, corrupting the anchor, and the replay
        # timeline is already zero-filled where nothing was spoken.
        is_real = bool(packet) and not (hasattr(packet, "is_silence") and packet.is_silence())
        opus_frame = data.opus
        if not is_real or not opus_frame:
            return
        now = time.monotonic()
        # Final firewall: an E2EE frame that reached this point undecrypted
        # is not audio. Recording it would put garbage noise in the replay.
        if opus_frame.endswith(DAVE_MAGIC_MARKER):
            _HealthFor(guild.id)["opus_fail"] = now
            if now - _recorder_error_log[0] > 5:
                _recorder_error_log[0] = now
                print(f"Voice - Dropped undecrypted E2EE frame(s) from user {user.id}.")
            return
        rtp_timestamp = getattr(packet, "timestamp", None)
        buffer.AddOpusPacket(user, opus_frame, rtp_timestamp if isinstance(rtp_timestamp, int) else None)
        _HealthFor(guild.id)["pcm"] = now
        # Live decode for the recognizers only; a failed frame costs this
        # 20ms of speech audio and nothing else.
        key = (guild.id, user.id)
        decoder = _speech_decoders.get(key)
        if decoder is None:
            decoder = _speech_decoders[key] = discord.opus.Decoder()
        try:
            pcm = decoder.decode(opus_frame, fec=False)
        except Exception as e:
            _HealthFor(guild.id)["opus_fail"] = now
            if now - _recorder_error_log[0] > 5:
                _recorder_error_log[0] = now
                print(f"Voice - Dropped undecodable audio frame(s) from user {user.id} "
                      f"(len={len(opus_frame)}, head={opus_frame[:4].hex()}).\nErrors: {e}\n")
            return
        speech.FeedAudio(guild, user, pcm)
    except Exception as e:
        print(f"Voice - Error performing recorder callback.\nErrors: {e}\n")

def SaveReplay(ctx: discord.Interaction, seconds: int = 15, pitch: float = 1) -> discord.File:
    """..."""
    return SaveReplayForGuild(ctx.guild, seconds, pitch)
    ...

def SaveReplayForGuild(guild: discord.Guild, seconds: int = 15, pitch: float = 1) -> discord.File:
    """Generate a replay file for a guild, or None when not recording."""
    global guild_data
    data = guild_data.get(guild.id)
    if data is None:
        return None
    pitch = max(pitch, 0.1)
    clean_guild_name = re.sub(r'[^a-zA-Z0-9]', '', guild.name)
    filename = f"Rec_{clean_guild_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
    audio_buffer = data.GetReplay(seconds, pitch)
    file = discord.File(audio_buffer, filename)
    return file
    ...

def ClearRecordData(guild:discord.Guild, disconnected:bool = True):
    """..."""
    # Every disconnect stashes the music state so a rejoin keeps the queue,
    # with the interrupted media back at the front. Only /clear drops it.
    data = guild_data.get(guild.id)
    if disconnected and data is not None and (data.queue or data.current or data.history):
        queue = list(data.queue)
        if data.current is not None:
            queue.insert(0, data.current)
        _music_backup[guild.id] = (queue, list(data.history))
    # Clear guild recorded voice bytes to preserve memory.
    guild_data[guild.id] = None if disconnected else GuildData()
    for key in [k for k in _speech_decoders if k[0] == guild.id]:
        _speech_decoders.pop(key, None)
    if disconnected:
        speech.UnregisterGuild(guild)
    ...

#endregion

#region Music

QUEUE_DISPLAY_LIMIT = 20  # Queue entries listed on the music message.
HISTORY_LIMIT = 50  # Played media kept around for /prev.
# Playlist, album and track links, including regional "intl-xx" urls.
SPOTIFY_PATTERN = re.compile(r"open\.spotify\.com/(?:intl-[a-z\-]+/)?(playlist|album|track)/([A-Za-z0-9]+)")

class PrivateMediaError(Exception):
    """The linked playlist or media is private or inaccessible."""

def _ParseSource(prompt:str):
    """Split a trailing source hint off a prompt: "... on youtube" forces
    YouTube, "... on spotify" forces Spotify, None means Spotify first."""
    lowered = prompt.lower().strip()
    for suffix, source in ((" on youtube", "youtube"), (" no youtube", "youtube"), (" from youtube", "youtube"),
                           (" on spotify", "spotify"), (" no spotify", "spotify"), (" from spotify", "spotify")):
        if lowered.endswith(suffix):
            return prompt.strip()[:-len(suffix)].strip(), source
    return prompt.strip(), None

def _SimplifyName(text:str) -> str:
    """Lowercase and strip accents for fuzzy name comparison."""
    text = unicodedata.normalize("NFKD", text.lower())
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())

def IsPlaying(guild:discord.Guild) -> bool:
    """Whether the guild's voice client has active (or paused) media. A
    lone wake acknowledgment clip does not count as media."""
    if guild.id in _ack_only:
        return False
    voice_client:discord.VoiceClient = guild.voice_client
    return bool(voice_client and voice_client.is_connected() and (voice_client.is_playing() or voice_client.is_paused()))

async def QueueMedia(guild:discord.Guild, prompt:str, user:discord.Member, next:bool = False, push:bool = False):
    """Resolve a prompt (search, url or Spotify playlist link) and add it to
    the guild's queue, starting playback when idle. Returns (count, error).

    next inserts at the front of the queue instead of the back; push also
    skips whatever is playing so the new media starts immediately."""
    data = guild_data.get(guild.id)
    if data is None:
        return 0, "not_connected"
    prompt, source = _ParseSource(prompt)
    token = settings.GetInfo(guild.id, "setup/spotify_token")
    medias = []
    if SPOTIFY_PATTERN.search(prompt):
        # Spotify playlist, album and track links resolve to "name - artist"
        # searches through the Spotify API or its public embed page, so a
        # configured app token is optional.
        try:
            tracks = await asyncio.to_thread(_SpotifyTracks, token, prompt)
        except PrivateMediaError:
            return 0, "lbl_music_private"
        except Exception as e:
            print(f"Music - Could not fetch from Spotify.\nErrors: {e}\n")
            return 0, "lbl_spotify_invalid" if token else "lbl_music_not_found"
        medias = [MediaData(f"ytsearch1:{track}", track, user.display_name, user.display_avatar.url) for track in tracks]
    else:
        is_url = prompt.lower().startswith(("http://", "https://", "www."))
        # Text prompts search Spotify first when an app token is set up:
        # artist names queue their top tracks, song names queue one track.
        # A trailing "on youtube" skips this, "on spotify" requires it.
        if not is_url and source != "youtube":
            if token:
                market = "BR" if settings.GetLanguage(guild.id) == "pt" else "US"
                try:
                    tracks = await asyncio.to_thread(_SpotifySearchTracks, token, prompt, market)
                except Exception as e:
                    print(f"Music - Spotify search failed for \"{prompt}\".\nErrors: {e}\n")
                    tracks = []
                medias = [MediaData(f"ytsearch1:{track}", track, user.display_name, user.display_avatar.url) for track in tracks]
                if not medias and source == "spotify":
                    return 0, "lbl_music_not_found"
            elif source == "spotify":
                return 0, "lbl_spotify_disabled"
        if not medias:
            # A single flat extraction resolves searches, direct links and
            # whole playlists; streams are resolved just in time after.
            try:
                entries = await asyncio.to_thread(_ExtractQueueEntries, prompt)
            except Exception as e:
                print(f"Music - Could not find media \"{prompt}\".\nErrors: {e}\n")
                # Surface private playlists and videos, not a generic error.
                if "private" in str(e).lower():
                    return 0, "lbl_music_private"
                return 0, "lbl_music_not_found"
            for entry in entries:
                media = MediaData(entry["url"], entry["title"], user.display_name, user.display_avatar.url)
                if entry.get("stream_url"):
                    media.stream_url = entry["stream_url"]
                    media.resolved_at = time.monotonic()
                medias.append(media)
    if not medias:
        return 0, "lbl_music_not_found"
    if next or push:
        data.queue[0:0] = medias
    else:
        data.queue.extend(medias)
    # New media supersedes the "cleared by" footer state.
    _cleared_by.pop(guild.id, None)
    # Create the music message in the configured music channel on the first
    # play, when none exists yet.
    if GetMusicMessageInfo(guild.id) is None:
        music_channel_id = settings.GetInfo(guild.id, "setup/music_channel")
        music_channel = guild.get_channel(int(music_channel_id)) if music_channel_id else None
        if music_channel is not None:
            await CreateMusicMessage(guild, music_channel)
    # A push skips straight into the new media; otherwise start playing
    # when idle or refresh the message and prefetch the upcoming media.
    if push or not IsPlaying(guild):
        await PlayNext(guild)
    else:
        await UpdateMusicMessage(guild)
        _PrefetchNext(guild)
    return len(medias), None

async def PlayNext(guild:discord.Guild) -> bool:
    """Advance the queue. Stops active media (the after-play callback pops
    the next one) or pops and plays directly when idle."""
    data = guild_data.get(guild.id)
    voice_client:discord.VoiceClient = guild.voice_client
    if data is None or not voice_client or not voice_client.is_connected():
        return False
    if voice_client.is_playing() or voice_client.is_paused():
        if guild.id in _ack_only:
            # Only the wake acknowledgment is sounding: cut it and fall
            # through to start the actual media.
            voice_client.stop()
            _ack_only.discard(guild.id)
        else:
            voice_client.stop()
            return True
    while data.queue:
        media = data.queue.pop(0)
        # Reuse the prefetched stream url, re-extracting only when it went
        # stale. Media that fails to resolve is skipped.
        try:
            if not media.IsResolved():
                await asyncio.to_thread(_ResolveMedia, media)
            source = OverlayMixSource(discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(media.stream_url, **ffmpeg_settings), 1))
        except Exception as e:
            print(f"Music - Could not play \"{media.title}\".\nErrors: {e}\n")
            continue
        data.current = media
        _overlay_sources[guild.id] = source
        voice_client.play(source, after=_AfterPlay(guild))
        # Reset the playback position tracking.
        data.play_started = time.monotonic()
        data.play_offset = 0
        data.paused_at = None
        data.paused_total = 0
        # Resolve the upcoming media in the background so it starts instantly.
        _PrefetchNext(guild)
        await UpdateMusicMessage(guild)
        return True
    data.current = None
    await UpdateMusicMessage(guild)
    return False

async def PlayPrev(guild:discord.Guild) -> bool:
    """Requeue the current media and play the previous one."""
    data = guild_data.get(guild.id)
    voice_client:discord.VoiceClient = guild.voice_client
    if data is None or not data.history or not voice_client or not voice_client.is_connected():
        return False
    if data.current is not None:
        data.queue.insert(0, data.current)
    data.queue.insert(0, data.history.pop())
    if voice_client.is_playing() or voice_client.is_paused():
        # The current media was requeued by hand, keep it out of history.
        data.requeued = True
        voice_client.stop()
    else:
        await PlayNext(guild)
    return True

DUCK_VOLUME = 0.25  # Music volume while a voice command is being captured.
ACK_SOUND = "./assets/response.mp3"  # Played when the wake word is heard.

def DuckMusic(guild_id:int, ducked:bool):
    """Lower the music while someone talks to the bot, so speech stays
    audible to the recognizers. Safe to call from any thread."""
    if _bot is None:
        return
    guild = _bot.get_guild(guild_id)
    voice_client:discord.VoiceClient = guild.voice_client if guild else None
    source = getattr(voice_client, "source", None)
    if isinstance(source, OverlayMixSource):
        source = source.base
    if isinstance(source, discord.PCMVolumeTransformer):
        source.volume = DUCK_VOLUME if ducked else 1.0

_ack_pcm_cache:bytes = None

def _AckPcm() -> bytes:
    """Blocking: decode the acknowledgment sound once to raw 48kHz PCM."""
    global _ack_pcm_cache
    if _ack_pcm_cache is None:
        try:
            result = subprocess.run(
                [FFMPEG, "-v", "error", "-i", ACK_SOUND, "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS), "pipe:1"],
                capture_output=True, check=True)
            _ack_pcm_cache = result.stdout
        except Exception as e:
            print(f"Voice - Could not load the acknowledgment sound.\nErrors: {e}\n")
            _ack_pcm_cache = b""
    return _ack_pcm_cache

def _PitchedAckPcm() -> bytes:
    """The acknowledgment sound with a small random pitch variation."""
    base = _AckPcm()
    if not base:
        return b""
    pitch = random.uniform(0.94, 1.08)
    frames = numpy.frombuffer(base, dtype=numpy.int16).reshape(-1, CHANNELS)
    length = max(1, int(len(frames) / pitch))
    positions = numpy.linspace(0, len(frames) - 1, length)
    resampled = numpy.stack(
        [numpy.interp(positions, numpy.arange(len(frames)), frames[:, channel]) for channel in range(CHANNELS)],
        axis=1)
    return resampled.astype(numpy.int16).tobytes()

def PlayAcknowledge(guild_id:int):
    """Play the wake acknowledgment: mixed over the music when playing,
    on its own when idle. Safe to call from any thread."""
    if _bot is None:
        return
    guild = _bot.get_guild(guild_id)
    voice_client:discord.VoiceClient = guild.voice_client if guild else None
    if not voice_client or not voice_client.is_connected():
        return
    pcm = _PitchedAckPcm()
    if not pcm:
        return
    if voice_client.is_playing():
        source = voice_client.source
        if isinstance(source, OverlayMixSource):
            source.add(pcm)
        return
    if voice_client.is_paused():
        return
    # Idle: play the clip standalone, flagged so PlayNext knows it is not
    # media and IsPlaying does not mistake it for a track.
    ding = OverlayMixSource(None)
    ding.add(pcm)
    _ack_only.add(guild_id)
    def finished(error):
        _ack_only.discard(guild_id)
    try:
        voice_client.play(ding, after=finished)
    except Exception:
        _ack_only.discard(guild_id)

def PauseMusic(guild:discord.Guild) -> bool:
    voice_client:discord.VoiceClient = guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        # Freeze the playback position.
        data = guild_data.get(guild.id)
        if data is not None:
            data.paused_at = time.monotonic()
        return True
    return False

def ResumeMusic(guild:discord.Guild) -> bool:
    voice_client:discord.VoiceClient = guild.voice_client
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        # Paused time does not count towards the playback position.
        data = guild_data.get(guild.id)
        if data is not None and data.paused_at is not None:
            data.paused_total += time.monotonic() - data.paused_at
            data.paused_at = None
        return True
    return False

async def ClearQueue(guild:discord.Guild, user:discord.Member = None):
    """Empty the pending queue, including one stashed by a disconnect.
    This is the only place the queue is ever dropped. The clearing user is
    shown on the music message footer until new media arrives."""
    _music_backup.pop(guild.id, None)
    data = guild_data.get(guild.id)
    if data is not None:
        data.queue.clear()
    if user is not None:
        _cleared_by[guild.id] = (user.display_name, user.display_avatar.url)
    await UpdateMusicMessage(guild)

async def ShuffleQueue(guild:discord.Guild) -> bool:
    """Shuffle the pending queue once."""
    data = guild_data.get(guild.id)
    if data is None or not data.queue:
        return False
    random.shuffle(data.queue)
    await UpdateMusicMessage(guild)
    return True

async def MoveMedia(guild:discord.Guild, source:int, destination:int) -> bool:
    """Move a queued media between 1-based queue positions, matching the
    numbering shown on the music message."""
    data = guild_data.get(guild.id)
    if data is None or not data.queue:
        return False
    total = len(data.queue)
    if not 1 <= source <= total:
        return False
    destination = min(max(destination, 1), total)
    media = data.queue.pop(source - 1)
    data.queue.insert(destination - 1, media)
    await UpdateMusicMessage(guild)
    return True

def GetLoop(guild_id:int) -> bool:
    """Whether playlist loop is on. Persisted per guild, so the preference
    applies to every future queue until toggled again."""
    return bool(settings.GetInfo(guild_id, "music_loop"))

async def ToggleLoop(guild:discord.Guild) -> bool:
    """Toggle playlist loop: finished media returns to the queue. Works
    connected or not, the state is stored in the guild settings."""
    looping = not GetLoop(guild.id)
    settings.SetInfo(guild.id, "music_loop", True if looping else None)
    await UpdateMusicMessage(guild)
    return looping

def PlaybackPosition(guild:discord.Guild) -> float:
    """Seconds into the current media, accounting for scrubs and pauses."""
    data = guild_data.get(guild.id)
    if data is None or data.current is None:
        return 0.0
    end = data.paused_at if data.paused_at is not None else time.monotonic()
    return max(0.0, data.play_offset + (end - data.play_started) - data.paused_total)

def ParseTimestamp(text:str) -> float:
    """Parse "90", "1:30" or "1:02:30" into seconds, None when invalid."""
    try:
        parts = [float(part) for part in text.strip().split(":")]
    except ValueError:
        return None
    if not parts or len(parts) > 3:
        return None
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds

async def Scrub(guild:discord.Guild, position:float) -> bool:
    """Jump to a position (in seconds) in the current media by restarting
    its stream with an ffmpeg seek. Scrubbing resumes paused playback."""
    data = guild_data.get(guild.id)
    voice_client:discord.VoiceClient = guild.voice_client
    if data is None or data.current is None or not voice_client or not voice_client.is_connected():
        return False
    media = data.current
    if not media.IsResolved():
        await asyncio.to_thread(_ResolveMedia, media)
    position = max(0.0, position)
    if media.duration:
        position = min(position, max(media.duration - 1, 0))
    # Restart the stream at the target position.
    seek_settings = dict(ffmpeg_settings)
    seek_settings["before_options"] = f"-ss {position:.1f} {seek_settings.get('before_options', '')}".strip()
    source = OverlayMixSource(discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(media.stream_url, **seek_settings), 1))
    _overlay_sources[guild.id] = source
    if voice_client.is_playing() or voice_client.is_paused():
        # Flag the stop as a seek so the after-play callback does not
        # advance the queue.
        data.seeking = True
        voice_client.stop()
    voice_client.play(source, after=_AfterPlay(guild))
    # Track the new playback position.
    data.play_started = time.monotonic()
    data.play_offset = position
    data.paused_at = None
    data.paused_total = 0
    await UpdateMusicMessage(guild)
    return True

async def ScrubRelative(guild:discord.Guild, delta:float) -> bool:
    """Jump forwards or backwards relative to the playback position."""
    data = guild_data.get(guild.id)
    if data is None or data.current is None:
        return False
    return await Scrub(guild, PlaybackPosition(guild) + delta)

async def StopMusic(guild:discord.Guild) -> bool:
    """Stop playback and leave the voice channel. The queue survives: the
    disconnect stashes it for the next join, only /clear empties it."""
    disconnected = await Disconnect(guild)
    await UpdateMusicMessage(guild)
    return disconnected

def _ExtractInfo(prompt:str) -> dict:
    """Blocking media extraction. A fresh yt-dlp instance per call keeps
    concurrent extractions (prefetch + commands) safe."""
    with yt_dlp.YoutubeDL(ytdl_stream_settings) as extractor:
        return get_audio_info(extractor.extract_info(prompt, download=False))

def _ExtractQueueEntries(prompt:str) -> list[dict]:
    """Blocking: resolve a prompt into {url, title, stream_url} entries.

    Searches and playlists come back flat (title and watch url only, one
    request for the whole list); a direct single link is fully extracted,
    so its stream url is already known."""
    with yt_dlp.YoutubeDL(ytdl_queue_settings) as extractor:
        info = extractor.extract_info(prompt, download=False)
    if info.get("entries") is None:
        # Single media, fully processed.
        return [{
            "url": info.get("webpage_url") or prompt,
            "title": info.get("title") or prompt,
            "stream_url": info.get("url"),
        }]
    entries = []
    for entry in info["entries"]:
        if not entry:
            continue
        url = entry.get("webpage_url") or entry.get("url") or entry.get("id") or ""
        if not url:
            continue
        # Flat entries may carry a bare video id instead of a url.
        if not url.startswith("http"):
            url = f"https://www.youtube.com/watch?v={url}"
        entries.append({ "url":url, "title":entry.get("title") or url, "stream_url":None })
    return entries

def _ResolveMedia(media:MediaData) -> MediaData:
    """Blocking: fill a media's stream url, watch url and title."""
    info = _ExtractInfo(media.url)
    # Keep curated titles (e.g. Spotify "name - artist"), only placeholder
    # titles that still equal the prompt get replaced.
    if media.title == media.url:
        media.title = info.get("title") or media.title
    media.url = info.get("webpage_url") or media.url
    media.stream_url = info["url"]
    media.resolved_at = time.monotonic()
    media.duration = info.get("duration") or media.duration
    media.ext = info.get("ext") or media.ext
    return media

def _PrefetchNext(guild:discord.Guild):
    """Resolve the next queued media in the background, so the switch to it
    plays without an extraction pause."""
    data = guild_data.get(guild.id)
    if data is None or not data.queue:
        return
    media = data.queue[0]
    if media.IsResolved():
        return
    async def prefetch():
        try:
            await asyncio.to_thread(_ResolveMedia, media)
        except Exception as e:
            print(f"Music - Could not prefetch \"{media.title}\".\nErrors: {e}\n")
    asyncio.create_task(prefetch())

def _AfterPlay(guild:discord.Guild):
    """After-play callback: runs on the player thread, so the queue advance
    is scheduled back onto the bot loop."""
    def callback(error):
        if error:
            print(f"Music - Playback error.\nErrors: {error}\n")
        if _bot is not None:
            asyncio.run_coroutine_threadsafe(_OnMediaEnd(guild), _bot.loop)
    return callback

async def _OnMediaEnd(guild:discord.Guild):
    data = guild_data.get(guild.id)
    if data is None:
        return
    # A scrub restarts the same media, nothing ended.
    if data.seeking:
        data.seeking = False
        return
    if data.current is not None and not data.requeued:
        data.history.append(data.current)
        del data.history[:-HISTORY_LIMIT]
        # Playlist loop: the finished media returns to the queue.
        if GetLoop(guild.id):
            data.queue.append(data.current)
    data.requeued = False
    data.current = None
    await PlayNext(guild)

def _SpotifyTracks(token:str, url:str) -> list[str]:
    """Fetch "name - artist" entries from a Spotify playlist, album or track
    link. The official API is tried first when an app token is configured,
    falling back to the public embed page: development-mode Spotify apps get
    403 on playlist tracks since the 2024/2025 API restrictions, and the
    embed page needs no authentication at all. Playlists come back shuffled."""
    kind, item_id = SPOTIFY_PATTERN.search(url).groups()
    tracks = []
    if token:
        try:
            tracks = _SpotifyApiTracks(token, kind, item_id)
        except Exception as e:
            print(f"Music - Spotify API refused ({e}), falling back to the embed page.\n")
    if not tracks:
        tracks = _SpotifyEmbedTracks(kind, item_id)
    # Playlists keep the old shuffled behavior, albums keep their order.
    if kind == "playlist":
        random.shuffle(tracks)
    return tracks

def _SpotifyAccessToken(token:str) -> str:
    """Blocking: exchange the app credentials for an access token. The
    token is "client_id:client_secret"."""
    credentials = re.split(r"[:/\s]+", token.strip(), maxsplit=1)
    if len(credentials) != 2:
        raise ValueError("Invalid Spotify token format, expected \"client_id:client_secret\".")
    auth = base64.b64encode(f"{credentials[0]}:{credentials[1]}".encode()).decode()
    request = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
        headers={"Authorization": f"Basic {auth}"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode())["access_token"]

def _SpotifyApi(access_token:str, endpoint:str) -> dict:
    request = urllib.request.Request(
        f"https://api.spotify.com/v1/{endpoint}",
        headers={"Authorization": f"Bearer {access_token}"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode())

def _TrackNames(track_objects:list) -> list[str]:
    tracks = []
    for track in track_objects:
        name = track.get("name")
        artists = track.get("artists") or []
        if name:
            artist = artists[0].get("name", "") if artists else ""
            tracks.append(f"{name} - {artist}".strip(" -"))
    return tracks

def _SpotifyApiTracks(token:str, kind:str, item_id:str) -> list[str]:
    """Blocking: fetch a linked item's tracks through the Spotify Web API."""
    access_token = _SpotifyAccessToken(token)
    # Collect the track objects for the linked item.
    if kind == "playlist":
        items = _SpotifyApi(access_token, f"playlists/{item_id}/tracks?limit={PLAYLIST_LIMIT}").get("items", [])
        track_objects = [item.get("track") or {} for item in items]
    elif kind == "album":
        track_objects = _SpotifyApi(access_token, f"albums/{item_id}/tracks?limit=50").get("items", [])
    else:
        track_objects = [_SpotifyApi(access_token, f"tracks/{item_id}")]
    return _TrackNames(track_objects)

def _SpotifySearchTracks(token:str, query:str, market:str = "US") -> list[str]:
    """Blocking: search Spotify for a text prompt. A close artist-name
    match queues the artist's top tracks, anything else the best track."""
    access_token = _SpotifyAccessToken(token)
    encoded = urllib.parse.urlencode({ "q":query, "type":"artist,track", "limit":5, "market":market })
    results = _SpotifyApi(access_token, f"search?{encoded}")
    # An artist whose name closely matches the prompt gets top billing.
    simplified = _SimplifyName(query)
    for artist in (results.get("artists") or {}).get("items", [])[:3]:
        name = artist.get("name", "")
        ratio = difflib.SequenceMatcher(None, _SimplifyName(name), simplified).ratio()
        if ratio >= 0.8:
            tracks = []
            try:
                top = _SpotifyApi(access_token, f"artists/{artist['id']}/top-tracks?market={market}")
                tracks = _TrackNames(top.get("tracks", []))
            except urllib.error.HTTPError:
                # Development-mode apps get 403 on top-tracks: an artist
                # filtered track search comes close enough.
                pass
            if not tracks:
                encoded = urllib.parse.urlencode({ "q":f"artist:\"{name}\"", "type":"track", "limit":10, "market":market })
                tracks = _TrackNames(_SpotifyApi(access_token, f"search?{encoded}").get("tracks", {}).get("items", []))
            if tracks:
                return tracks
    # Otherwise the best matching track only.
    return _TrackNames((results.get("tracks") or {}).get("items", [])[:1])

def _SpotifyEmbedTracks(kind:str, item_id:str) -> list[str]:
    """Blocking: fetch tracks from the public Spotify embed page, which
    serves playlist content without authentication. Private content raises
    PrivateMediaError: the embed page only exposes public items."""
    request = urllib.request.Request(
        f"https://open.spotify.com/embed/{kind}/{item_id}",
        headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            html = response.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise PrivateMediaError(f"Spotify {kind} {item_id} is private or gone.")
        raise
    match = re.search(r"<script id=\"__NEXT_DATA__\" type=\"application/json\">(.*?)</script>", html, re.DOTALL)
    if match is None:
        raise ValueError("Could not read the Spotify embed page.")
    # Private or deleted items render an embed page without entity data.
    page_props = json.loads(match.group(1)).get("props", {}).get("pageProps") or {}
    entity = ((page_props.get("state") or {}).get("data") or {}).get("entity") or {}
    if not entity:
        raise PrivateMediaError(f"Spotify {kind} {item_id} is private or gone.")
    # Playlists and albums carry a track list, a track link is the entity.
    entries = entity.get("trackList") or [entity]
    tracks = []
    for entry in entries[:PLAYLIST_LIMIT]:
        title = entry.get("title") or entry.get("name")
        artist = entry.get("subtitle") or ""
        if title:
            tracks.append(f"{title} - {artist}".strip(" -"))
    if not tracks:
        # An embed page with no track content means a private item.
        raise PrivateMediaError(f"Spotify {kind} {item_id} has no public tracks.")
    return tracks

#endregion

#region Music message

def GetMusicMessageInfo(guild_id:int):
    """The saved music message as (channel_id, message_id), or None."""
    info = settings.GetInfo(guild_id, "music_message")
    if not info:
        return None
    try:
        channel_id, message_id = str(info).split("/")
        return int(channel_id), int(message_id)
    except ValueError:
        return None

def BuildMusicEmbed(guild:discord.Guild) -> discord.Embed:
    """The playlist embed: queue listed top-down into the playing media.
    While idle or disconnected the pending (or stashed) queue still shows,
    so the playlist never looks cleared when it is not."""
    data = guild_data.get(guild.id)
    current = data.current if data is not None else None
    queue = list(data.queue) if data is not None else []
    if data is None:
        backup = _music_backup.get(guild.id)
        if backup is not None:
            queue = list(backup[0])
    total = len(queue)
    lines = ""
    # Collapse overlong queues to the last entry plus a marker, like before.
    if total > QUEUE_DISPLAY_LIMIT:
        lines += f"```#{total:02d} : {queue[-1].title}```"
        lines += f"```#.. : {settings.Localize('lbl_music_long_list', guild_id=guild.id)}```"
    for position in range(min(total, QUEUE_DISPLAY_LIMIT), 0, -1):
        lines += f"```#{position:02d} : {queue[position - 1].title}```"
    current_title = current.title if current is not None else settings.Localize("lbl_music_empty", guild_id=guild.id)
    lines += f"\n{settings.Localize('lbl_music_playing', guild_id=guild.id)}\n```#00 : {current_title}```"
    embedded = discord.Embed(description=lines)
    cleared = _cleared_by.get(guild.id)
    if current is not None:
        embedded.set_footer(icon_url=current.user_avatar, text=settings.Localize("lbl_music_requested", current.user_name, guild_id=guild.id))
    elif cleared is not None:
        embedded.set_footer(icon_url=cleared[1], text=settings.Localize("lbl_music_cleared_by", cleared[0], guild_id=guild.id))
    else:
        embedded.set_footer(icon_url="https://i.gifer.com/L7sU.gif", text=settings.Localize("lbl_music_requested", ". . .", guild_id=guild.id))
    return embedded

async def UpdateMusicMessage(guild:discord.Guild):
    """Re-render the guild's music message, when one exists."""
    from scripts import elements
    info = GetMusicMessageInfo(guild.id)
    if info is None:
        return
    channel = guild.get_channel(info[0])
    if channel is None:
        return
    try:
        await channel.get_partial_message(info[1]).edit(embed=BuildMusicEmbed(guild), view=elements.MusicMessageView(guild))
    except Exception as e:
        print(f"Music - Could not update the music message.\nErrors: {e}\n")

async def CreateMusicMessage(guild:discord.Guild, channel) -> discord.Message:
    """Post a fresh music message in the channel and save it, deleting the
    previous one when reachable."""
    from scripts import elements
    info = GetMusicMessageInfo(guild.id)
    if info is not None:
        old_channel = guild.get_channel(info[0])
        if old_channel is not None:
            try:
                await old_channel.get_partial_message(info[1]).delete()
            except Exception:
                pass
    message = await channel.send(embed=BuildMusicEmbed(guild), view=elements.MusicMessageView(guild))
    settings.SetInfo(guild.id, "music_message", f"{channel.id}/{message.id}")
    return message

#endregion

#region Media info

def get_audio_info(info):
    """..."""
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

#region Download

DOWNLOAD_CHUNK = 1024 * 1024  # Ranged request size for parallel downloads.
DOWNLOAD_WORKERS = 6  # Parallel connections per download.

def Download(ctx: discord.Interaction, url:str) -> dict:
    """Blocking: resolve a prompt and fetch its audio in parallel chunks."""
    with yt_dlp.YoutubeDL(ytdl_download_settings) as extractor:
        info = get_audio_info(extractor.extract_info(url, download=False))
    title = info.get("title") or "audio"
    ext = info.get("ext") or "m4a"
    return _BuildAudioFile(info["url"], title, ext, info.get("http_headers"))

def DownloadCurrent(guild:discord.Guild) -> dict:
    """Blocking: fetch the currently playing media's audio, reusing its
    already resolved stream url so no extraction round-trip is paid."""
    data = guild_data.get(guild.id)
    media = data.current if data is not None else None
    if media is None:
        return None
    if not media.IsResolved():
        _ResolveMedia(media)
    return _BuildAudioFile(media.stream_url, media.title, media.ext or "m4a", None)

def _BuildAudioFile(url:str, title:str, ext:str, headers:dict) -> dict:
    audio = _DownloadRanged(url, headers or {})
    # Downloads are always delivered as real mp3 files.
    if ext != "mp3":
        audio = _TranscodeMp3(audio)
    filename = f"{title.replace(' ', '_')}.mp3"
    file = discord.File(io.BytesIO(audio), filename)
    return {"file":file, "title":title}

def _TranscodeMp3(audio:bytes) -> bytes:
    """Blocking: convert downloaded audio to mp3 with the bundled ffmpeg.
    The source goes through a temp file (mp4 containers are not always
    pipeable), the mp3 comes back over stdout without touching disk."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".audio") as source:
        source.write(audio)
        source_path = source.name
    try:
        result = subprocess.run(
            [FFMPEG, "-v", "error", "-i", source_path, "-vn", "-f", "mp3", "-b:a", "192k", "pipe:1"],
            capture_output=True, check=True)
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffmpeg mp3 conversion failed: {e.stderr.decode('utf-8', 'ignore')[:300]}")
    finally:
        os.remove(source_path)

def _DownloadRanged(url:str, headers:dict) -> bytes:
    """Fetch a url over several parallel ranged connections, falling back
    to a single sequential read when ranges are unsupported."""
    probe = urllib.request.Request(url, headers={**headers, "Range": "bytes=0-0"})
    with urllib.request.urlopen(probe, timeout=15) as response:
        content_range = response.headers.get("Content-Range", "")
    total = 0
    if "/" in content_range:
        try:
            total = int(content_range.split("/")[-1])
        except ValueError:
            total = 0
    if not total:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
            return response.read()
    buffer = bytearray(total)
    def fetch(start:int):
        end = min(start + DOWNLOAD_CHUNK, total) - 1
        request = urllib.request.Request(url, headers={**headers, "Range": f"bytes={start}-{end}"})
        with urllib.request.urlopen(request, timeout=60) as response:
            buffer[start:end + 1] = response.read()
    with ThreadPoolExecutor(DOWNLOAD_WORKERS) as pool:
        # Consume the iterator so worker errors surface here.
        for _ in pool.map(fetch, range(0, total, DOWNLOAD_CHUNK)):
            pass
    return bytes(buffer)

#endregion