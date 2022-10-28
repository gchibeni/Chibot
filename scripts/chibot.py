import asyncio
import random
from turtle import update
import hikari
import lightbulb
import songbird
import urllib
import urllib.request
import re
import os
import json
import spotipy

from spotipy.oauth2 import SpotifyClientCredentials
from functools import partial
from songbird import ytdl, Queue
from songbird.hikari import Voicebox
from typing import Dict, List, Sequence
from html import unescape

from threading import Timer   


# Get and read bot token.
with open('./token.secret') as f:
    token = f.read().strip()

# Create bot instance.
bot = lightbulb.BotApp(token=token, prefix='/', intents=hikari.Intents.ALL)

# ─────────────── COMMON FUNCTIONS ───────────────

def update_guild_info(guild, key, value):
    # Common variables.
    data = {}; options = {}
    # Get filename and rewrite guild id so it does not duplicate.
    file = 'guilds.json'; guildid = f'{guild}'
    exists = os.path.isfile(f'./{file}')
    # Check if file exists.
    if exists:
        # Try getting existent info.
        with open(file, 'r+', encoding='utf-8') as f:
            try: data = json.load(f)
            except: data = {}
        # Checks if guild is in file and get complementary info.
        if guildid in data: options = data[guildid]
    # Create or update current data.
    options[key] = value
    data[guildid] = options
    jdata = json.dumps(data, indent=2)
    # Write json file.
    with open(file, 'w+', encoding='utf-8') as f: f.write(jdata)

def get_guild_info(guild, key):
    # Common variables.
    data = {}; options = {}
    # Get filename and rewrite guild id so it does not duplicate.
    file = 'guilds.json'; guildid = f'{guild}'
    exists = os.path.isfile(f'./{file}')
    # Check if file exists and get existent data.
    if exists:
        # Try getting existent info.
        with open(file, 'r+', encoding='utf-8') as f:
            try: data = json.load(f)
            except: data = {}
        # Checks if guild is in file, get and return complementary info.
        if guildid in data:
            options = data[guildid]
            if key in options: return options[key]
    # Return false if nothing is made. 
    return False



# ──────────────── MUSIC COMMANDS ────────────────

class uprompt:
    # Media user prompt class.
    def __init__(self, url, title, user):
        self.url : str = url
        self.title : str = title
        self.user : hikari.User = user

class infovb:
    # Voicebox information class.
    def __init__(self, voice, queue, reqs):
        self.voice : Voicebox = voice
        self.queue : Queue = queue
        self.reqs : List[uprompt] = reqs

guildvb : Dict[str, infovb] = {}

async def on_next(_, __, guild):
    # Check if there are any requests and removes the first one from playlist.
    if len(guildvb[guild].reqs) > 1:
        if len(guildvb[guild].queue) != 0: guildvb[guild].reqs.pop(0)
        await update_playlist(guild)
    # Check if there are any requests and add source to the queue.
    if len(guildvb[guild].reqs) > 1:
        source = await ytdl(guildvb[guild].reqs[1].url)
        guildvb[guild].queue.append(source)

async def on_end(_, __, guild):
    # If media ended playing and there is no more media on queueu try clearing the playlist.
    if len(guildvb[guild].queue) == 0: await clear_playlist(guild)

async def get_media(prompt):
    # Get media from Youtube based on the prompt.
    try:
        html = urllib.request.urlopen(f'https://www.youtube.com/results?search_query={urllib.parse.quote_plus(prompt)}')
        video_ids = re.findall(r'watch\?v=(\S{11})', html.read().decode())
        prompt : str = 'https://www.youtube.com/watch?v=' + video_ids[0]
        return prompt
    except:
        return False

async def get_media_title(url):
    # Get media title based on the url.
    # It download the whole music to get the title, but will be removed from ram memory once on playlist.
    # This method can take a little longer but its optimal for server resources.
    try:
        source = await ytdl(url)
        track, track_handle = await songbird.create_player(source)
        return track_handle.metadata.title
    except:
        return False

def get_youtube_title(url):
    params = {'format': 'json', 'url': '%s' % url}
    urljson = f'https://www.youtube.com/oembed?{urllib.parse.urlencode(params)}'
    with urllib.request.urlopen(urljson) as response:
        response_text = response.read()
        data = json.loads(response_text.decode())
        return data['title']

async def add_media_queue(guild, url, title, user):
    # Add media to playlist list.
    guildvb[guild].reqs.append(uprompt(url, title, user))
    # Checks if there is no more than two media on queue.
    if len(guildvb[guild].reqs) > 2: return
    # Add media from playlist to queue.
    source = await ytdl(url)
    guildvb[guild].queue.append(source)
    if len(guildvb[guild].queue) == 0: await update_playlist(guild)

async def clear_playlist(guild):
    guildvb[guild].queue.clear()
    guildvb[guild].reqs.clear()
    await update_playlist(guild)

async def update_playlist(guild):
    # Common variables.
    queuestr = ''; playing = ''; user : hikari.User
    musicmessage = get_guild_info(guild, 'music_message')
    # Checks if guild has music message.
    if not musicmessage: return
    messageid = musicmessage.split('/')
    # Check if guild requests is not null.
    if guildvb[guild].reqs:
        # Reverse playlist to be listed on message.
        for s, i in reversed(list(enumerate(guildvb[guild].reqs))):
            if (s != 0): queuestr += f'```#{s:02d} : {i.title}```'
            else: playing = f'\n──────── Playing ────────\n ```#{s:02d} : {i.title}```'; user = i.user
        # Create embeded message for when there is music playing.
        embeded = (hikari.Embed(description=f'{queuestr+playing}').set_footer(icon=user.avatar_url,text=f'Requested by ➜ {user.username} '))
    # Create embeded message for when there is no music playing.
    else: embeded = (hikari.Embed(description=f'\nPlaying ➜ ```#00 : No media playing . . .```').set_footer(icon=f'https://i.gifer.com/L7sU.gif',text='Requested by ➜ . . .'))
    # Try and edit message.
    try: await bot.rest.edit_message(channel=messageid[0],message=messageid[1],content=embeded)
    except: print(f'< Music <X>: Could not update playlist message.')

def get_spotify_playlist(url):
    spotifyauth = get_guild_info('bot_info', 'spotify_auth')
    if not spotifyauth: return
    auth = spotifyauth.split('/')
    # Authenticate in spotify app.
    client_credentials_manager = SpotifyClientCredentials(client_id=auth[0], client_secret=auth[1])
    # Create spotify session object.
    session = spotipy.Spotify(client_credentials_manager=client_credentials_manager)
    # Get uri from https link
    if match := re.match(r"https://open.spotify.com/playlist/(.*)\?", url): playlist_uri = match.groups()[0]
    else: return False
    # Get list of tracks in a given playlist
    try: tracks = session.playlist_items(playlist_uri,limit=100)["items"]
    except: return 'no_auth'
    playlist = []
    for track in tracks:
        name = track["track"]["name"]
        artist = track["track"]["artists"][0]['name']
        playlist.append(f'{name} - {artist}')
    return playlist

async def play_audio(guild, audio):
    source = await songbird.Source.ffmpeg(f'./audios/{audio}.mp3')
    await guildvb[guild].voice.play_source(source)

# PLAY ────────────────
@bot.command
@lightbulb.app_command_permissions(dm_enabled=False)
@lightbulb.option('prompt', 'Prompt of media to add to the queue', required=False, type=str)
@lightbulb.command('play', 'Play media and adds the prompt to the queue')
@lightbulb.implements(lightbulb.SlashCommand)
async def play(ctx: lightbulb.Context) -> None:
    # Common variables.
    prompt = ctx.options.prompt
    user = ctx.user
    guild = ctx.guild_id
    voicestate = ctx.get_guild().get_voice_state(user=user.id)
    # Check if user is in voice channel.
    if not voicestate: await ctx.respond(f'─── MUSIC ─── You are not in a voice channel.', flags=hikari.MessageFlag.EPHEMERAL); return
    channel = voicestate.channel_id
    # Check if bot is already in guild.
    if guild not in guildvb:
        # Add bot to current user channel.
        voice = await Voicebox.connect(client=bot, guild_id=guild, channel_id=channel)
        next = partial(on_next, guild=guild)
        queue = Queue(voice, on_next=next)
        end = partial(on_end, guild=guild)
        await voice.add_event(songbird.Event.End, end)
        # Add instance to guild class.
        guildvb[guild] = infovb(voice=voice, queue=queue, reqs=[])
    # Check again if bot is already in guild.
    if guild in guildvb:
        # Checks if user is in same channel as bot.
        if guildvb[guild].voice.channel_id != voicestate.channel_id: await ctx.respond(f'─── MUSIC ─── You must be in the same channel as the bot.', flags=hikari.MessageFlag.EPHEMERAL); return
        # If no prompt was added either resume media or tell user that bot joined the server.
        if prompt is None:
            if not guildvb[guild].queue.running:
                await ctx.respond(f'─── MUSIC ─── Joined channel.', flags=hikari.MessageFlag.EPHEMERAL)
            else:
                try: guildvb[guild].queue.track_handle.play(); await ctx.respond(f'─── MUSIC ─── Resumed media.', flags=hikari.MessageFlag.EPHEMERAL)
                except: await ctx.respond(f'─── MUSIC ─── No media to resume.', flags=hikari.MessageFlag.EPHEMERAL)
            return
        # Send fast response so bot does not glitch.
        await ctx.respond(f'─── MUSIC ─── Media is being added to queue . . .', flags=hikari.MessageFlag.EPHEMERAL)
        # Create count of all added media.
        mediacount : int = 0
        # Import all media from Spotify playlist.
        if prompt.startswith('https://open.spotify.com/playlist'):
            await ctx.edit_last_response(f'─── MUSIC ─── Spotify is currently disabled.'); return
            spotifyauth = get_guild_info('bot_info', 'spotify_auth')
            if not spotifyauth: await ctx.edit_last_response(f'─── MUSIC ─── Spotify is currently disabled. Use `/spotifyauth` to authenticate into a developer application so this function can be activated.'); return
            # Extract each item from spotify playlist.
            playlist = get_spotify_playlist(prompt)
            if playlist:
                if playlist == 'no_auth': await ctx.edit_last_response(f'─── MUSIC ─── Spotify authentification is invalid. Use `/spotifyauth` to update authenticator.'); return
                for music in playlist:
                    # Get media url and title.
                    media = await get_media(music)
                    title = get_youtube_title(media)
                    # Checks if media exists.
                    if media and title:
                        print(f'{media} - {title}')
                        # Add media to playlist list.
                        await add_media_queue(guild, media, title, user)
                        mediacount += 1
                await update_playlist(guild)
        # Import media from URL.
        elif prompt.startswith('http://') or prompt.startswith('https://'):
            # Get media url and title.
            media = prompt
            if '.youtube.com/' in prompt: title = get_youtube_title(media)
            else: title = await get_media_title(prompt)
            # Checks if media exists.
            if media and title:
                # Add media to playlist list.
                await add_media_queue(guild, media, title, user)
                mediacount += 1
        # Import media from Youtube.
        else:
            # Get media url and title.
            media = await get_media(prompt)
            title = get_youtube_title(media)
            # Checks if media exists.
            if media and title:
                # Add media to playlist list.
                await add_media_queue(guild, media, title, user)
                mediacount += 1
        # Checks if media was able to be added.
        if mediacount == 0: await ctx.edit_last_response(f'─── MUSIC ─── Media could not be found or added.'); return
        # Add new media list to media queue.
        await ctx.edit_last_response(f'─── MUSIC ─── Media added to the queue.')
        print(f'< Music ||| {user.username} <X>: Finished downloading media.')

# SKIP ────────────────
@bot.command
@lightbulb.app_command_permissions(dm_enabled=False)
@lightbulb.command('skip', 'Skips the current music')
@lightbulb.implements(lightbulb.SlashCommand)
async def skip(ctx: lightbulb.Context) -> None:
    # Common variables.
    guild = ctx.guild_id
    # Try to skip.
    try: guildvb[guild].queue.skip(); await ctx.respond(f'─── MUSIC ─── Skipped media.', flags=hikari.MessageFlag.EPHEMERAL)
    except: await ctx.respond(f'─── MUSIC ─── No media to skip.', flags=hikari.MessageFlag.EPHEMERAL)
    if len(guildvb[guild].queue) == 0: await clear_playlist(guild)

# PAUSE ───────────────
@bot.command
@lightbulb.app_command_permissions(dm_enabled=False)
@lightbulb.command('pause', 'Pause the current media playing')
@lightbulb.implements(lightbulb.SlashCommand)
async def pause(ctx: lightbulb.Context) -> None:
    # Common variables.
    guild = ctx.guild_id
    # Try to pause.
    try: guildvb[guild].queue.track_handle.pause(); await ctx.respond(f'─── MUSIC ─── Paused media.', flags=hikari.MessageFlag.EPHEMERAL)
    except: await ctx.respond(f'─── MUSIC ─── No media to pause.', flags=hikari.MessageFlag.EPHEMERAL)

# STOP ────────────────
@bot.command
@lightbulb.app_command_permissions(dm_enabled=False)
@lightbulb.command('stop', 'Stops all media playing and force the bot to leave')
@lightbulb.implements(lightbulb.SlashCommand)
async def stop(ctx: lightbulb.Context) -> None:
    # Common variables.
    guild = ctx.guild_id
    # Check if bot is in guild.
    if guild not in guildvb: await ctx.respond(f'─── MUSIC ─── Bot is not connected.', flags=hikari.MessageFlag.EPHEMERAL); return
    # Disconnect bot and remove guild from guildvb.
    await clear_playlist(guild); await guildvb[guild].voice.disconnect(); del guildvb[guild]
    # Clear all media from playlist.
    await ctx.respond(f'─── MUSIC ─── Bot stopped.', flags=hikari.MessageFlag.EPHEMERAL)

# SET MUSIC MESSAGE ───
@bot.command
@lightbulb.app_command_permissions(dm_enabled=False)
@lightbulb.command('musicmessage', 'Create music message to show playlist queue.')
@lightbulb.implements(lightbulb.SlashCommand)
async def musicmsg(ctx: lightbulb.Context) -> None:
    # Common variables.
    guild = ctx.guild_id
    channel = ctx.get_channel()
    # Create music message.
    embeded = (hikari.Embed(description=f'──────── Playing ────────\n```#00 : Use /play to add media to playlist.```').set_footer(icon=f'https://i.gifer.com/L7sU.gif',text=f'Requested by ➜ . . .'))
    message = await bot.rest.create_message(channel=channel,content=embeded)
    await ctx.respond(f'─── MUSIC ─── Music message created.', delete_after=0)
    # Update guild info.
    update_guild_info(guild, 'music_message', f'{channel.id}/{message.id}')

# SPOTIFY AUTH ────────
@bot.command
@lightbulb.app_command_permissions(dm_enabled=False)
@lightbulb.option('clientsecret', 'Spotify application client secret', required=True, type=str)
@lightbulb.option('clientid', 'Spotify application client id', required=True, type=str)
@lightbulb.command('spotifyauth', 'Authenticate into a spotify application so bot can work with spotify')
@lightbulb.implements(lightbulb.SlashCommand)
async def spotifyauth(ctx: lightbulb.Context) -> None:
    # Common variables.
    guild = ctx.guild_id
    clientid = ctx.options.clientid
    clientsecret = ctx.options.clientsecret
    auth = f'{clientid}/{clientsecret}'
    # Update spotify auth.
    update_guild_info('bot_info', 'spotify_auth', auth)
    await ctx.respond(f'─── MUSIC ─── Spotify authenticator updated.', flags=hikari.MessageFlag.EPHEMERAL)





# ──────────────── COMMON COMMANDS ───────────────

# STATUS ──────────────
@bot.command
@lightbulb.app_command_permissions(dm_enabled=False)
@lightbulb.command('status', 'Check bot status')
@lightbulb.implements(lightbulb.SlashCommand)
async def status(ctx: lightbulb.Context) -> None:
    guild = ctx.guild_id
    if guild in guildvb:
        for i in guildvb[guild].reqs:
            print(f'{i.title} --- {i.url} --- {i.user}')
        
    # Quick command to check bot status and lag.
    print('─── STATUS ─── Application is up and running!')
    await ctx.respond('─── STATUS ─── Application is up and running!', delete_after=2)

# AVATAR ──────────────
@bot.command
@lightbulb.app_command_permissions(dm_enabled=False)
@lightbulb.option('user', 'Targeted user to steal their avatar', required=True, type=hikari.User)
@lightbulb.command('avatar', 'Fetch the avatar url of any user in the server')
@lightbulb.implements(lightbulb.SlashCommand)
async def avatar(ctx: lightbulb.Context) -> None:
    # Common variables.
    user = ctx.options.user
    fetchuser : hikari.User = await bot.rest.fetch_user(user=user)
    avatar = fetchuser.avatar_url
    # Create embeded and return user avatar.
    embeded = (hikari.Embed(description=f'─── AVATAR ─── \nFetched {fetchuser.mention} avatar:').set_image(avatar))
    await ctx.respond(embeded, flags=hikari.MessageFlag.EPHEMERAL)

# FLIP ────────────────
@bot.command
@lightbulb.command('flip', 'Flip a coin')
@lightbulb.implements(lightbulb.SlashCommand)
async def flip(ctx: lightbulb.Context) -> None:
    # Common variables.
    flipped = random.randint(0, 1)
    # Flip coin.
    if flipped == 0: await ctx.respond(f'─── FLIP ─── Flipped ➜ :heads:')
    else: await ctx.respond(f'─── FLIP ─── Flipped ➜ :tails:')

# ROLL ────────────────
@bot.command
@lightbulb.option('number', 'Rolls to this number', min_value=2, required=False, type=int)
@lightbulb.command('roll', 'Rolls D20 or a random number between 0 and specified number')
@lightbulb.implements(lightbulb.SlashCommand)
async def roll(ctx: lightbulb.Context) -> None:
    # Common variables.
    end = 20
    # Check custom max number.
    if ctx.options.number: end = ctx.options.number
    # Roll die.
    rolled = random.randint(1, end)
    await ctx.respond(f'─── ROLL D{end} ─── Rolled ➜ {rolled}')

# SECRET ROLL ─────────
@bot.command
@lightbulb.app_command_permissions(dm_enabled=False)
@lightbulb.option('number', 'Rolls to this number', min_value=2, required=False, type=int)
@lightbulb.command('sroll', 'Secretly rolls D20 or a random number between 0 and specified number')
@lightbulb.implements(lightbulb.SlashCommand)
async def sroll(ctx: lightbulb.Context) -> None:
    # Common variables.
    end = 20
    # Check custom max number.
    if ctx.options.number: end = ctx.options.number
    # Roll die secretly.
    rolled = random.randint(1, end); await ctx.respond(f'─── ROLL D{end} ─── Rolled ➜ {rolled}', flags=hikari.MessageFlag.EPHEMERAL)

# SAY ─────────────────
@bot.command
@lightbulb.app_command_permissions(dm_enabled=False, perms=hikari.Permissions.MANAGE_MESSAGES)
@lightbulb.option('message', 'Message to be said by the bot', required=True)
@lightbulb.option('att', 'Attached files or images', required=False, type=hikari.OptionType.ATTACHMENT)
@lightbulb.command('say', 'Force the bot to send the specified message')
@lightbulb.implements(lightbulb.SlashCommand)
async def say(ctx: lightbulb.Context) -> None:
    # Common variables.
    channel = ctx.get_channel()
    msg = ctx.options.message
    att : hikari.Attachment = ctx.options.att
    # Send response so it does not glitch.
    await ctx.respond(f'─── SAY ─── Message Sent ➜', flags=hikari.MessageFlag.EPHEMERAL)
    # Check if message has attachment.
    if att is not None:
        # Send message with attachment.
        a = (hikari.Attachment(filename=att.filename,height=att.height,id=att.id,is_ephemeral=att.is_ephemeral,media_type=att.media_type,proxy_url=att.proxy_url,size=att.size,url=att.url,width=att.width))
        await bot.rest.create_message(channel=channel,content=msg,attachment=a)
        # Send message without attachment.
    else: await bot.rest.create_message(channel=channel,content=msg)

# ANON ────────────────
@bot.command
@lightbulb.app_command_permissions(dm_enabled=False)
@lightbulb.option('message', 'Message to be sent anonymously', required=True)
@lightbulb.option('user', 'Targeted user to force into channel', required=False, type=hikari.User)
@lightbulb.command('anon', 'Send an anonymous message to the channel')
@lightbulb.implements(lightbulb.SlashCommand)
async def anon(ctx: lightbulb.Context) -> None:
    # Common variables.
    channel = ctx.get_channel()
    msg = ctx.options.message
    user = ctx.options.user
    guildname = ctx.get_guild().name
    guildicon = ctx.get_guild().icon_url
    # Check if no user was targetted.
    if user is None:
        # Send anonymous message on server. 
        await ctx.respond(f'─── ANON ─── Message Sent ➜', flags=hikari.MessageFlag.EPHEMERAL)
        embeded = (hikari.Embed(description=f'{msg}').set_footer(icon=f'https://i.gifer.com/L7sU.gif',text='➜ Sent anonymously'))
        await bot.rest.create_message(channel, embeded)
    else:
        # Send anonymous message to targeted user direct message. 
        await ctx.respond(f'─── ANON ─── Direct Message Sent ➜ <@{user.id}>', flags=hikari.MessageFlag.EPHEMERAL)
        embeded = (hikari.Embed(description=f'{msg}').set_footer(icon=f'{guildicon}',text=f'From: {guildname} ➜ Sent anonymously'))
        u : hikari.User = await bot.rest.fetch_user(user)
        await u.send(embeded)

# PURGE ───────────────
@bot.command
@lightbulb.app_command_permissions(dm_enabled=False, perms=hikari.Permissions.MANAGE_MESSAGES)
@lightbulb.option('quantity', 'Quantity of messages to be purged', required=True, type=int)
@lightbulb.option('force', 'Force delete past marked messages', required=False, type=bool)
@lightbulb.command('purge', 'Delete in order the quantity specified of messages in the channel')
@lightbulb.implements(lightbulb.SlashCommand)
async def purge(ctx: lightbulb.Context) -> None:
    # Common variables.
    channel = ctx.get_channel()
    quantity = ctx.options.quantity
    force = ctx.options.force
    # Send message first so it does not take too long to process.
    await ctx.respond(f'─── PURGE ─── \n> - Purging {quantity} messages . . .')
    # Message variables and groups.
    allmsgs = ( await bot.rest.fetch_messages(channel).limit(quantity + 1) )
    delmsgs : Sequence[hikari.Message] = []
    # Check every message.
    for m in allmsgs:
        # Check if message is saved or marked.
        Saved = False; Marked = False
        for r in m.reactions:
            if ('⭐' in r.emoji.name) or ('🍞' in r.emoji.name): Saved = True
            if ('🚩' in r.emoji.name) and not force: Marked = True
        # Check if message is not pinned saved or marked.
        if not m.is_pinned and not Saved and not Marked: delmsgs.append(m)
        # Check if message is marked and break the loop.
        elif Marked: break
    # Delete messages.
    await bot.rest.delete_messages(channel.id, delmsgs)

# SET BRING CHANNEL ───
@bot.command
@lightbulb.app_command_permissions(dm_enabled=False)
@lightbulb.command('setbring', 'Set server /bring channel to current connected one')
@lightbulb.implements(lightbulb.SlashCommand)
async def setbring(ctx: lightbulb.Context) -> None:
    # Common variables.
    guild = ctx.guild_id
    user = ctx.user
    voicestate = ctx.get_guild().get_voice_state(user=user.id)
    # Checks if user is connected to voice channel.
    if not voicestate: await ctx.respond(f'─── BRING ─── You must be connected to a voice channel.', flags=hikari.MessageFlag.EPHEMERAL); return
    await ctx.respond(f'─── BRING ─── Bring channel selected.', flags=hikari.MessageFlag.EPHEMERAL)
    # Update guild info.
    update_guild_info(guild, 'bring_channel', f'{voicestate.channel_id}')

# BRING ───────────────
@bot.command
@lightbulb.app_command_permissions(dm_enabled=False)
@lightbulb.option('user', 'Targeted user to force into channel', required=True, type=hikari.User)
@lightbulb.command('bring', 'Force move user to the current voice channel')
@lightbulb.implements(lightbulb.SlashCommand)
async def bring(ctx: lightbulb.Context) -> None:
    # Common variables.
    guild = ctx.guild_id
    user = ctx.user
    bringuser = ctx.options.user
    bringstate = ctx.get_guild().get_voice_state(user=bringuser)
    voicestate = ctx.get_guild().get_voice_state(user=user.id)
    # Rewrite channel it does not glitch.
    channelid = f'{voicestate.channel_id}'
    bringchannel = get_guild_info(guild, 'bring_channel')
    # Check if bring channel exists.
    if not bringchannel: await ctx.respond(f'─── BRING ─── Bring voice channel not set. Use `/setbring` to set one up.', flags=hikari.MessageFlag.EPHEMERAL); return
    # Checks if target user is connected to any voice channel.
    if not bringstate: await ctx.respond(f'─── BRING ─── Targeted user is not connected to any voice chat.', flags=hikari.MessageFlag.EPHEMERAL); return
    # Checks if user is connected to bring channel.
    if channelid != bringchannel: await ctx.respond(f'─── BRING ─── You are not connected to the bring channel.', flags=hikari.MessageFlag.EPHEMERAL); return
    # Bring selected user to voice channel.
    try:
        await bot.rest.edit_member(guild=voicestate.guild_id, user=bringuser, voice_channel=voicestate.channel_id)
        await ctx.respond(f'─── BRING ─── User was moved to the channel.', flags=hikari.MessageFlag.EPHEMERAL)
    except:
        await ctx.respond(f'─── BRING ─── Could not bring user to channel.', flags=hikari.MessageFlag.EPHEMERAL)

# ROULETTE ────────────
@bot.command
@lightbulb.app_command_permissions(dm_enabled=False)
@lightbulb.command('roulette', 'Russian roulette. 1/6 chances of being punished')
@lightbulb.implements(lightbulb.SlashCommand)
async def roullete(ctx: lightbulb.Context) -> None:
    # Common variables.
    rand = random.randint(1,6)
    user = ctx.user
    # Checks bad luck.
    if rand == 6:
        # Change user name and try to disconnect user from voice channel.
        await ctx.respond(f'─── ROULETTE ─── DEAD! You were shot and was punished.', flags=hikari.MessageFlag.EPHEMERAL)
        voicestate = ctx.get_guild().get_voice_state(user=user.id)
        if voicestate: await voicestate.member.edit(voice_channel=None)
        await ctx.member.edit(nickname='> DUMB <')
    else:
        await ctx.respond(f'─── ROULETTE ─── Nothing happend! You are safe, for now . . .', flags=hikari.MessageFlag.EPHEMERAL)

# CLEAR DM ────────────
@bot.command
@lightbulb.command('cleardm', 'Clear all bot messages in dm', guilds=None)
@lightbulb.implements(lightbulb.PrefixCommand)
async def cleardm(ctx: lightbulb.Context) -> None:
    # Common variables.
    ch = await ctx.user.fetch_dm_channel()
    msgs = await bot.rest.fetch_messages(channel=ch)
    # Check each message and delete them.
    for m in msgs:
        try: await bot.rest.delete_message(ch,m.id)
        except: continue

# CREATE RESPONSES ────
@bot.command
@lightbulb.app_command_permissions(dm_enabled=False)
@lightbulb.option('responses', 'List of all responses. {| = separator},{<@u> = user mention}', required=True, type=str)
@lightbulb.option('triggers', 'List of all triggers. {| = separator},{any:* = req anywhere},{sec:* = req anywhere},{* = equal}', required=True, type=str)
@lightbulb.command('settriggers', 'Creates text triggers that will send a random set response')
@lightbulb.implements(lightbulb.SlashCommand)
async def settriggers(ctx: lightbulb.Context) -> None:
    # Common variables.
    guild = ctx.guild_id
    triggers = ctx.options.triggers
    responses = ctx.options.responses
    custom = {}
    # Get and maintain any text triggers.
    texttriggers = get_guild_info(guild,'text_triggers')
    if texttriggers: custom = texttriggers
    # Create new text triggers and responses.
    custom[triggers] = responses
    update_guild_info(guild, 'text_triggers', custom)
    await ctx.respond(f'─── TRIGGERS ─── Text triggers created.', flags=hikari.MessageFlag.EPHEMERAL)

# LIST RESPONSES ──────
@bot.command
@lightbulb.app_command_permissions(dm_enabled=False)
@lightbulb.command('listtriggers', 'Lists all text triggers')
@lightbulb.implements(lightbulb.SlashCommand)
async def listtriggers(ctx: lightbulb.Context) -> None:
    # Common variables.
    guild = ctx.guild_id
    queuestr = ''; count : int = 0
    texttriggers = get_guild_info(guild,'text_triggers')
    if not texttriggers: await ctx.respond(f'─── TRIGGERS ─── No triggers to list.', flags=hikari.MessageFlag.EPHEMERAL); return
    # List all triggers.
    for i in texttriggers:
        triggers = i.replace('|', ' | ')[0:100]; responses = texttriggers[i].replace('|', ' | ')[0:100]
        queuestr += f'\n```#{count:02d} : ──────────\n\n─── TRIGGERS ───\n> [ {triggers} ] . . .\n─── RESPONSES ──\n> [ {responses} ]  . . .```'; count += 1
    # Create and send embeded.
    embeded = (hikari.Embed(description=f'{queuestr}').set_footer(text=f'Trigger list and indexes'))
    await ctx.respond(content=embeded, flags=hikari.MessageFlag.EPHEMERAL)

# DELETE RESPONSES ────
@bot.command
@lightbulb.app_command_permissions(dm_enabled=False)
@lightbulb.option('triggerid', 'ID of specific trigger', required=True, min_value=0, type=int)
@lightbulb.command('deltriggers', 'Delete specific trigger based on ID')
@lightbulb.implements(lightbulb.SlashCommand)
async def deltriggers(ctx: lightbulb.Context) -> None:
    # Common variables.
    guild = ctx.guild_id
    triggerid : int = ctx.options.triggerid
    # 
    texttriggers = get_guild_info(guild,'text_triggers')
    if not texttriggers: await ctx.respond(f'─── TRIGGERS ─── No triggers to delete.', flags=hikari.MessageFlag.EPHEMERAL); return
    if triggerid >= len(texttriggers): await ctx.respond(f'─── TRIGGERS ─── Trigger id not existent.', flags=hikari.MessageFlag.EPHEMERAL); return
    for s, i in list(enumerate(texttriggers)):
        if s == triggerid: del texttriggers[i]
    update_guild_info(guild, 'text_triggers', texttriggers)
    await ctx.respond(f'─── TRIGGERS ─── Text trigger deleted.', flags=hikari.MessageFlag.EPHEMERAL)








#def Register(cmd : str, desc : str, func, kek):
#    @bot.command
#    @lightbulb.app_command_permissions(dm_enabled=False)
#    @lightbulb.command(cmd, desc)
#    @lightbulb.implements(lightbulb.SlashCommand)
#    async def cmd(ctx: lightbulb.Context) -> None:
#        await func(ctx)
#
#def UnregisterPrefix(cmd : str):
#    bot.remove_command(bot.get_prefix_command(cmd))

# LISTENERS ────────────


@bot.listen(hikari.VoiceStateUpdateEvent)
async def bot_disconnect(event : hikari.VoiceStateUpdateEvent):
    guild = event.guild_id
    botuser = await bot.rest.fetch_my_user()
    # Checks if the bot is alone in a channel and disconnects him
    if guild in guildvb:
        voicebox = guildvb[guild].voice
        states = bot.cache.get_voice_states_view_for_channel(guild,voicebox.channel_id)
        # Checks if there are no users in channel.
        if (len(states) == 1):
            # Wait 10 seconds before disconnecting.
            await asyncio.sleep(10)
            states = bot.cache.get_voice_states_view_for_channel(guild,voicebox.channel_id)
            # Checks again if there is still no users in channel.
            if (len(states) == 1):
                # Disconnect bot and remove guild from guildvb.
                voice = guildvb[guild].voice
                await clear_playlist(guild); del guildvb[guild]; await voice.disconnect(); 
    #if event.state.user_id == botuser.id:
        #if guild in guildvb:
            # Disconnect bot and remove guild from guildvb.
            #voice = guildvb[guild].voice
            #await clear_playlist(guild); del guildvb[guild]; await voice.disconnect(); 

@bot.listen(hikari.GuildMessageCreateEvent)
async def on_message(message : hikari.GuildMessageCreateEvent):
    # Common variables.
    content = message.content
    author = message.author
    guild = message.get_guild()
    channel = guild.get_channel(channel=message.channel_id)
    # Check if author is any bot.
    if author.is_bot: return

    # Get current responses on guild:
    texttriggers = get_guild_info(guild.id, 'text_triggers')
    if texttriggers and content:
        for trigger in texttriggers:
            # Common variables.
            complete = []; words1 = []; words2 = []; resps = []
            # Get triggers and responses.
            triggers = trigger.split('|')
            responses = texttriggers[trigger].split('|')
            # Get trigger type.
            for word in triggers:
                if word.startswith('any:'): words1.append(word.removeprefix('any:'))
                elif word.startswith('sec:'): words2.append(word.removeprefix('sec:'))
                else: complete.append(word)
            # Replace placed variables on response to real variables.
            for resp in responses:
                resps.append(resp.replace('<@u>', author.mention))
            # Variables to check if triggers are in the message.
            cany = any(x in content.lower() for x in words1)
            csec = any(x in content.lower() for x in words2)
            ccomp = any(x == content.lower() for x in complete)
            # Check combination to see if its possible.
            if (cany and not words2) or (cany and csec and words1 and words2) or ccomp:
                # Randomly send final response message.
                finalresp = random.choice(resps)
                await bot.rest.create_message(channel, f'{finalresp}')

    # Print user action and messages for debugging purposes.
    if not content: content = '── EMPTY MESSAGE or EMBEDED MESSAGE ── ]]]'
    print(f'⎾ {guild.name} ||| {channel} ⏋ ⤵')
    print(f'< {author.id} ||| {author.username}> <M>: {content}')

@bot.listen(lightbulb.SlashCommandInvocationEvent)
async def on_slashcommand(invoc : lightbulb.SlashCommandInvocationEvent):
    # Common variables.
    author = invoc.context.author
    command = invoc.command.name
    # Send message to console for debugging reasons.
    try:
        guild = invoc.context.get_guild()
        channel = guild.get_channel(channel=invoc.context.channel_id)
        if command != "anon":
            print(f'⎾ {guild.name} ||| {channel.name} ⏋ ⤵')
            print(f'< {author.id} ||| {author.username}> <C>: Used {command} < < < <')
    except: return

"""
@bot.listen(lightbulb.PrefixCommandErrorEvent)
async def on_error(event: lightbulb.PrefixCommandErrorEvent) -> None: return
@bot.listen(lightbulb.SlashCommandErrorEvent)
async def on_error(event: lightbulb.SlashCommandErrorEvent) -> None:
    exception = event.exception.__cause__ or event.exception
    resp = "─── ERROR! ───"
    if isinstance(exception, lightbulb.CommandIsOnCooldown): resp = f"─── Command Cooldown! ─── Retry in `{exception.retry_after:.2f}` seconds."
    elif isinstance(exception, lightbulb.MissingRequiredPermission): resp = f"─── Missing Permissions! ─── You don't have permission to execute this command."
    elif isinstance(exception, lightbulb.MissingRequiredRole): resp = f"─── Missing Role! ─── You don't have permission to execute this command."
    elif isinstance(exception, lightbulb.MissingRequiredAttachment): resp = f"─── Missing Attachment! ─── Attachment must come with execution of command."
    elif isinstance(exception, lightbulb.CommandInvocationError): resp = f"─── Error! ─── Command could not execute."
    elif isinstance(exception, lightbulb.NotEnoughArguments): resp = f"─── Missing Arguments! ─── Command is expected to have more arguments."
    else: resp = f"─── Error! ─── Command could not execute."
    await event.context.respond(resp, flags=hikari.MessageFlag.EPHEMERAL)
"""


#secs = 15
#def update_servers():
#    print('Updated servers!')
#    t = Timer(secs, update_servers)
#    t.start()
#update_servers()




# START ───────────────
@bot.listen(hikari.StartedEvent)
async def bot_started(event : hikari.StartedEvent) -> None:
    print(f'─── STATUS ─── Application is up and running!')

_activity = hikari.Activity(name='────────', type=hikari.ActivityType.PLAYING)
bot.run(check_for_updates=True, activity=_activity)