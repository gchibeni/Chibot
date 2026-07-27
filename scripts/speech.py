import asyncio
import audioop
import io
import json
import os
import queue
import threading
import time
import urllib.request
import wave
import zipfile

import discord

#region Global

try:
    import vosk
    vosk.SetLogLevel(-1)
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

SOURCE_RATE = 48000  # Discord voice PCM rate.
TARGET_RATE = 16000  # Rate the vosk models expect.
MODELS_DIR = "./models"
MODELS = {
    "en": "vosk-model-small-en-us-0.15",
    "pt": "vosk-model-small-pt-0.3",
}
MODEL_URL = "https://alphacephei.com/vosk/models/{name}.zip"
TRIGGER_COOLDOWN = 3.0  # Seconds before the same trigger can refire per user.
BATCH_BYTES = 4800  # Process audio in ~0.15s batches (16kHz mono 16-bit).
CONTEXT_SECONDS = 4.0  # How long a finished utterance still counts for matching.
BYTES_PER_SECOND = TARGET_RATE * 2  # 16kHz mono 16-bit.
PRE_ROLL_SECONDS = 0.6  # Audio kept from before the wake phrase was detected.
# Just enough to cover recognition latency without swallowing whatever
# was being said before the wake word.
CAPTURE_MAX_SECONDS = 6.0  # Longest voice command capture after a wake phrase.
# The idle pause must stay well under CAPTURE_MAX_SECONDS: it is the
# latency of every spoken command (the capture waits this long in silence
# before going to whisper), while still not splitting slow speech.
CAPTURE_IDLE_SECONDS = 1.2  # Pause that consolidates a voice command capture.
WAKE_WINDOW_SECONDS = 2.5  # How long "hey oto" alone waits for a command.
# 1s proved shorter than a natural thinking pause, expiring silently
# right before the user spoke; the armed capture ends quietly anyway.
SPEECH_RMS_THRESHOLD = 250  # Audio energy that counts as speech, not bleed.
# Hint biasing whisper towards the wake word spellings. Deliberately short:
# a vocabulary list in the prompt gets echoed back as hallucinations
# ("replay, replay, replay...") whenever the audio is silent or garbled.
WHISPER_PROMPT = "Hey Oto. Ei Oto. Hey Chibot."

_queue:queue.Queue = queue.Queue(maxsize=512)
_worker:threading.Thread = None
_worker_lock = threading.Lock()
_models:dict[str, "vosk.Model"] = {}
_models_failed = False

_guilds:dict[int, dict] = {}  # guild_id -> {"bot", "guild", "triggers", "grammar", "has_call"}
_recognizers:dict[tuple, "vosk.KaldiRecognizer"] = {}  # (guild_id, user_id, lang)
_resample_states:dict[tuple, tuple] = {}  # (guild_id, user_id)
_audio_buffers:dict[tuple, bytearray] = {}  # (guild_id, user_id)
_recent_finals:dict[tuple, tuple] = {}  # (guild_id, user_id, lang) -> (text, time)
_last_fired:dict[tuple, float] = {}  # (guild_id, user_id, title)
_rolling:dict[tuple, bytearray] = {}  # (guild_id, user_id) pre-roll audio
_captures:dict[tuple, dict] = {}  # (guild_id, user_id) -> {"buffer", "last_audio"}
_wake_counts:dict[tuple, int] = {}  # (guild_id, user_id) wake phrases seen in the current utterance.
_transcribe_queue:queue.Queue = queue.Queue(maxsize=16)
_transcriber:threading.Thread = None
_whisper_model = None
_whisper_failed = False
_dropped_chunks = 0  # Audio chunks lost to recognition backlog.
_last_drop_log = [0.0]

#endregion

#region Public

def RegisterGuild(bot, guild:discord.Guild):
    """Start listening for voice triggers in a guild (call on voice connect).
    Built-in wake word commands are always on, custom triggers optional."""
    from scripts import actions, settings
    triggers = actions.GetTriggers(guild.id, "voice")
    lang = settings.GetLanguage(guild.id)
    _guilds[guild.id] = { "bot":bot, "guild":guild, "triggers":triggers, "grammar":_BuildGrammar(guild.id, triggers), "has_call":True, "lang":lang if lang in MODELS else "en" }
    ...

def UnregisterGuild(guild:discord.Guild):
    """Stop listening and free the guild's recognizers (call on disconnect)."""
    _guilds.pop(guild.id, None)
    _DropRecognizers(guild.id)
    for cache in (_resample_states, _audio_buffers, _recent_finals, _rolling, _captures, _wake_counts):
        for key in [k for k in cache if k[0] == guild.id]:
            cache.pop(key, None)
    ...

def RefreshGuild(guild_id:int):
    """Reload a guild's triggers (call after /triggers or /setup edits)."""
    state = _guilds.get(guild_id)
    if state:
        from scripts import actions, settings
        state["triggers"] = actions.GetTriggers(guild_id, "voice")
        state["grammar"] = _BuildGrammar(guild_id, state["triggers"])
        lang = settings.GetLanguage(guild_id)
        state["lang"] = lang if lang in MODELS else "en"
        # Grammar changed: drop the guild's recognizers to rebuild.
        _DropRecognizers(guild_id)
    ...

def _BuildGrammar(guild_id:int, triggers:dict) -> list[str]:
    """Collect the phrases the vosk recognizers should listen for. The wake
    phrases are always included: built-in commands (play, skip, replay...)
    listen even when a guild has no custom triggers."""
    from scripts import actions
    phrases = []
    for title, data in triggers.items():
        for phrase in actions.GetPhrases(title, data):
            phrase = phrase.lower().strip()
            if phrase.startswith(actions.CALL_PREFIX):
                if WHISPER_AVAILABLE:
                    # Whisper transcribes %call commands after the wake
                    # phrase; vosk only needs to hear the wake phrase.
                    continue
                phrase = phrase[len(actions.CALL_PREFIX):].strip()
            if phrase:
                phrases.append(phrase)
    phrases.extend(actions.GetWakePhrases(guild_id))
    # Fixed builtin commands fire straight from vosk, no whisper wait.
    phrases.extend(actions.BUILTIN_GRAMMAR_PHRASES)
    return phrases

def FeedAudio(guild:discord.Guild, user:discord.User, pcm:bytes):
    """Queue a voice packet for recognition. Must return fast: it is
    called from the voice decode thread."""
    if not VOSK_AVAILABLE or _models_failed:
        return
    state = _guilds.get(guild.id)
    if not state:
        return
    _EnsureWorker()
    try:
        _queue.put_nowait((guild.id, user.id, pcm))
    except queue.Full:
        # The recognition worker cannot keep up: make it visible instead
        # of going silently deaf.
        global _dropped_chunks
        _dropped_chunks += 1
        now = time.monotonic()
        if now - _last_drop_log[0] > 5:
            _last_drop_log[0] = now
            print(f"Speech - Recognition backlog, dropping audio ({_dropped_chunks} chunks dropped so far).")
    ...

#endregion

#region Worker

def _EnsureWorker():
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_WorkerLoop, name="speech-worker", daemon=True)
            _worker.start()

def _WorkerLoop():
    global _models_failed
    try:
        _LoadModels()
    except Exception as e:
        _models_failed = True
        print(f"Speech - Failed to prepare voice models, voice triggers disabled.\nErrors: {e}\n")
        return
    # Preload whisper so the first voice command answers fast.
    if WHISPER_AVAILABLE and any(state.get("has_call") for state in _guilds.values()):
        _EnsureTranscriber()
    while True:
        try:
            guild_id, user_id, pcm = _queue.get(timeout=0.5)
        except queue.Empty:
            _FinalizeIdleCaptures()
            continue
        try:
            _ProcessChunk(guild_id, user_id, pcm)
            _FinalizeIdleCaptures()
        except Exception as e:
            print(f"Speech - Error processing audio chunk.\nErrors: {e}\n")

def _LoadModels():
    os.makedirs(MODELS_DIR, exist_ok=True)
    for lang, name in MODELS.items():
        if lang in _models:
            continue
        path = os.path.join(MODELS_DIR, name)
        if not os.path.isdir(path):
            _DownloadModel(name)
        print(f"Speech - Loading {lang} model...")
        _models[lang] = vosk.Model(path)
    print("Speech - Voice trigger models ready.")

def _DownloadModel(name:str):
    url = MODEL_URL.format(name=name)
    zip_path = os.path.join(MODELS_DIR, f"{name}.zip")
    print(f"Speech - Downloading model {name} (~40MB)...")
    urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path) as file:
        file.extractall(MODELS_DIR)
    os.remove(zip_path)

def _DropRecognizers(guild_id:int):
    for key in [k for k in _recognizers if k[0] == guild_id]:
        _recognizers.pop(key, None)

def _KnownPhrases(model, phrases:list[str]) -> list[str]:
    """Keep only phrases fully inside the model's vocabulary. Vosk drops
    unknown words with a warning, degrading phrases (a wake phrase with an
    unknown name would collapse to just "hey"), so the phrase goes to the
    other language's recognizer instead."""
    if not hasattr(model, "vosk_model_find_word"):
        return list(phrases)
    known = []
    for phrase in phrases:
        if all(model.vosk_model_find_word(word) != -1 for word in phrase.split()):
            known.append(phrase)
    return known

def _GetRecognizer(guild_id:int, user_id:int, lang:str, phrases:list[str]):
    key = (guild_id, user_id, lang)
    recognizer = _recognizers.get(key)
    if recognizer is None:
        # Default json.dumps escapes accented characters into ASCII "u00e7"
        # style sequences, which vosk then rejects as unknown words.
        grammar = json.dumps(_KnownPhrases(_models[lang], phrases) + ["[unk]"], ensure_ascii=False)
        recognizer = vosk.KaldiRecognizer(_models[lang], TARGET_RATE, grammar)
        _recognizers[key] = recognizer
    return recognizer

def _ResetRecognition(guild_id:int, user_id:int):
    """Clear a user's recognizer streams and wake bookkeeping, so a fired
    or consumed utterance cannot match again."""
    for lang in _models:
        key = (guild_id, user_id, lang)
        if key in _recognizers:
            _recognizers[key].Reset()
        _recent_finals.pop(key, None)
    _wake_counts.pop((guild_id, user_id), None)

def _ProcessChunk(guild_id:int, user_id:int, pcm:bytes):
    from scripts import actions, settings
    state = _guilds.get(guild_id)
    if not state:
        return
    triggers = state["triggers"]
    # Downmix stereo 48kHz to mono 16kHz.
    key = (guild_id, user_id)
    mono = audioop.tomono(pcm, 2, 0.5, 0.5)
    resampled, _resample_states[key] = audioop.ratecv(
        mono, 2, 1, SOURCE_RATE, TARGET_RATE, _resample_states.get(key))
    # Keep a short pre-roll so captures include speech from just before
    # the wake phrase was recognized.
    rolling = _rolling.setdefault(key, bytearray())
    rolling.extend(resampled)
    del rolling[:max(0, len(rolling) - int(PRE_ROLL_SECONDS * BYTES_PER_SECOND))]
    # Feed an active voice command capture. Only audio with real speech
    # energy refreshes the idle timer, so background music bleed cannot
    # keep a capture from consolidating.
    capture = _captures.get(key)
    if capture is not None:
        capture["buffer"].extend(resampled)
        if audioop.rms(resampled, 2) > SPEECH_RMS_THRESHOLD:
            capture["last_audio"] = time.monotonic()
            capture["got_audio"] = True
        if len(capture["buffer"]) >= CAPTURE_MAX_SECONDS * BYTES_PER_SECOND:
            _FinalizeCapture(key)
    # Batch audio so the recognizers run a few times per second, not per packet.
    batch = _audio_buffers.setdefault(key, bytearray())
    batch.extend(resampled)
    if len(batch) < BATCH_BYTES:
        return
    data = bytes(batch)
    batch.clear()
    now = time.monotonic()
    # Recognize only in the server's configured language (cached in the
    # guild state: reading settings from disk per chunk lagged the worker).
    guild_lang = state.get("lang", "en")
    if guild_lang not in _models:
        guild_lang = "en"
    for lang in (guild_lang,):
        recognizer = _GetRecognizer(guild_id, user_id, lang, state["grammar"])
        text_key = (guild_id, user_id, lang)
        recent, recent_time = _recent_finals.get(text_key, ("", 0))
        is_final = recognizer.AcceptWaveform(data)
        if is_final:
            text = json.loads(recognizer.Result()).get("text", "")
            if text:
                # Utterance finished: remember it for cross-pause matching.
                _recent_finals[text_key] = (text, now)
                if settings.SPEECH_DEBUG:
                    print(f"Speech - Heard ({lang}) from {user_id}: \"{text}\"")
        else:
            text = json.loads(recognizer.PartialResult()).get("partial", "")
        if not text:
            if is_final:
                # Even an empty final closes the partial stream.
                _wake_counts.pop(key, None)
            continue
        # Every NEW wake phrase (re)starts the voice command capture, so
        # "hey oto... hey oto play x" always starts the command at the
        # LAST wake heard. Occurrences are counted because a partial
        # result repeats the same wake on every batch: only an increase
        # is a fresh wake, not the previous one still in the stream.
        if WHISPER_AVAILABLE and not _whisper_failed and state["has_call"]:
            wake_count = actions.CountWakePhrases(text, guild_id)
            if wake_count > _wake_counts.get(key, 0):
                _StartCapture(guild_id, user_id)
            _wake_counts[key] = wake_count
        if is_final:
            # The utterance closed: the next partial starts a fresh count.
            _wake_counts.pop(key, None)
        # Prepend the previous utterance so phrases split by a short pause
        # (e.g. "hey oto" ... "tocar musica") still match together.
        match_text = f"{recent} {text}" if now - recent_time < CONTEXT_SECONDS else text
        for title, trigger in actions.MatchTriggers(match_text, triggers, guild_id):
            if _Cooldown(guild_id, user_id, title):
                _FireTrigger(guild_id, user_id, trigger)
                # Reset so the same utterance cannot rematch.
                _ResetRecognition(guild_id, user_id)
                return
        # Fixed builtin commands ("hey oto pause") fire straight from
        # vosk for instant response; the whisper capture is dropped and
        # the cooldown swallows whisper's duplicate of the utterance.
        if _TryBuiltin(guild_id, user_id, match_text, fixed_only=True):
            if settings.SPEECH_DEBUG:
                print(f"Speech - Fast builtin fired from {user_id}: \"{match_text}\"")
            _captures.pop(key, None)
            _UpdateDucking(guild_id)
            _ResetRecognition(guild_id, user_id)
            return

def _Cooldown(guild_id:int, user_id:int, phrase:str) -> bool:
    key = (guild_id, user_id, phrase)
    now = time.monotonic()
    if now - _last_fired.get(key, 0) < TRIGGER_COOLDOWN:
        return False
    _last_fired[key] = now
    return True

def _ResponseChannel(guild:discord.Guild, member:discord.Member):
    """Voice responses go to the configured response channel when set,
    the voice channel's own chat otherwise."""
    from scripts import settings
    channel = member.voice.channel if member.voice else None
    response_channel_id = settings.GetInfo(guild.id, "setup/text_channel")
    if response_channel_id:
        response_channel = guild.get_channel(int(response_channel_id))
        if response_channel is not None:
            channel = response_channel
    return channel

def _FireTrigger(guild_id:int, user_id:int, trigger:dict):
    state = _guilds.get(guild_id)
    if state is None:
        return
    from scripts import actions
    bot = state["bot"]
    guild:discord.Guild = state["guild"]
    member = guild.get_member(user_id)
    if member is None or member.voice is None:
        return
    channel = _ResponseChannel(guild, member)
    asyncio.run_coroutine_threadsafe(
        actions.FireTrigger(bot, guild, channel, member, trigger), bot.loop)

def _TryBuiltin(guild_id:int, user_id:int, text:str, fixed_only:bool = False) -> bool:
    """Fire a built-in wake word command from recognized speech. With
    fixed_only, only argument-free commands preceded by the wake phrase
    fire (the vosk fast path); free-form ones wait for whisper."""
    state = _guilds.get(guild_id)
    if state is None:
        return False
    from scripts import actions
    if fixed_only and not actions.HasWakePhrase(text, guild_id):
        return False
    matched = actions.MatchBuiltinCommand(text, guild_id)
    if matched is None:
        return False
    if fixed_only and matched[2]:
        return False
    # The cooldown exists so the vosk fast path and whisper's transcription
    # of the SAME utterance cannot double-fire. Only argument-free commands
    # can take both paths: commands with arguments fire from whisper alone,
    # so they skip the cooldown and an immediate retry after a failed
    # attempt ("hey oto play x"... "hey oto play x!") always works.
    if not matched[2] and not _Cooldown(guild_id, user_id, f"builtin-{matched[0]}"):
        return True
    bot = state["bot"]
    guild:discord.Guild = state["guild"]
    member = guild.get_member(user_id)
    if member is None or member.voice is None:
        return False
    from scripts import settings
    if settings.SPEECH_DEBUG:
        print(f"Speech - Builtin voice command \"{matched[0]}\" from {user_id}.")
    channel = _ResponseChannel(guild, member)
    asyncio.run_coroutine_threadsafe(
        actions.FireBuiltinCommand(bot, guild, channel, member, matched), bot.loop)
    return True

#endregion

#region Whisper

def _WakeOnlyBytes() -> int:
    """Capture length below which the audio is likely just the wake phrase."""
    return int((PRE_ROLL_SECONDS + 2.5) * BYTES_PER_SECOND)

def _UpdateDucking(guild_id:int):
    """Duck the music while any voice command capture is active."""
    from scripts import voice
    try:
        voice.DuckMusic(guild_id, any(key[0] == guild_id for key in _captures))
    except Exception:
        pass

def _StartCapture(guild_id:int, user_id:int, armed:bool = False):
    """Begin recording a voice command for whisper transcription.

    An "armed" capture (wake phrase heard, command not started yet) waits
    up to WAKE_WINDOW_SECONDS for the user to start speaking again.
    """
    from scripts import settings, voice
    key = (guild_id, user_id)
    now = time.monotonic()
    _captures[key] = { "buffer":bytearray(_rolling.get(key, b"")), "last_audio":now, "got_audio":not armed }
    _UpdateDucking(guild_id)
    # Acknowledge the wake word with a sound (pitch varies per play).
    if not armed:
        try:
            voice.PlayAcknowledge(guild_id)
        except Exception as e:
            print(f"Speech - Could not play the acknowledgment sound.\nErrors: {e}\n")
    if settings.SPEECH_DEBUG:
        print(f"Speech - {'Waiting for' if armed else 'Capturing'} command from {user_id}...")

def _FinalizeIdleCaptures():
    now = time.monotonic()
    for key in list(_captures):
        capture = _captures[key]
        idle = now - capture["last_audio"]
        if not capture["got_audio"]:
            # Armed but no command yet: expire quietly after the window.
            if idle > WAKE_WINDOW_SECONDS:
                _captures.pop(key, None)
                _UpdateDucking(key[0])
        elif idle > CAPTURE_IDLE_SECONDS:
            _FinalizeCapture(key)

def _FinalizeCapture(key:tuple):
    """Send a finished capture to the transcriber."""
    capture = _captures.pop(key, None)
    if capture is None:
        return
    guild_id, user_id = key
    _UpdateDucking(guild_id)
    # Clear the wake phrase from the recognizer streams.
    _ResetRecognition(guild_id, user_id)
    _EnsureTranscriber()
    audio = bytes(capture["buffer"])
    try:
        _transcribe_queue.put_nowait((guild_id, user_id, audio))
    except queue.Full:
        print("Speech - Transcription backlog, dropping a voice command capture.")
    # A capture barely longer than the wake phrase itself means the user
    # called the bot and paused. Keep listening RIGHT NOW: waiting for
    # whisper to confirm the wake first left a deaf gap of several
    # seconds in which the actual command was spoken and lost.
    if len(audio) <= _WakeOnlyBytes():
        _StartCapture(guild_id, user_id, armed=True)

def _EnsureTranscriber():
    global _transcriber
    with _worker_lock:
        if _transcriber is None or not _transcriber.is_alive():
            _transcriber = threading.Thread(target=_TranscriberLoop, name="speech-transcriber", daemon=True)
            _transcriber.start()

def _TranscriberLoop():
    global _whisper_model, _whisper_failed
    from scripts import settings
    try:
        if _whisper_model is None:
            print(f"Speech - Loading whisper model \"{settings.WHISPER_MODEL}\"...")
            # Leave cores free for the voice decode and playback threads,
            # so transcription never makes the recording glitch.
            threads = max(1, min(4, (os.cpu_count() or 4) - 2))
            _whisper_model = WhisperModel(settings.WHISPER_MODEL, device="cpu", compute_type="int8", cpu_threads=threads)
            print("Speech - Whisper model ready.")
    except Exception as e:
        _whisper_failed = True
        print(f"Speech - Failed to load whisper model, voice commands disabled.\nErrors: {e}\n")
        return
    while True:
        guild_id, user_id, audio = _transcribe_queue.get()
        try:
            _Transcribe(guild_id, user_id, audio)
        except Exception as e:
            print(f"Speech - Error transcribing voice command.\nErrors: {e}\n")

def _CleanTranscription(text:str) -> str:
    """Scrub whisper hallucinations: collapse repeated-word runs and
    discard transcripts that are one phrase looped over and over."""
    words = text.replace(",", " ").split()
    collapsed = []
    for word in words:
        if len(collapsed) >= 2 and word.lower() == collapsed[-1].lower() == collapsed[-2].lower():
            continue
        collapsed.append(word)
    # A long transcript made of almost nothing but repeats is a loop.
    if len(words) >= 8 and len(set(word.lower() for word in words)) <= max(2, len(words) // 6):
        return ""
    return " ".join(collapsed).strip()

def _Transcribe(guild_id:int, user_id:int, audio:bytes):
    """Transcribe a captured voice command and fire matching %call triggers."""
    from scripts import actions, settings
    state = _guilds.get(guild_id)
    if state is None or not audio:
        return
    # Wrap the raw PCM in an in-memory wav for whisper.
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(TARGET_RATE)
        file.writeframes(audio)
    buffer.seek(0)
    # temperature=0 and no text conditioning cut whisper's hallucination
    # loops on short noisy clips; the prompt only biases the wake words.
    # The language is always the server's configured one: auto-detection
    # on short clips guessed wildly (Swedish, Turkish...) and cost a
    # second pass to correct.
    options = { "vad_filter":True, "beam_size":3, "temperature":0.0, "condition_on_previous_text":False, "initial_prompt":WHISPER_PROMPT }
    segments, info = _whisper_model.transcribe(buffer, language=state.get("lang", "en"), **options)
    text = _CleanTranscription(" ".join(segment.text for segment in segments))
    if settings.SPEECH_DEBUG:
        print(f"Speech - Whisper heard ({info.language}) from {user_id}: \"{text}\"")
    if not text:
        return
    matches = actions.MatchCallTriggers(text, state["triggers"])
    for title, trigger in matches:
        if _Cooldown(guild_id, user_id, title):
            _FireTrigger(guild_id, user_id, trigger)
    # Custom triggers take precedence, built-in commands run otherwise.
    fired = bool(matches) or _TryBuiltin(guild_id, user_id, text)
    # The user likely said only the wake phrase and paused (vosk already
    # confirmed the wake): keep listening for the actual command. Never
    # clobber a capture that is already running (a new wake or the
    # immediate re-arm from _FinalizeCapture may have started one).
    if not fired and (actions.HasWakePhrase(text, guild_id) or len(audio) <= _WakeOnlyBytes()):
        if (guild_id, user_id) not in _captures:
            _StartCapture(guild_id, user_id, armed=True)

#endregion
