# Chibot
###### A custom discord bot with easy implementation.

### ─── Installation >

Execute the `start.bat` file, paste the token id if requested, after that, it will download all requirements and initialize the bot after 5 seconds.
Follow the instructions bellow if `start.bat` is not working.

On the main folder, create a `token.secret` file that contains only your bot token in the first line.
Install the requirements for the bot to work properly, running the following command:

```bash
pip install -r requirements.txt
```

Or install the requirements separetely:

```bash
pip install hikari==2.0.0.dev109
pip install hikari-lightbulb==2.2.4
pip install songbird-py==0.1.7
pip install urllib3==1.26.11
pip install yt-dlp==2022.7.18
```

### ─── Inicialization >

Execute the command bellow to initialize the bot:
```bash
python -m chibot
```