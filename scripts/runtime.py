"""Process startup: working directory, bundled binaries and the entry point.

Chibot reads and writes several paths relative to the working directory
(``token.secret``, ``settings.json``, ``locale.json``, ``guilds/``). Rather
than rewrite each one, :func:`main` moves the process to the project root
before the bot is imported, so the bot behaves identically no matter where
it was launched from.
"""

import os
import shutil
import sys
from functools import lru_cache
from getpass import getpass
from pathlib import Path

from colorama import Fore, Style

# The project root — the folder holding this package, locale.json and guilds/.
ROOT = Path(__file__).resolve().parent.parent

TOKEN_FILE = ROOT / 'token.secret'


@lru_cache(maxsize=1)
def ffmpeg_executable() -> str:
    """Locate ffmpeg, preferring a system install over the bundled copy.

    A system ffmpeg is a full build and ships ffprobe alongside it, so it is
    used when present. Otherwise Chibot falls back to the binary vendored in
    the ``imageio-ffmpeg`` wheel, which means a fresh clone plays audio
    without anyone installing ffmpeg by hand.
    """
    system = shutil.which('ffmpeg')
    if system:
        return system
    from imageio_ffmpeg import get_ffmpeg_exe
    return get_ffmpeg_exe()


def ensure_opus() -> bool:
    """Load libopus, warning clearly if it is missing.

    discord.py vendors libopus for Windows, so nothing is needed there. On
    Linux and macOS it is resolved from the system, and it is the one library
    Chibot cannot ship for you. Voice is the only feature that needs it, so a
    failure warns rather than aborts.
    """
    import discord

    try:
        if discord.opus.is_loaded() or discord.opus._load_default():
            return True
    except Exception:
        pass

    hint = {
        'linux': 'sudo apt install libopus0',
        'darwin': 'brew install opus',
    }.get(sys.platform, 'install the libopus shared library')
    print(
        f'{Fore.RED}> libopus not found — voice features will fail.\n'
        f'> Fix it with: {hint}{Style.RESET_ALL}'
    )
    return False


def configure_pydub() -> None:
    """Point pydub at our ffmpeg before it probes for one itself.

    pydub warns at import time if no ffmpeg is on PATH, which is noise when
    we are about to hand it an explicit path. Importing it here, quietly and
    first, keeps that warning out of the startup output.
    """
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)
        from pydub import AudioSegment
    AudioSegment.converter = ffmpeg_executable()


def read_token() -> str:
    """Return the bot token, prompting for it on first run."""
    if not TOKEN_FILE.is_file():
        token = getpass(f'{Fore.YELLOW}> Enter BOT token: *{Style.RESET_ALL}')
        TOKEN_FILE.write_text(token.strip(), encoding='utf-8')
        print(f'{Fore.YELLOW}> TOKEN CREATED{Style.RESET_ALL}')
    return TOKEN_FILE.read_text(encoding='utf-8').strip()


def main() -> int:
    """Entry point for both ``chibot`` and ``python -m scripts``."""
    os.chdir(ROOT)
    read_token()
    ensure_opus()
    configure_pydub()
    import scripts.chibot  # noqa: F401  — importing starts the bot.
    return 0
