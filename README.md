# Chibot
###### A custom discord bot with easy implementation.

This bot was made with the idea to be extremely optmized to run on a Raspberry Pi.
- Runs on multiple servers
- RAM optimized
- Highly customizable

Relevant Features:
- Broadcasting & Anonymous messages
- Custom message soundboard
- Custom trigger messages & responses
- Musics from Youtube, Spotify or any URL
- Perfect music list & display
- Accessibility & Admin features
- AUTH CODES for guild features

### ─── Preparations :

1. Install Python3 or above on your system.
2. Make sure you have APT, Homebrew or Chocolatey installed.
3. Create a Discord application on Discord developer page (SAVE THE BOT TOKEN).
4. Add bot to the desired your server with admin privileges (Optional: Attribute it the highest server role to unlock all bot functionalities).
5. Optional: Create a Spotify application on Spotify developer page (Needed to unlock spotify functionalities, SAVE CLIENT ID & SECRET).

### ─── Installation :

Chibot is recommended for Windows / MacOS / Linux
1. Install required Libs by using "apt-get", "brew" or "choco":
```bash
opus-tools
libopus0 or libopus
ffmpeg
yt-dlp
```
2. Start a new command line (Terminal Command) and change the directory to the project's initial folder.
3. Optional: Start a virtual environment (Venv) on the project.
4. Install project requirements:
```bash
pip install -r requirements.txt
```
5. Bot should be ready.

### ─── Initialization :

On the project's initial folder, run the following command to initialize the BOT:
```bash
python -m scripts
```
It may ask you for the Discord bot TOKEN. You can find it in the Discord developer page.
If you entered the wrong one, don't worry. You can open the new file ('token.secret') created inside the bot folder as a text editor and paste your token there. Then run this command again and the bot will initialize.

After the bot is running to link the Spotify app, as the BOT OWNER you can use the command "/spotifyauth clientid:X clientsecret:Y".
#### NOW you are all set. Hope you enjoy!
