#!/usr/bin/env python3
import discord
from discord.ext import commands
import logging
import sys
import asyncio
import socket
import struct
from datetime import datetime, timedelta
from config import *

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
log = logging.getLogger(__name__)

class RCONClient:
    def __init__(self, host, port, password):
        self.host = host
        self.port = port
        self.password = password
        self.socket = None
    
    def connect(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10)
            self.socket.connect((self.host, self.port))
            
            packet_id = 1
            packet_type = 3
            body = self.password
            packet = struct.pack('<ii', packet_id, packet_type) + body.encode('utf-8') + b'\x00\x00'
            packet_len = len(packet)
            self.socket.send(struct.pack('<i', packet_len) + packet)
            
            len_data = self.socket.recv(4)
            if len(len_data) < 4:
                return False
            packet_len = struct.unpack('<i', len_data)[0]
            self.socket.recv(packet_len)
            
            log.info("RCON подключен")
            return True
        except Exception as e:
            log.error(f"RCON ошибка: {e}")
            return False
    
    def send_command(self, command):
        if not self.socket:
            if not self.connect():
                return None
        
        try:
            packet_id = 2
            packet_type = 2
            body = command
            packet = struct.pack('<ii', packet_id, packet_type) + body.encode('utf-8') + b'\x00\x00'
            packet_len = len(packet)
            self.socket.send(struct.pack('<i', packet_len) + packet)
            
            len_data = self.socket.recv(4)
            if len(len_data) < 4:
                return None
            packet_len = struct.unpack('<i', len_data)[0]
            response = self.socket.recv(packet_len)
            
            if len(response) > 8:
                return response[8:-2].decode('utf-8')
            return None
        except Exception as e:
            log.error(f"Ошибка RCON команды: {e}")
            return None
    
    def send_chat_message(self, message):
        message = message.replace('"', '\\"')
        command = f'say "{message}"'
        return self.send_command(command)

bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())
rcon = None

@bot.event
async def on_ready():
    global rcon
    
    # Подключаем RCON
    if RCON_PASSWORD:
        rcon = RCONClient(RCON_HOST, RCON_PORT, RCON_PASSWORD)
        await asyncio.get_event_loop().run_in_executor(None, rcon.connect)
    
    log.info("=" * 50)
    log.info(f"Бот {bot.user.name} запущен!")
    log.info(f"Сервер: {SERVER_NAME}")
    log.info(f"IP: {SERVER_IP}")
    log.info(f"RCON: {RCON_HOST}:{RCON_PORT}")
    log.info("=" * 50)
    
    await bot.change_presence(activity=discord.Game(name=f"x2 | {SERVER_IP}"))

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    if message.channel.id == GAME_CHAT_CHANNEL_ID:
        if not message.content.startswith('!'):
            # Отправляем в игру
            if rcon:
                game_msg = f"[DISCORD] {message.author.display_name}: {message.clean_content}"
                result = await asyncio.get_event_loop().run_in_executor(
                    None, rcon.send_chat_message, game_msg
                )
                if result is not None:
                    await message.add_reaction('✅')
                    log.info(f"В игру: {message.author.display_name}: {message.clean_content}")
                else:
                    await message.add_reaction('❌')
                    log.error(f"Не отправлено: {message.author.display_name}")
    
    await bot.process_commands(message)

# ========== КОМАНДЫ ==========

@bot.command(name='ip')
async def cmd_ip(ctx):
    await ctx.send(f"🎮 IP сервера: `{SERVER_IP}`")

@bot.command(name='info')
async def cmd_info(ctx):
    embed = discord.Embed(title=f"ℹ️ {SERVER_NAME}", color=discord.Color.gold())
    embed.add_field(name="IP", value=f"`{SERVER_IP}`")
    embed.add_field(name="Вайп", value="Каждый четверг в 12:00 МСК")
    await ctx.send(embed=embed)

@bot.command(name='wipe')
async def cmd_wipe(ctx):
    now = datetime.now()
    days = (3 - now.weekday()) % 7
    if days == 0 and now.hour >= 12:
        days = 7
    next_wipe = now + timedelta(days=days)
    next_wipe = next_wipe.replace(hour=12, minute=0)
    delta = next_wipe - now
    await ctx.send(f"💣 Следующий вайп: {next_wipe.strftime('%d.%m.%Y в 12:00')}\n⏳ Осталось: {delta.days} д. {delta.seconds//3600} ч.")

@bot.command(name='rcon')
async def cmd_rcon(ctx):
    if not rcon:
        await ctx.send("❌ RCON не настроен! Проверьте переменные окружения.")
        return
    
    await ctx.send("🔄 Проверка RCON...")
    result = await asyncio.get_event_loop().run_in_executor(
        None, rcon.send_command, "status"
    )
    
    if result:
        await ctx.send(f"✅ RCON работает!\n```{result[:300]}```")
    else:
        await ctx.send("❌ RCON не отвечает! Проверьте порт и пароль.")

@bot.command(name='help_bot')
async def cmd_help(ctx):
    embed = discord.Embed(title="🤖 Команды", color=discord.Color.blue())
    embed.add_field(name="!ip", value="IP сервера")
    embed.add_field(name="!info", value="Информация")
    embed.add_field(name="!wipe", value="Вайп")
    embed.add_field(name="!rcon", value="Проверка RCON")
    embed.add_field(name="!help_bot", value="Помощь")
    await ctx.send(embed=embed)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
