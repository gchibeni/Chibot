from scripts import settings, voice, elements
import asyncio
import difflib
import discord
import random
import re
import unicodedata

#region Global

# Bot call names selectable per guild via /setup, accents are ignored.
# The extra spellings are phonetic aliases that exist in the vosk model
# vocabularies ("chibot" itself is in neither), so the recognizers can
# actually hear the wake word.
WAKE_WORD_OPTIONS = {
    "oto": ["hey oto", "ei oto", "hey otto", "ei otto", "hey óto", "ei óto", "ai oto", "ai otto", "oi otto"],
    "chibot": ["hey chibot", "ei chibot", "hey chi bot", "ei xi bote", "ai chibot", "ai xi bote"],
}
DEFAULT_WAKE_WORD = "oto"
CALL_PREFIX = "%call"  # Phrases starting with this require a wake phrase first.
MAX_WAIT = 30  # Longest %wait allowed in an action sequence, in seconds.

class TriggerContext:
    """Minimal Interaction-like shim so trigger actions can reuse the
    views from elements.py, which only read ctx.user and ctx.data."""
    def __init__(self, guild:discord.Guild, channel, user:discord.Member):
        self.guild = guild
        self.channel = channel
        self.user = user
        self.data = {}

#endregion

#region Engine

async def FireTrigger(bot, guild:discord.Guild, channel, user:discord.Member, trigger:dict):
    """Execute a trigger's actions: one random line, all in sequence, or
    every line joined as a single action."""
    actions = [line.strip() for line in trigger.get("actions", []) if line.strip()]
    if not actions:
        return
    play = trigger.get("play", "random")
    if play == "sequence":
        lines = actions
    elif play == "one":
        lines = ["\n".join(actions)]
    else:
        lines = [random.choice(actions)]
    for line in lines:
        try:
            await ExecuteAction(bot, guild, channel, user, line)
        except Exception as e:
            print(f"Triggers - Failed to execute action \"{line}\".\nErrors: {e}\n")

async def ExecuteAction(bot, guild:discord.Guild, channel, user:discord.Member, line:str):
    """Execute a single action line.

    "/name args" runs a bot command, "%name args" runs a custom action,
    anything else is sent to the channel as a response.
    """
    if line.startswith("/"):
        name, *args = line[1:].split()
        handler = COMMAND_ACTIONS.get(name.lower())
        if handler is None:
            print(f"Triggers - Unknown command action \"{line}\".\n")
            return
        await handler(bot, guild, channel, user, args)
    elif line.startswith("%"):
        name, *args = line[1:].split()
        handler = CUSTOM_ACTIONS.get(name.lower())
        if handler is None:
            print(f"Triggers - Unknown custom action \"{line}\".\n")
            return
        await handler(bot, guild, channel, user, args)
    else:
        await channel.send(ReplaceTokens(line, user))

def ReplaceTokens(text:str, user:discord.Member) -> str:
    return text.replace("@self", user.mention)

def ResolveTarget(guild:discord.Guild, user:discord.Member, args:list[str]) -> discord.Member:
    """Resolve an action target: @self, a mention, or a raw user id."""
    if not args:
        return user
    token = args[0]
    if token.lower() == "@self":
        return user
    match = re.fullmatch(r"<@!?(\d+)>|(\d+)", token)
    if match:
        member = guild.get_member(int(match.group(1) or match.group(2)))
        if member:
            return member
    return user

#endregion

#region Actions

async def _command_replay(bot, guild, channel, user, args):
    seconds = int(args[0]) if args and args[0].isdigit() else 15
    seconds = min(max(seconds, 5), settings.MAX_RECORDING_TIME)
    file = await asyncio.to_thread(voice.SaveReplayForGuild, guild, seconds, 1)
    if file is not None:
        await channel.send(settings.Localize("lbl_replay_complete", seconds, 1), file=file)

async def _command_roll(bot, guild, channel, user, args):
    number = int(args[0]) if args and args[0].isdigit() else 20
    view = elements.RollView(TriggerContext(guild, channel, user), max(number, 2))
    await channel.send(view=view)

async def _command_flip(bot, guild, channel, user, args):
    view = elements.FlipView(TriggerContext(guild, channel, user))
    await channel.send(view=view)

async def _command_roulette(bot, guild, channel, user, args):
    view = elements.RouletteView(TriggerContext(guild, channel, user))
    await channel.send(view=view)

async def _custom_disconnect(bot, guild, channel, user, args):
    target = ResolveTarget(guild, user, args)
    if target.voice and target.voice.channel:
        await target.move_to(None, reason="Chibot trigger")

async def _custom_kick(bot, guild, channel, user, args):
    target = ResolveTarget(guild, user, args)
    await target.kick(reason="Chibot trigger")

async def _custom_mute(bot, guild, channel, user, args):
    target = ResolveTarget(guild, user, args)
    if target.voice:
        await target.edit(mute=True, reason="Chibot trigger")

async def _custom_unmute(bot, guild, channel, user, args):
    target = ResolveTarget(guild, user, args)
    if target.voice:
        await target.edit(mute=False, reason="Chibot trigger")

async def _custom_deafen(bot, guild, channel, user, args):
    target = ResolveTarget(guild, user, args)
    if target.voice:
        await target.edit(deafen=True, reason="Chibot trigger")

async def _custom_undeafen(bot, guild, channel, user, args):
    target = ResolveTarget(guild, user, args)
    if target.voice:
        await target.edit(deafen=False, reason="Chibot trigger")

async def _custom_move(bot, guild, channel, user, args):
    """%move [@target] <voice channel name>"""
    target = ResolveTarget(guild, user, args)
    name_args = args[1:] if args and (args[0].lower() == "@self" or re.fullmatch(r"<@!?\d+>|\d+", args[0])) else args
    name = " ".join(name_args).lower()
    destination = discord.utils.find(lambda c: c.name.lower() == name, guild.voice_channels)
    if destination and target.voice:
        await target.move_to(destination, reason="Chibot trigger")

async def _custom_wait(bot, guild, channel, user, args):
    """%wait <seconds> — pause between actions in a sequence."""
    try:
        seconds = float(args[0]) if args else 1
    except ValueError:
        seconds = 1
    await asyncio.sleep(min(max(seconds, 0), MAX_WAIT))

COMMAND_ACTIONS = {
    "replay": _command_replay,
    "roll": _command_roll,
    "flip": _command_flip,
    "roulette": _command_roulette,
}

CUSTOM_ACTIONS = {
    "disconnect": _custom_disconnect,
    "kick": _custom_kick,
    "mute": _custom_mute,
    "unmute": _custom_unmute,
    "deafen": _custom_deafen,
    "undeafen": _custom_undeafen,
    "move": _custom_move,
    "wait": _custom_wait,
}

#endregion

#region Voice commands

# Built-in wake word commands ("hey oto, play imagine dragons"), matched
# against the whisper transcription. Ordered: first fullmatch wins, so
# scrub-with-seconds outranks "previous", and bare "play music" resumes
# before "play <prompt>" queues.

async def _voice_play(bot, guild, channel, member, args):
    prompt = (args.get("prompt") or "").strip()
    if prompt:
        await voice.QueueMedia(guild, prompt, member, push=bool(args.get("push")))
        return
    # Resume paused media or start whatever is queued.
    if not voice.ResumeMusic(guild):
        await voice.PlayNext(guild)
    await voice.UpdateMusicMessage(guild)

async def _voice_push(bot, guild, channel, member, args):
    args = dict(args)
    args["push"] = True
    await _voice_play(bot, guild, channel, member, args)

async def _voice_pause(bot, guild, channel, member, args):
    if voice.PauseMusic(guild):
        await voice.UpdateMusicMessage(guild)

async def _voice_next(bot, guild, channel, member, args):
    await voice.PlayNext(guild)

async def _voice_prev(bot, guild, channel, member, args):
    await voice.PlayPrev(guild)

async def _voice_shuffle(bot, guild, channel, member, args):
    await voice.ShuffleQueue(guild)

async def _voice_loop(bot, guild, channel, member, args):
    await voice.ToggleLoop(guild)

async def _voice_forward(bot, guild, channel, member, args):
    await voice.ScrubRelative(guild, float(args.get("seconds") or 10))

async def _voice_backward(bot, guild, channel, member, args):
    await voice.ScrubRelative(guild, -float(args.get("seconds") or 10))

async def _voice_download(bot, guild, channel, member, args):
    file = await asyncio.to_thread(voice.DownloadCurrent, guild)
    if file is not None and channel is not None:
        await channel.send(settings.Localize("lbl_download_complete", file["title"], guild_id=guild.id), file=file["file"])

async def _voice_replay(bot, guild, channel, member, args):
    seconds = args.get("seconds")
    await _command_replay(bot, guild, channel, member, [seconds] if seconds else [])

async def _voice_transcribe(bot, guild, channel, member, args):
    message = (args.get("message") or "").strip()
    if message and channel is not None:
        embedded = discord.Embed(description=message)
        embedded.set_footer(icon_url=member.display_avatar.url, text=settings.Localize("lbl_transcribe_footer", member.display_name, guild_id=guild.id))
        await channel.send(embed=embedded)

_NUM = r"(?P<seconds>\d+)"
BUILTIN_VOICE_COMMANDS = [
    # Scrubbing with a number first: "volta 10 segundos" beats "volta".
    ("backward", rf"(?:backwards?|rewind|go back|volta|voltar|retrocede) {_NUM}(?: ?(?:seconds?|segundos?))?", _voice_backward),
    ("forward", rf"(?:forward|fast forward|skip ahead|avanca|avancar|adianta) {_NUM}(?: ?(?:seconds?|segundos?))?", _voice_forward),
    ("backward", r"(?:backwards?|rewind)(?: a (?:bit|little))?", _voice_backward),
    ("forward", r"(?:fast forward|skip ahead)(?: a (?:bit|little))?", _voice_forward),
    ("replay", rf"(?:(?:save|salva|salve|salvar) )?(?:a |the |o |um )?replay(?: (?:from|of|dos) (?:the )?(?:last|ultimos) {_NUM} ?(?:seconds?|segundos?))?", _voice_replay),
    ("replay", r"clip (?:that|this|it|isso)", _voice_replay),
    ("transcribe", r"(?:transcribe|transcreve|transcreva|transcrever|anota|anote|anotar|escreve|escreva) (?P<message>.+)", _voice_transcribe),
    # Download needs an explicit object ("download this music"), a bare
    # "download" is too easy to misfire.
    ("download", r"(?:download|baixa|baixe|baixar) (?:this|that|it|this music|this song|the music|the song|essa musica|a musica|musica|music|song|isso)", _voice_download),
    ("push", r"(?:push|play now|toca agora|toque agora) (?P<prompt>.+)", _voice_push),
    ("pause", r"(?:pause|pausa|pause|pausar|hold|stop|stop it|pare|para|parar)(?: (?:the |a )?(?:music|song|musica))?", _voice_pause),
    # Bare "play (music)" resumes; with anything else it queues below.
    ("resume", r"(?:play|resume|continue|unpause|start|toca|toque|tocar|continua|continue|continuar|retoma|retome)(?: (?:the |a |some )?(?:music|song|musica))?", _voice_play),
    ("next", r"(?:next|skip|proxima|proximo|pula|pule|pular|passa|passe|passar)(?: (?:this |the |essa |esse )?(?:song|music|track|one|musica))?", _voice_next),
    ("previous", r"(?:previous|prev|go back|anterior|volta|volte|voltar)(?: (?:song|music|track|one|musica))?", _voice_prev),
    ("shuffle", r"(?:shuffle|embaralha|embaralhe|embaralhar|mistura|misture|misturar)(?: (?:the |a )?(?:queue|playlist|fila))?", _voice_shuffle),
    ("loop", r"(?:toggle )?(?:repeat|loop|repetir|repete|repita)(?: (?:on|off|mode|the (?:queue|playlist)))?", _voice_loop),
    ("queue", r"(?:play|queue|add|toca|toque|tocar|adiciona|adicione|adicionar|coloca|coloque|colocar|bota|bote|botar) (?P<prompt>.+)", _voice_play),
]

# Every verb the command patterns accept, for fuzzy correction of near
# misses in the transcription ("transcriva" -> "transcreva").
VOICE_COMMAND_VERBS = [
    "play", "queue", "add", "push", "pause", "hold", "stop", "resume", "continue", "unpause",
    "start", "next", "skip", "previous", "prev", "shuffle", "repeat", "loop", "replay", "clip",
    "download", "transcribe", "forward", "rewind", "backward", "backwards",
    "toca", "toque", "tocar", "adiciona", "adicione", "adicionar", "coloca", "coloque", "colocar",
    "bota", "bote", "botar", "pausa", "pausar", "pare", "para", "parar", "continua", "continuar",
    "retoma", "retome", "proxima", "proximo", "pula", "pule", "pular", "passa", "passe", "passar",
    "anterior", "volta", "volte", "voltar", "embaralha", "embaralhe", "embaralhar", "mistura",
    "misture", "misturar", "repete", "repita", "repetir", "baixa", "baixe", "baixar",
    "transcreve", "transcreva", "transcrever", "anota", "anote", "anotar", "escreve", "escreva",
    "avanca", "avance", "avancar", "adianta", "salva", "salve", "salvar",
]

# Single-word commands added to the vosk grammar: they fire straight from
# vosk (no whisper round-trip), so pause/skip react in under a second.
BUILTIN_GRAMMAR_PHRASES = [
    "play", "pause", "stop", "continue", "resume", "next", "skip", "previous", "shuffle",
    "repeat", "loop", "replay",
    "toca", "tocar", "pausa", "pare", "para", "continua", "proxima", "proximo", "pula",
    "passa", "volta", "anterior", "embaralha", "mistura", "repete", "repetir",
]

def _CorrectVerb(word:str) -> str:
    matches = difflib.get_close_matches(word, VOICE_COMMAND_VERBS, n=1, cutoff=0.75)
    return matches[0] if matches else word

def MatchBuiltinCommand(text:str, guild_id:int):
    """Match transcribed speech against the built-in voice commands.
    Returns (name, handler, args) or None.

    Transcriptions are messy (wake word variations, fillers, punctuation,
    near-miss verbs), so after stripping the wake phrase, leading words
    are progressively dropped and the leading verb is fuzzy-corrected
    until a command matches: "ei o to transcriva banana" still works."""
    clean = NormalizeText(text)
    # Drop the wake phrase, punctuation and vosk's [unk] fillers.
    clean = re.sub(rf"(?<!\w)(?:{_WakePattern(guild_id)})(?!\w)", " ", clean)
    clean = " ".join(re.sub(r"[^\w\s]", " ", clean).split())
    clean = re.sub(r"^(?:please |por favor )+", "", clean)
    words = [word for word in clean.split() if word != "unk"]
    def try_match(candidate:str):
        for name, pattern, handler in BUILTIN_VOICE_COMMANDS:
            match = re.fullmatch(pattern, candidate)
            if match:
                return name, handler, {key: value for key, value in match.groupdict().items() if value}
        return None
    # Trim at most a few leading fillers, so a command buried at the end
    # of an unrelated long sentence does not fire by accident.
    for start in range(0, min(4, len(words))):
        candidate_words = words[start:]
        matched = try_match(" ".join(candidate_words))
        if matched is not None:
            return matched
        # Retry with the leading verb fuzzy-corrected.
        corrected = _CorrectVerb(candidate_words[0])
        if corrected != candidate_words[0]:
            matched = try_match(" ".join([corrected] + candidate_words[1:]))
            if matched is not None:
                return matched
    return None

async def FireBuiltinCommand(bot, guild:discord.Guild, channel, member:discord.Member, matched):
    name, handler, args = matched
    try:
        await handler(bot, guild, channel, member, args)
    except Exception as e:
        print(f"Voice - Failed builtin voice command \"{name}\".\nErrors: {e}\n")

#endregion

#region Matching

def NormalizeText(text:str) -> str:
    """Lowercase, strip accents and collapse whitespace for matching."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.split())

def _PhrasePattern(phrase:str) -> str:
    """Regex for a normalized phrase, tolerant of punctuation between words."""
    return r"\W+".join(re.escape(word) for word in phrase.split())

def GetWakeWord(guild_id:int) -> str:
    """The guild's configured wake word key, or the default."""
    wake = settings.GetInfo(guild_id, "setup/wake_word")
    return wake if wake in WAKE_WORD_OPTIONS else DEFAULT_WAKE_WORD

def GetWakePhrases(guild_id:int) -> list[str]:
    """The wake phrases the guild answers to."""
    return WAKE_WORD_OPTIONS[GetWakeWord(guild_id)]

def _WakePattern(guild_id:int) -> str:
    return "|".join(_PhrasePattern(NormalizeText(wake)) for wake in GetWakePhrases(guild_id))

def GetTriggers(guild_id:int, mode:str) -> dict[str, dict]:
    """Fetch guild triggers filtered to those active for the given mode."""
    triggers = settings.GetInfo(guild_id, "triggers") or {}
    return {
        title: data for title, data in triggers.items()
        if data.get("mode", "text") in (mode, "both")
    }

def GetPhrases(title:str, data:dict) -> list[str]:
    """A trigger's phrase lines. Old entries used their key as the phrase."""
    return data.get("phrases") or [title]

def GetCallPhrases(title:str, data:dict) -> list[str]:
    """A trigger's %call phrases, normalized, with the prefix stripped."""
    phrases = []
    for phrase in GetPhrases(title, data):
        phrase = NormalizeText(phrase)
        if phrase.startswith(CALL_PREFIX):
            phrase = phrase[len(CALL_PREFIX):].strip()
            if phrase:
                phrases.append(phrase)
    return phrases

def HasWakePhrase(text:str, guild_id:int) -> bool:
    """Whether the text contains one of the guild's wake phrases."""
    return re.search(rf"(?<!\w)(?:{_WakePattern(guild_id)})(?!\w)", NormalizeText(text)) is not None

def CountWakePhrases(text:str, guild_id:int) -> int:
    """How many wake phrases the text contains. Recognizer partials repeat
    the same text every batch, so speech.py compares counts between batches
    to tell a NEW "hey oto" from the same one still sitting in the stream."""
    return len(re.findall(rf"(?<!\w)(?:{_WakePattern(guild_id)})(?!\w)", NormalizeText(text)))

def MatchCallTriggers(text:str, triggers:dict[str, dict]) -> list[tuple[str, dict]]:
    """Match %call phrases WITHOUT requiring the wake words, for use on
    audio captured right after a wake phrase was already heard."""
    text = NormalizeText(text)
    matched = []
    for title, data in triggers.items():
        for phrase in GetCallPhrases(title, data):
            if re.search(rf"(?<!\w){_PhrasePattern(phrase)}(?!\w)", text):
                matched.append((title, data))
                break
    return matched

def MatchTriggers(text:str, triggers:dict[str, dict], guild_id:int) -> list[tuple[str, dict]]:
    """Return (title, trigger) pairs whose phrases appear in the text.

    Phrases starting with %call only match when preceded by the guild's wake
    phrase ("hey oto ..."). Matching ignores case, accents and punctuation.
    """
    text = NormalizeText(text)
    wake_pattern = _WakePattern(guild_id)
    matched = []
    for title, data in triggers.items():
        for phrase in GetPhrases(title, data):
            phrase = NormalizeText(phrase)
            requires_call = phrase.startswith(CALL_PREFIX)
            if requires_call:
                phrase = phrase[len(CALL_PREFIX):].strip()
            if not phrase:
                continue
            pattern = rf"(?<!\w){_PhrasePattern(phrase)}(?!\w)"
            if requires_call:
                pattern = rf"(?<!\w)(?:{wake_pattern})\W+{_PhrasePattern(phrase)}(?!\w)"
            if re.search(pattern, text):
                matched.append((title, data))
                break
    return matched

async def CheckTextTriggers(bot, message:discord.Message):
    """Run text-mode triggers against a guild message."""
    triggers = GetTriggers(message.guild.id, "text")
    if not triggers:
        return
    for title, trigger in MatchTriggers(message.content, triggers, message.guild.id):
        await FireTrigger(bot, message.guild, message.channel, message.author, trigger)

#endregion
