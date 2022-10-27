# Chibot
###### A custom discord bot with easy implementation.

This bot was made with the idea to be optmized to run on a raspberry pi, without any problems of downloaded media overflowing ram memory, whilist being used on multiple servers, it is also highly customizable. Its not perfect but it works and im happy with it. Hope you like it.

### ─── Installation >

If you are a newbie start by downloading and installing python on your system. I recommend that you watch a video on how to do so before proceeding on this readme file, this way you can be more interated on whats happening here.

You should create a discord application on the discord developer page, add it to your server with the administrator privilages and put it on the highest server role (Only if you want the bot to work with all its functionalities).

This bot uses hikari, hikari-lightbulb and songbird-py, and may require some tools instalations on your system.
Them being: "opus-tools", "libopus0", "ffmpeg", "youtube-dl" restart the system after installing them so it does not glitch.

Here is how you can install them on a raspberry pi
```bash
sudo apt-get install opus-tools
sudo apt-get install libopus0
sudo apt-get install ffmpeg
sudo apt-get install youtube-dl
```

Start a new command line (Terminal Command) and change the directory to the bot initial folder.
Then run the following command to install all requirements:
```bash
pip install -r requirements.txt
```

### ─── Inicialization >

With the same command line use the commad bellow to initialize the bot:
```bash
python -m chibot
```
It may ask you for the bot token. You can find it in the discord developer page, just get your application token.
If you entered the wrong one, don't worry. You can open the new file ('token.secret') created inside the bot folder as a text editor and paste your token there. Then run this command again and the bot will initialize.
