from scripts import settings
import discord
from discord.ext import commands, tasks, voice_recv
from discord import app_commands
import asyncio
import wave
import os
import io
import numpy as np
from datetime import datetime

async def setup(bot: commands.Bot):
    print("Cog added - Common")
    await bot.add_cog(commands_common(bot))

class commands_common(commands.Cog):
    def __init__(self, bot: commands.Cog):
        self.bot = bot

    # STATUS ────────────────
    @app_commands.command(name="status", description = "-")
    async def status(self, ctx:discord.Interaction):
        print('─── STATUS ─── Application is up and running!')
        await ctx.respond('─── STATUS ─── Application is up and running!', delete_after=2)
        await ctx.response.send_message(settings.Localize("bot_status", "Test"), ephemeral=True, delete_after=2)

    # CLEAR ────────────────
    @app_commands.command(name="clear", description = "-")
    @app_commands.private_channel_only()
    async def clear(self, ctx:discord.Interaction):
        await ctx.response.send_message("Clear", ephemeral=True)
    
    # AVATAR ────────────────
    @app_commands.command(name="avatar", description = "-")
    @app_commands.private_channel_only()
    async def avatar(self, ctx:discord.Interaction):
        await ctx.response.send_message("Avatar", ephemeral=True)
    
    # FLIP ────────────────
    @app_commands.command(name="flip", description = "-")
    @app_commands.private_channel_only()
    async def flip(self, ctx:discord.Interaction):
        await ctx.response.send_message("Flip", ephemeral=True)

    # ROLL ────────────────
    @app_commands.command(name="roll", description = "-")
    @app_commands.private_channel_only()
    async def roll(self, ctx:discord.Interaction):
        await ctx.response.send_message("Roll", ephemeral=True)

    # ANON ────────────────
    @app_commands.command(name="anon", description = "-")
    @app_commands.private_channel_only()
    async def anon(self, ctx:discord.Interaction):
        await ctx.response.send_message("Anon", ephemeral=True)
        
    # REMINDME ────────────────
    @app_commands.command(name="remindme", description = "-")
    @app_commands.private_channel_only()
    async def remind_me(self, ctx:discord.Interaction):
        await ctx.response.send_message("Remind me", ephemeral=True)
        
    # ROULETTE ────────────────
    @app_commands.command(name="roulette", description = "-")
    @app_commands.private_channel_only()
    async def roulette(self, ctx:discord.Interaction):
        await ctx.response.send_message("Roulette", ephemeral=True)
        
    # PULL/BRING ────────────────
    @app_commands.command(name="pull", description = "-")
    @app_commands.private_channel_only()
    async def pull(self, ctx:discord.Interaction):
        await ctx.response.send_message("Pull", ephemeral=True)

    # PULL/BRING ────────────────
    @app_commands.command(name="record", description = "-")
    @app_commands.guild_only()
    async def record(self, ctx:discord.Interaction):
        if ctx.user.voice is None:
            await ctx.response.send_message(settings.Localize("require_connected"))
            return

        def callback(user: discord.User, data: voice_recv.VoiceData):
            if not recording:
                return
            if user not in user_buffers:
                user_buffers[user] = io.BytesIO()
            user_buffers[user].write(data.pcm)

        user_buffers = {}
        audio_buffer = io.BytesIO()
        recording = True
        
        await ctx.response.send_message(settings.Localize("started_recording", "sheeesh"), ephemeral=True)
        vc = await ctx.user.voice.channel.connect(cls=voice_recv.VoiceRecvClient)
        vc.listen(voice_recv.BasicSink(callback))

        # Wait for 5 seconds to collect audio.
        await asyncio.sleep(5)
        # Stop recording.
        vc.stop_listening()
        recording = False

        filename = f"rec_{ctx.guild_id}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.wav"
        all_audio = []
        max_length = 0
        for user, buffer in user_buffers.items():
            buffer.seek(0)
            pcm_data = np.frombuffer(buffer.read(), dtype=np.int16)
            all_audio.append(pcm_data)
            max_length = max(max_length, len(pcm_data))
            buffer.close()
        
        # Mix all users audio by avaraging the PCM values.
        if all_audio:
            # Pad all audio arrays to the max length with zeros (silence).
            padded_audio = [np.pad(audio, (0, max_length - len(audio)), mode='constant') for audio in all_audio]
            # Mix all users' audio by averaging the padded PCM values
            mixed_audio = np.mean(padded_audio, axis=0).astype(np.int16)
            new_bitrate = int (48000 * 0.75)
            with wave.open(f"./recs/{filename}", 'wb') as wav_file:
                wav_file.setnchannels(2) # Set as stereo
                wav_file.setsampwidth(2) # 2 bps (16-bit PCM) / Works as pitch.
                wav_file.setframerate(new_bitrate) # Bitrate
                wav_file.writeframes(mixed_audio.tobytes())
            audio_buffer.close()
            
            print(f"Audio saved as {filename}")
            discord_file = discord.File(f"./recs/{filename}")
            await ctx.delete_original_response()
            await ctx.channel.send("Recording complete. Audio saved on Desktop.", file=discord_file)
            
            os.remove(f"./recs/{filename}")
        else:
            await ctx.response.edit_message("Could not finish recording.")
        
