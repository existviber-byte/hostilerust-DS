#!/usr/bin/env python3
import discord
from discord.ext import commands, tasks
import asyncio
import json
import logging
import os
import socket
import struct
import re
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
ADMIN_ROLE_ID = int(os.getenv('ADMIN_ROLE_ID', 0))
WIPE_CHANNEL_ID = int(os.getenv('WIPE_CHANNEL_ID', 0))
RUST_SERVER_IP = os.getenv('RUST_SERVER_IP', '37.230.137.6')
RUST_SERVER_PORT = int(os.getenv('RUST_SERVER_PORT', 20602))
RUST_SERVER_PASSWORD = os.getenv('RUST_SERVER_PASSWORD', '')
RUST_SERVER_NAME = os.getenv('RUST_SERVER_NAME', 'HOSTILE RUST | x2 | SOLO/DUO')

FIRST_WIPE_DATE = datetime(2026, 6, 18, 12, 0, 0)
WIPE_INTERVAL_DAYS = 14

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
log = logging.getLogger(__name__)

# ========== RCON ==========
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
        if not self.socket and not self.connect():
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
            log.error(f"RCON ошибка: {e}")
            return None
    
    def get_status(self):
        result = self.send_command("status")
        if not result:
            return {'online': 0, 'sleeping': 0}
        online = 0
        sleeping = 0
        for line in result.split('\n'):
            nums = re.findall(r'\d+', line)
            if 'connected' in line.lower() and nums:
                online = int(nums[0]) if nums else 0
            if 'sleeping' in line.lower() and nums:
                sleeping = int(nums[0]) if nums else 0
        return {'online': online, 'sleeping': sleeping}

# ========== ЗАМЕТКИ ==========
class NotesManager:
    def __init__(self):
        self.file = Path("data/notes.json")
        self.notes = {}
        self.load()
    
    def load(self):
        if self.file.exists():
            try:
                with open(self.file, 'r') as f:
                    self.notes = json.load(f)
            except:
                self.notes = {}
        else:
            self.file.parent.mkdir(exist_ok=True)
            self.save()
    
    def save(self):
        with open(self.file, 'w') as f:
            json.dump(self.notes, f, indent=2)
    
    def create(self, user_id, title, content):
        if user_id not in self.notes:
            self.notes[user_id] = []
        note_id = len(self.notes[user_id]) + 1
        self.notes[user_id].append({'id': note_id, 'title': title, 'content': content})
        self.save()
        return note_id
    
    def get(self, user_id):
        return self.notes.get(user_id, [])
    
    def delete(self, user_id, note_id):
        notes = self.notes.get(user_id, [])
        for i, n in enumerate(notes):
            if n['id'] == note_id:
                notes.pop(i)
                for j, nn in enumerate(notes):
                    nn['id'] = j + 1
                self.save()
                return True
        return False

# ========== ВАЙП ==========
def get_wipe():
    now = datetime.now()
    if now < FIRST_WIPE_DATE:
        next_wipe = FIRST_WIPE_DATE
    else:
        days = (now - FIRST_WIPE_DATE).days
        cycles = days // WIPE_INTERVAL_DAYS
        next_wipe = FIRST_WIPE_DATE + timedelta(days=WIPE_INTERVAL_DAYS * (cycles + 1))
    
    if next_wipe.day <= 7 and next_wipe.weekday() == 3:
        next_wipe = next_wipe.replace(hour=22, minute=0)
    else:
        next_wipe = next_wipe.replace(hour=12, minute=0)
    
    delta = next_wipe - now
    return {
        'date': next_wipe.strftime('%d.%m.%Y'),
        'time': '22:00 МСК' if next_wipe.hour == 22 else '12:00 МСК',
        'days': delta.days,
        'hours': delta.seconds // 3600,
        'minutes': (delta.seconds % 3600) // 60,
        'wipe_number': ((next_wipe - FIRST_WIPE_DATE).days // WIPE_INTERVAL_DAYS) + 1
    }

# ========== БОТ ==========
bot = commands.Bot(command_prefix='!', intents=discord.Intents.all())
notes = NotesManager()
rcon = None
server_status = {'online': 0, 'sleeping': 0}
wipe_channel = None

@bot.event
async def on_ready():
    global rcon, wipe_channel
    log.info("=" * 50)
    log.info(f"✅ Админ бот {bot.user.name} запущен!")
    log.info(f"🎮 Сервер: {RUST_SERVER_NAME}")
    log.info("=" * 50)
    
    if RUST_SERVER_PASSWORD:
        rcon = RCONClient(RUST_SERVER_IP, RUST_SERVER_PORT, RUST_SERVER_PASSWORD)
        await asyncio.get_event_loop().run_in_executor(None, rcon.connect)
    
    if WIPE_CHANNEL_ID:
        wipe_channel = bot.get_channel(WIPE_CHANNEL_ID)
    
    update_status.start()
    check_wipe.start()

async def is_admin(ctx):
    if ADMIN_ROLE_ID == 0:
        return True
    if ctx.author.guild_permissions.administrator:
        return True
    role = ctx.guild.get_role(ADMIN_ROLE_ID)
    return role and role in ctx.author.roles

@tasks.loop(seconds=30)
async def update_status():
    global server_status
    if not rcon:
        return
    try:
        status = await asyncio.get_event_loop().run_in_executor(None, rcon.get_status)
        server_status = status
        # Обновляем статус бота
        if status['online'] > 0:
            await bot.change_presence(activity=discord.Game(name=f"🟢 {status['online']} / {status['sleeping']} спят"))
        else:
            await bot.change_presence(activity=discord.Game(name=f"🌙 0 / 0 спят"))
    except Exception as e:
        log.error(f"Ошибка: {e}")

@tasks.loop(hours=1)
async def check_wipe():
    if not wipe_channel:
        return
    wipe = get_wipe()
    if wipe['days'] == 1:
        embed = discord.Embed(title="💣 ВАЙП ЗАВТРА!", description=f"**{RUST_SERVER_NAME}**\n📅 {wipe['date']}\n⏰ {wipe['time']}", color=discord.Color.orange())
        await wipe_channel.send(embed=embed)

# ========== КОМАНДЫ ==========
@bot.command(name='admin')
async def cmd_admin(ctx):
    if not await is_admin(ctx):
        await ctx.send("❌ Нет прав!")
        return
    wipe = get_wipe()
    embed = discord.Embed(title="👑 АДМИН-ПАНЕЛЬ", description=f"**{RUST_SERVER_NAME}**", color=discord.Color.gold())
    embed.add_field(name="📊 СТАТУС", value=f"🟢 Онлайн: {server_status['online']}\n🌙 Спят: {server_status['sleeping']}", inline=False)
    embed.add_field(name="💣 ВАЙП", value=f"📅 {wipe['date']}\n⏰ {wipe['time']}\n🔢 #{wipe['wipe_number']}\n⏳ {wipe['days']}д {wipe['hours']}ч", inline=False)
    embed.add_field(name="📝 ЗАМЕТКИ", value="`!note create <название> <текст>`\n`!note list`\n`!note delete <id>`", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='status')
async def cmd_status(ctx):
    embed = discord.Embed(title="🖥️ СТАТУС СЕРВЕРА", description=f"**{RUST_SERVER_NAME}**", color=discord.Color.blue())
    embed.add_field(name="🎮 ИГРОКИ", value=f"🟢 Онлайн: {server_status['online']}\n🌙 Спят: {server_status['sleeping']}", inline=False)
    embed.add_field(name="🌐 IP", value=f"`{RUST_SERVER_IP}:{RUST_SERVER_PORT}`", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='wipe')
async def cmd_wipe(ctx):
    wipe = get_wipe()
    embed = discord.Embed(title="💣 ИНФОРМАЦИЯ О ВАЙПЕ", description=f"**{RUST_SERVER_NAME}**", color=discord.Color.purple())
    embed.add_field(name="📅 ДАТА", value=wipe['date'], inline=True)
    embed.add_field(name="⏰ ВРЕМЯ", value=wipe['time'], inline=True)
    embed.add_field(name="🔢 НОМЕР", value=f"#{wipe['wipe_number']}", inline=True)
    embed.add_field(name="⏳ ОСТАЛОСЬ", value=f"{wipe['days']} д. {wipe['hours']} ч. {wipe['minutes']} мин.", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='server')
async def cmd_server(ctx):
    embed = discord.Embed(title="ℹ️ ИНФОРМАЦИЯ О СЕРВЕРЕ", description=f"**{RUST_SERVER_NAME}**", color=discord.Color.gold())
    embed.add_field(name="🎮 IP", value=f"`{RUST_SERVER_IP}:{RUST_SERVER_PORT}`", inline=False)
    embed.add_field(name="🔄 ВАЙП", value="Каждые 2 недели по четвергам\nс 18.06.2026", inline=False)
    embed.add_field(name="👥 ТИП", value="x2 | SOLO/DUO", inline=True)
    await ctx.send(embed=embed)

@bot.command(name='note_create')
async def note_create(ctx, title: str, *, content: str):
    if not await is_admin(ctx):
        await ctx.send("❌ Нет прав!")
        return
    note_id = notes.create(str(ctx.author.id), title, content)
    await ctx.send(f"✅ Заметка #{note_id} создана!")

@bot.command(name='note_list')
async def note_list(ctx):
    if not await is_admin(ctx):
        await ctx.send("❌ Нет прав!")
        return
    user_notes = notes.get(str(ctx.author.id))
    if not user_notes:
        await ctx.send("📭 Нет заметок")
        return
    msg = "**📝 ВАШИ ЗАМЕТКИ:**\n"
    for n in user_notes:
        msg += f"`#{n['id']}` - {n['title']}\n"
    await ctx.send(msg)

@bot.command(name='note_delete')
async def note_delete(ctx, note_id: int):
    if not await is_admin(ctx):
        await ctx.send("❌ Нет прав!")
        return
    if notes.delete(str(ctx.author.id), note_id):
        await ctx.send(f"✅ Заметка #{note_id} удалена!")
    else:
        await ctx.send(f"❌ Заметка #{note_id} не найдена!")

@bot.command(name='help')
async def cmd_help(ctx):
    embed = discord.Embed(title="🤖 ПОМОЩЬ", color=discord.Color.blue())
    embed.add_field(name="📊 ИНФОРМАЦИЯ", value="`!status` - Статус\n`!wipe` - Вайп\n`!server` - О сервере", inline=False)
    if await is_admin(ctx):
        embed.add_field(name="👑 АДМИН", value="`!admin` - Панель\n`!note create/list/delete` - Заметки", inline=False)
    await ctx.send(embed=embed)

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
