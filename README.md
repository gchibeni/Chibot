## ![Chibot](assets/chibot-featured.png)

###### A lightweight, self-hosted Discord bot built to run beautifully on a Raspberry Pi — multi-server, RAM-optimized, and packed with music, soundboards, custom triggers, and admin tooling.

> [!NOTE]
> **Chibot is a work in progress.** The core (voice, replay, admin, auth, fun commands) is up and running, but several features are still being built. See the [Roadmap](#construction-roadmap) for what's live and what's coming.

<br>

## :sparkles: Highlights

- **Runs anywhere** — Windows, macOS and Linux, designed around the constraints of a Raspberry Pi.
- **RAM optimized** — voice buffers are trimmed continuously and freed the moment the bot leaves a channel.
- **Multi-guild** — every server keeps its own isolated settings, assets and state.
- **Localized** — all user-facing text lives in `locale.json`, ready to be translated.
- **Highly customizable** — per-guild themes, authenticators and (soon) triggers and commands.

<br>

## :jigsaw: Features

### Voice & Audio

- **Rolling replay buffer** — Chibot continuously records the voice channel it's in, keeping the last **120 seconds** in memory. Use `/replay` to instantly clip the last few seconds of chaos.
- **Per-user mixing** — each speaker is buffered separately, silence-padded and overlaid, so replays stay perfectly in sync.
- **Pitch effects** — bend any replay from `0.0` (slow and deep) to `2.0` (fast and squeaky).
- **Audio playback** — stream from YouTube or any direct URL via `yt-dlp` + `ffmpeg`.
- **Downloads** — pull any supported video down as an `.mp3` with `/download`.
- **Smart auto-disconnect** — leaves on its own after being alone for 15 seconds, clearing its buffers.

### Messaging & Moderation

- **Message builder** — `/say` opens an interactive builder with embeds, attachments and a 15-minute editing session.
- **Anonymous messages** — `/anon` sends a message to a channel or straight to a user's DMs.
- **Protective purge** — `/purge` skips pinned messages and anything marked with :star:, and stops at the :triangular_flag_on_post: bookmark.

### Guild Themes

- **Calendar-driven server icons** — schedule icons by date and Chibot rotates the server avatar automatically.
- **Sleep icons** — pair an icon with a "sleeping" variant and wake/sleep hours, and the server avatar changes with the time of day.

### Authenticators

- **TOTP vault** — `/auth` stores 2FA authenticators per guild (or privately per user in DMs) and generates codes on demand, with a live expiration countdown.
- **Permission-gated** — only administrators can add or remove entries; everyone else can only read codes.

### Fun

- `/flip`, `/roll` and `/roulette` — interactive, re-rollable button views.

<br>

## :busts_in_silhouette: Commands

| Command | Scope | Description |
| :--- | :--- | :--- |
| `/replay` | Guild | Generate an audio replay from the connected voice channel |
| `/play` | Guild | Play audio from a search term or URL |
| `/download` | Guild | Download videos as `.mp3` files |
| `/say` | Guild | Build and send a message *(Manage Server)* |
| `/attach` | Guild | Attach files or images to a message or builder *(Manage Server)* |
| `/purge` | Guild | Purge messages, preserving pinned and starred ones *(Manage Messages)* |
| `/addicon` | Guild | Schedule a themed server icon *(Administrator)* |
| `/auth` | Anywhere | List and generate authenticator codes |
| `/anon` | Anywhere | Send an anonymous message |
| `/avatar` | Guild | Fetch a user's avatar |
| `/clear` | DM | Clear all received direct messages |
| `/status` | Anywhere | Show current bot status |
| `/flip` | Anywhere | Flip a coin |
| `/roll` | Anywhere | Roll a die |
| `/roulette` | Anywhere | Play a round of russian roulette |

Bot owners can also sync the command tree from any message:

```
!sync here          # Sync commands to the current guild
!sync here force    # Wipe and re-register the current guild's commands
!sync here clear    # Remove all commands from the current guild
!sync all           # Sync commands globally
```

<br>

## :hammer_and_wrench: Preparations

1. Install **Python 3.12 or above** on your system.
2. Make sure you have **APT**, **Homebrew** or **Chocolatey** available.
3. Create a Discord application on the [Discord Developer Portal](https://discord.com/developers/applications) and **save the bot token**.
4. Under **Bot → Privileged Gateway Intents**, enable **Message Content**, **Server Members** and **Presence**.
5. Invite the bot to your server with administrator privileges.
   > Give it the highest role in the server to unlock every feature — server icon rotation requires it.

<br>

## :package: Installation

Chibot runs on **Windows**, **macOS** and **Linux**.

**1.** Install the required system libraries using `apt-get`, `brew` or `choco`:

```bash
opus-tools
libopus0    # or "libopus" on macOS / Windows
ffmpeg
yt-dlp
```

**2.** Open a terminal in the project's root folder.

**3.** *(Optional but recommended)* Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
```

**4.** Install the project requirements:

```bash
pip install -r requirements.txt
```

<br>

## :rocket: Initialization

From the project's root folder, run:

```bash
python -m scripts
```

On the first run Chibot will ask for your Discord bot **token** and store it in `token.secret`. If you paste the wrong one, just open `token.secret` in any text editor, replace its contents, and run the command again.

Once the bot is online, send `!sync here` in your server to register the slash commands.

> [!IMPORTANT]
> `token.secret`, `settings.json` and `guilds/` are gitignored — they hold your bot token, TOTP secrets and per-guild assets. Never commit them.

<br>

## :file_folder: Project Structure

```
scripts/
├── __main__.py      # Entry point — token prompt and bootstrap
├── chibot.py        # Bot instance, intents and startup
├── events.py        # Gateway events, command sync, auto-disconnect
├── settings.py      # Config, localization, per-guild storage, icon rotation
├── voice.py         # Voice connection, replay buffers, playback, downloads
├── elements.py      # Reusable views, modals and buttons
└── cogs/
    ├── admin.py     # /say, /attach, /purge, /addicon
    ├── auth.py      # /auth — TOTP authenticator vault
    ├── common.py    # /status, /clear, /avatar, /anon, /replay, fun commands
    ├── musics.py    # /play, /download and music controls
    └── triggers.py  # Custom trigger messages (in progress)

locale.json          # All user-facing strings
settings.json        # Per-guild settings (gitignored)
guilds/              # Per-guild assets, e.g. icons (gitignored)
```

<br>

## :construction: Roadmap

**Working**

- [x] Voice replay buffer with pitch effects
- [x] Audio playback and `.mp3` downloads
- [x] Message builder, anonymous messages and protective purge
- [x] Scheduled server icon themes with sleep variants
- [x] TOTP authenticator vault
- [x] Fun commands and interactive views
- [x] Localization system

**In progress**

- [ ] Full music queue — `/skip`, `/pause`, `/stop` and shuffle
- [ ] Persistent music message with playback controls
- [ ] Custom trigger messages & responses
- [ ] Custom soundboard
- [ ] `/reminder`
- [ ] Dynamic per-guild custom commands

**Planned**

- [ ] Spotify playlist support
- [ ] `/theme` command to replace `/addicon`
- [ ] Additional locales
- [ ] AI-assisted responses

<br>

## :warning: A Note on Voice Recording

Chibot's replay feature keeps a rolling in-memory buffer of the voice channel it is connected to. Nothing is written to disk and the buffer is discarded the moment the bot disconnects — but anyone in the channel can clip the last two minutes. **Let your members know the bot records**, and check the laws that apply to you before deploying it.

<br>

#### NOW you are all set. Hope you enjoy!
