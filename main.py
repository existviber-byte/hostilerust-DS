#!/usr/bin/env python3
"""
Hostile Rust Admin Bot - Discord бот для управления сервером x2
Вайпы: каждые 2 недели по четвергам, первый вайп 18.06.2026 в 12:00
"""

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
from typing import Optional, Dict, List
from dotenv import load_dotenv

load_dotenv()

# ========== НАСТРОЙКИ ==========
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
ADMIN_ROLE_ID = int(os.getenv('ADMIN_ROLE_ID', 0))
WIPE_CHANNEL_ID = int(os.getenv('WIPE_CHANNEL_ID', 0))

# Настройки сервера
RUST_SERVER_IP = os.getenv('RUST_SERVER_IP', '37.230.137.6')
RUST_SERVER_PORT = int(os.getenv('RUST_SERVER_PORT', 20602))
RUST_SERVER_PASSWORD = os.getenv('RUST_SERVER_PASSWORD', '')
RUST_SERVER_NAME = os.getenv('RUST_SERVER_NAME', 'HOSTILE RUST | x2 | SOLO/DUO')
RUST_SERVER_MAX_PLAYERS = int(os.getenv('RUST_SERVER_MAX_PLAYERS', 50))

# Настройки вайпа (первый вайп 18.06.2026 в 12:00, затем каждые 14 дней)
FIRST_WIPE_DATE = datetime(2026, 6, 18, 12, 0, 0)
WIPE_INTERVAL_DAYS = 14

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
log = logging.getLogger(__name__)

# ========== RCON КЛИЕНТ ==========
class RCONClient:
    def __init__(self, host: str, port: int, password: str):
        self.host = host
        self.port = port
        self.password = password
        self.socket = None
    
    def connect(self) -> bool:
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
            
            log.info("✅ RCON подключен")
            return True
        except Exception as e:
            log.error(f"❌ RCON ошибка: {e}")
            return False
    
    def send_command(self, command: str) -> Optional[str]:
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
            log.error(f"❌ RCON ошибка: {e}")
            return None
    
    def get_server_status(self) -> Dict:
        result = self.send_command("status")
        if not result:
            return {'online': 0, 'sleeping': 0, 'joining': 0}
        
        online = 0
        sleeping = 0
        joining = 0
        
        for line in result.split('\n'):
            if 'connected' in line.lower():
                numbers = re.findall(r'\d+', line)
                if numbers:
                    online = int(numbers[0]) if numbers else 0
            elif 'sleeping' in line.lower():
                numbers = re.findall(r'\d+', line)
                if numbers:
                    sleeping = int(numbers[0]) if numbers else 0
            elif 'joining' in line.lower() or 'connecting' in line.lower():
                numbers = re.findall(r'\d+', line)
                if numbers:
                    joining = int(numbers[0]) if numbers else 0
        
        return {'online': online, 'sleeping': sleeping, 'joining': joining}
    
    def close(self):
        if self.socket:
            self.socket.close()
            self.socket = None

# ========== УПРАВЛЕНИЕ КОНФИГУРАЦИЕЙ (АДМИНКА) ==========
class ConfigManager:
    def __init__(self):
        self.config_file = Path("data/config.json")
        self.config = {}
        self.load()
    
    def load(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except:
                self.config = self.get_default_config()
        else:
            self.config = self.get_default_config()
            self.save()
    
    def get_default_config(self) -> Dict:
        return {
            'server_name': RUST_SERVER_NAME,
            'server_ip': RUST_SERVER_IP,
            'server_port': RUST_SERVER_PORT,
            'server_max_players': RUST_SERVER_MAX_PLAYERS,
            'first_wipe_date': '2026-06-18 12:00:00',
            'wipe_interval_days': 14,
            'wipe_time_normal': '12:00',
            'wipe_time_first': '22:00',
            'discord_invite': 'https://discord.gg/invite',
            'vk_link': 'https://vk.com/group',
            'website': 'https://hostile-rust.ru'
        }
    
    def save(self):
        self.config_file.parent.mkdir(exist_ok=True)
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
    
    def get(self, key: str, default=None):
        return self.config.get(key, default)
    
    def set(self, key: str, value):
        self.config[key] = value
        self.save()
    
    def get_server_name(self) -> str:
        return self.config.get('server_name', RUST_SERVER_NAME)
    
    def get_server_ip(self) -> str:
        return self.config.get('server_ip', RUST_SERVER_IP)
    
    def get_server_port(self) -> int:
        return self.config.get('server_port', RUST_SERVER_PORT)
    
    def get_server_max_players(self) -> int:
        return self.config.get('server_max_players', RUST_SERVER_MAX_PLAYERS)

# ========== УПРАВЛЕНИЕ ЗАМЕТКАМИ (АДМИНКА) ==========
class NotesManager:
    def __init__(self):
        self.data_file = Path("data/notes.json")
        self.notes: Dict[str, List[Dict]] = {}
        self.load()
    
    def load(self):
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self.notes = json.load(f)
                log.info(f"📝 Загружено заметок для {len(self.notes)} админов")
            except:
                self.notes = {}
        else:
            self.data_file.parent.mkdir(exist_ok=True)
            self.save()
    
    def save(self):
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.notes, f, indent=2, ensure_ascii=False)
    
    def create_note(self, user_id: str, title: str, content: str, reminder_time: Optional[datetime] = None) -> int:
        if user_id not in self.notes:
            self.notes[user_id] = []
        
        note_id = len(self.notes[user_id]) + 1
        note = {
            'id': note_id,
            'title': title,
            'content': content,
            'created_at': datetime.now().isoformat(),
            'reminder_time': reminder_time.isoformat() if reminder_time else None,
            'is_reminded': False
        }
        self.notes[user_id].append(note)
        self.save()
        return note_id
    
    def get_notes(self, user_id: str) -> List[Dict]:
        return self.notes.get(user_id, [])
    
    def update_note(self, user_id: str, note_id: int, title: str = None, content: str = None, reminder_time: datetime = None) -> bool:
        for note in self.notes.get(user_id, []):
            if note['id'] == note_id:
                if title is not None:
                    note['title'] = title
                if content is not None:
                    note['content'] = content
                if reminder_time is not None:
                    note['reminder_time'] = reminder_time.isoformat()
                    note['is_reminded'] = False
                self.save()
                return True
        return False
    
    def delete_note(self, user_id: str, note_id: int) -> bool:
        notes = self.notes.get(user_id, [])
        for i, note in enumerate(notes):
            if note['id'] == note_id:
                notes.pop(i)
                for j, n in enumerate(notes):
                    n['id'] = j + 1
                self.save()
                return True
        return False
    
    def get_due_reminders(self) -> List[tuple]:
        now = datetime.now()
        due = []
        for user_id, notes in self.notes.items():
            for note in notes:
                if note.get('reminder_time') and not note.get('is_reminded'):
                    reminder_time = datetime.fromisoformat(note['reminder_time'])
                    if reminder_time <= now:
                        due.append((user_id, note))
        return due
    
    def mark_reminded(self, user_id: str, note_id: int):
        for note in self.notes.get(user_id, []):
            if note['id'] == note_id:
                note['is_reminded'] = True
                self.save()
                break

# ========== РАСЧЕТ ВАЙПА (с 18.06.2026) ==========
def get_next_wipe() -> datetime:
    """Расчет следующего вайпа от 18.06.2026 каждые 14 дней"""
    now = datetime.now()
    
    # Первый вайп 18.06.2026 12:00
    first_wipe = FIRST_WIPE_DATE
    
    # Если сейчас раньше первого вайпа
    if now < first_wipe:
        return first_wipe
    
    # Расчет количества прошедших дней от первого вайпа
    days_since_first = (now - first_wipe).days
    cycles_passed = days_since_first // WIPE_INTERVAL_DAYS
    
    # Следующий вайп
    next_wipe = first_wipe + timedelta(days=WIPE_INTERVAL_DAYS * cycles_passed)
    
    # Если вайп уже прошел, берем следующий
    if next_wipe <= now:
        next_wipe = first_wipe + timedelta(days=WIPE_INTERVAL_DAYS * (cycles_passed + 1))
    
    # Проверка на первый четверг месяца (вайп в 22:00)
    if next_wipe.day <= 7 and next_wipe.weekday() == 3:
        next_wipe = next_wipe.replace(hour=22, minute=0, second=0, microsecond=0)
    else:
        next_wipe = next_wipe.replace(hour=12, minute=0, second=0, microsecond=0)
    
    return next_wipe

def get_wipe_info() -> dict:
    """Получение полной информации о вайпе"""
    next_wipe = get_next_wipe()
    now = datetime.now()
    delta = next_wipe - now
    
    # Прогресс цикла вайпа
    first_wipe = FIRST_WIPE_DATE
    if now >= first_wipe:
        days_since_first = (now - first_wipe).days
        current_cycle = days_since_first // WIPE_INTERVAL_DAYS
        cycle_progress_days = days_since_first % WIPE_INTERVAL_DAYS
        cycle_progress_percent = int(cycle_progress_days / WIPE_INTERVAL_DAYS * 100)
    else:
        current_cycle = 0
        cycle_progress_percent = 0
    
    # Номер вайпа
    wipe_number = ((next_wipe - first_wipe).days // WIPE_INTERVAL_DAYS) + 1
    
    # Является ли вайп первым четвергом
    is_first_thursday = next_wipe.day <= 7 and next_wipe.weekday() == 3
    wipe_time = "22:00 МСК" if is_first_thursday else "12:00 МСК"
    
    return {
        'date': next_wipe.strftime('%d.%m.%Y'),
        'time': wipe_time,
        'datetime': next_wipe,
        'days': delta.days,
        'hours': delta.seconds // 3600,
        'minutes': (delta.seconds % 3600) // 60,
        'seconds': delta.seconds % 60,
        'is_first_thursday': is_first_thursday,
        'wipe_number': wipe_number,
        'cycle_progress': cycle_progress_percent,
        'next_wipe_timestamp': next_wipe
    }

# ========== БОТ ==========
class HostileAdminBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(command_prefix='!', intents=intents)
        
        self.rcon: Optional[RCONClient] = None
        self.config_manager = ConfigManager()
        self.notes_manager = NotesManager()
        self.wipe_channel: Optional[discord.TextChannel] = None
        self.server_status = {'online': 0, 'sleeping': 0, 'joining': 0}
        self.bot_start_time = datetime.now()
        self.last_wipe_notified = None
    
    async def setup_hook(self):
        """Настройка при запуске"""
        if RUST_SERVER_PASSWORD:
            self.rcon = RCONClient(
                self.config_manager.get_server_ip(),
                self.config_manager.get_server_port(),
                RUST_SERVER_PASSWORD
            )
            await asyncio.get_event_loop().run_in_executor(None, self.rcon.connect)
        
        if WIPE_CHANNEL_ID:
            self.wipe_channel = self.get_channel(WIPE_CHANNEL_ID)
        
        # Запуск фоновых задач
        self.update_server_status.start()
        self.update_bot_status.start()
        self.check_reminders.start()
        self.check_wipe_notification.start()
    
    async def on_ready(self):
        log.info("=" * 60)
        log.info(f"✅ Бот {self.user.name} запущен!")
        log.info(f"📊 ID: {self.user.id}")
        log.info(f"🎮 Сервер: {self.config_manager.get_server_name()}")
        log.info(f"🌐 IP: {self.config_manager.get_server_ip()}:{self.config_manager.get_server_port()}")
        log.info("=" * 60)
        
        # Отправка в канал уведомлений
        if self.wipe_channel:
            wipe = get_wipe_info()
            embed = discord.Embed(
                title="🖥️ БОТ ЗАПУЩЕН",
                description=f"**{self.config_manager.get_server_name()}**\n"
                           f"IP: `{self.config_manager.get_server_ip()}:{self.config_manager.get_server_port()}`\n\n"
                           f"💣 Следующий вайп: **{wipe['date']}** в **{wipe['time']}**\n"
                           f"📊 Номер вайпа: **#{wipe['wipe_number']}**",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            await self.wipe_channel.send(embed=embed)
    
    async def is_admin(self, user: discord.User) -> bool:
        if ADMIN_ROLE_ID == 0:
            return True
        for guild in self.guilds:
            member = guild.get_member(user.id)
            if member:
                if member.guild_permissions.administrator:
                    return True
                role = guild.get_role(ADMIN_ROLE_ID)
                if role and role in member.roles:
                    return True
        return False
    
    # ========== ФОНОВЫЕ ЗАДАЧИ ==========
    
    @tasks.loop(seconds=30)
    async def update_server_status(self):
        """Обновление статуса сервера"""
        if not self.rcon:
            return
        try:
            status = await asyncio.get_event_loop().run_in_executor(
                None, self.rcon.get_server_status
            )
            self.server_status = status
        except Exception as e:
            log.error(f"Ошибка статуса сервера: {e}")
    
    @tasks.loop(seconds=60)
    async def update_bot_status(self):
        """Обновление статуса бота в Discord"""
        if self.rcon and self.server_status['online'] > 0:
            status_text = f"🟢 {self.server_status['online']}/{self.config_manager.get_server_max_players()} | Вход: {self.server_status['joining']} | x2"
            await self.change_presence(activity=discord.Game(name=status_text))
        elif self.rcon:
            status_text = f"🌙 0/{self.config_manager.get_server_max_players()} | x2"
            await self.change_presence(activity=discord.Game(name=status_text))
        else:
            status_text = f"⚠️ RCON | {self.config_manager.get_server_ip()}"
            await self.change_presence(activity=discord.Game(name=status_text))
    
    @tasks.loop(minutes=1)
    async def check_reminders(self):
        """Проверка напоминаний о заметках"""
        for user_id_str, note in self.notes_manager.get_due_reminders():
            try:
                user = await self.fetch_user(int(user_id_str))
                if user:
                    embed = discord.Embed(
                        title="📝 НАПОМИНАНИЕ",
                        description=f"**{note['title']}**\n\n{note['content']}",
                        color=discord.Color.blue(),
                        timestamp=datetime.now()
                    )
                    await user.send(embed=embed)
                    self.notes_manager.mark_reminded(user_id_str, note['id'])
                    log.info(f"🔔 Напоминание отправлено {user_id_str}: {note['title']}")
            except Exception as e:
                log.error(f"Ошибка отправки напоминания: {e}")
    
    @tasks.loop(minutes=30)
    async def check_wipe_notification(self):
        """Проверка и отправка уведомлений о вайпе"""
        if not self.wipe_channel:
            return
        
        wipe = get_wipe_info()
        now = datetime.now()
        
        # За 7 дней
        if wipe['days'] == 7 and wipe['hours'] <= 12:
            if self.last_wipe_notified != '7days':
                embed = discord.Embed(
                    title="💣 ВАЙП ЧЕРЕЗ НЕДЕЛЮ!",
                    description=f"**{self.config_manager.get_server_name()}**\n\n"
                               f"📅 Дата: {wipe['date']}\n"
                               f"⏰ Время: {wipe['time']}\n"
                               f"📊 Номер вайпа: **#{wipe['wipe_number']}**\n\n"
                               f"🔄 Вайпы проходят каждые 2 недели с 18.06.2026",
                    color=discord.Color.orange(),
                    timestamp=now
                )
                await self.wipe_channel.send(embed=embed)
                self.last_wipe_notified = '7days'
        
        # За 1 день
        elif wipe['days'] == 1 and wipe['hours'] <= 12:
            if self.last_wipe_notified != '1day':
                # Прогресс-бар
                bar_length = 20
                filled = int(bar_length * wipe['cycle_progress'] / 100)
                bar = "█" * filled + "░" * (bar_length - filled)
                
                embed = discord.Embed(
                    title="⚠️ ВАЙП ЗАВТРА!",
                    description=f"**{self.config_manager.get_server_name()}**\n\n"
                               f"📅 **{wipe['date']}** в **{wipe['time']}**\n\n"
                               f"📊 Прогресс цикла:\n`{bar}` {wipe['cycle_progress']}%\n\n"
                               f"💡 **Что будет:**\n"
                               f"• Очистка карты\n"
                               f"• Сброс лута\n"
                               f"• Новый вайп #{wipe['wipe_number']}",
                    color=discord.Color.red(),
                    timestamp=now
                )
                await self.wipe_channel.send(embed=embed)
                self.last_wipe_notified = '1day'
        
        # За 1 час
        elif wipe['days'] == 0 and wipe['hours'] <= 1 and wipe['hours'] > 0:
            if self.last_wipe_notified != '1hour':
                embed = discord.Embed(
                    title="🔥 ВАЙП ЧЕРЕЗ ЧАС!",
                    description=f"**{self.config_manager.get_server_name()}**\n\n"
                               f"⏰ Вайп в **{wipe['time']}**\n\n"
                               f"🔄 Сервер будет перезагружен!\n"
                               f"📊 Осталось: {wipe['hours']} ч. {wipe['minutes']} мин.",
                    color=discord.Color.red(),
                    timestamp=now
                )
                await self.wipe_channel.send(embed=embed)
                self.last_wipe_notified = '1hour'
        
        # Начало вайпа
        elif wipe['days'] == 0 and wipe['hours'] == 0 and wipe['minutes'] <= 10:
            if self.last_wipe_notified != 'now':
                embed = discord.Embed(
                    title="💥 НАЧАЛСЯ ВАЙП!",
                    description=f"**{self.config_manager.get_server_name()}**\n\n"
                               f"🔄 Сервер перезагружается...\n"
                               f"💫 **Вайп #{wipe['wipe_number']}**\n\n"
                               f"⏱️ Обычно процесс занимает 5-10 минут.\n"
                               f"🎮 Скоро сервер снова будет доступен!",
                    color=discord.Color.purple(),
                    timestamp=now
                )
                await self.wipe_channel.send(embed=embed)
                self.last_wipe_notified = 'now'
        
        # Сброс после вайпа
        elif wipe['days'] > 7:
            self.last_wipe_notified = None
    
    # ========== АДМИН-КОМАНДЫ ДЛЯ РЕДАКТИРОВАНИЯ ==========
    
    @commands.group(name='set', invoke_without_command=True)
    async def set_cmd(self, ctx):
        """Настройка параметров сервера"""
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ Нет прав!")
            return
        
        embed = discord.Embed(
            title="⚙️ НАСТРОЙКИ СЕРВЕРА",
            description="Используйте: `!set <параметр> <значение>`",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="📝 ПАРАМЕТРЫ",
            value="`name` - Название сервера\n"
                  "`ip` - IP сервера\n"
                  "`port` - Порт сервера\n"
                  "`max_players` - Макс. игроков\n"
                  "`invite` - Ссылка Discord\n"
                  "`vk` - Ссылка VK\n"
                  "`website` - Сайт",
            inline=False
        )
        embed.add_field(
            name="📊 ТЕКУЩИЕ ЗНАЧЕНИЯ",
            value=f"**Название:** {self.config_manager.get_server_name()}\n"
                  f"**IP:** {self.config_manager.get_server_ip()}\n"
                  f"**Порт:** {self.config_manager.get_server_port()}\n"
                  f"**Макс. игроков:** {self.config_manager.get_server_max_players()}",
            inline=False
        )
        await ctx.send(embed=embed)
    
    @set_cmd.command(name='name')
    async def set_name(self, ctx, *, name: str):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ Нет прав!")
            return
        self.config_manager.set('server_name', name)
        await ctx.send(f"✅ Название сервера изменено на: **{name}**")
        await self.update_bot_status()
    
    @set_cmd.command(name='ip')
    async def set_ip(self, ctx, ip: str):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ Нет прав!")
            return
        self.config_manager.set('server_ip', ip)
        await ctx.send(f"✅ IP сервера изменен на: `{ip}`")
    
    @set_cmd.command(name='port')
    async def set_port(self, ctx, port: int):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ Нет прав!")
            return
        self.config_manager.set('server_port', port)
        await ctx.send(f"✅ Порт сервера изменен на: `{port}`")
    
    @set_cmd.command(name='max_players')
    async def set_max_players(self, ctx, max_players: int):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ Нет прав!")
            return
        self.config_manager.set('server_max_players', max_players)
        await ctx.send(f"✅ Максимум игроков изменен на: **{max_players}**")
    
    @set_cmd.command(name='invite')
    async def set_invite(self, ctx, url: str):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ Нет прав!")
            return
        self.config_manager.set('discord_invite', url)
        await ctx.send(f"✅ Discord ссылка обновлена: {url}")
    
    @set_cmd.command(name='vk')
    async def set_vk(self, ctx, url: str):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ Нет прав!")
            return
        self.config_manager.set('vk_link', url)
        await ctx.send(f"✅ VK ссылка обновлена: {url}")
    
    @set_cmd.command(name='website')
    async def set_website(self, ctx, url: str):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ Нет прав!")
            return
        self.config_manager.set('website', url)
        await ctx.send(f"✅ Сайт обновлен: {url}")
    
    @set_cmd.command(name='show')
    async def show_config(self, ctx):
        """Показать текущую конфигурацию"""
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ Нет прав!")
            return
        
        embed = discord.Embed(
            title="📋 ТЕКУЩАЯ КОНФИГУРАЦИЯ",
            color=discord.Color.gold()
        )
        embed.add_field(name="🎮 Название", value=self.config_manager.get_server_name(), inline=False)
        embed.add_field(name="🌐 IP", value=f"{self.config_manager.get_server_ip()}:{self.config_manager.get_server_port()}", inline=False)
        embed.add_field(name="👥 Макс. игроков", value=self.config_manager.get_server_max_players(), inline=False)
        embed.add_field(name="💬 Discord", value=self.config_manager.get('discord_invite', 'Не задан'), inline=False)
        embed.add_field(name="📱 VK", value=self.config_manager.get('vk_link', 'Не задан'), inline=False)
        embed.add_field(name="🌍 Сайт", value=self.config_manager.get('website', 'Не задан'), inline=False)
        await ctx.send(embed=embed)
    
    # ========== ОСНОВНЫЕ КОМАНДЫ ==========
    
    @commands.command(name='admin')
    async def cmd_admin_panel(self, ctx):
        """Админ-панель"""
        is_admin_user = await self.is_admin(ctx.author)
        
        wipe = get_wipe_info()
        
        embed = discord.Embed(
            title="👑 АДМИН-ПАНЕЛЬ",
            description=f"**{self.config_manager.get_server_name()}**",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        
        # Статус сервера
        embed.add_field(
            name="🖥️ СТАТУС СЕРВЕРА",
            value=f"🟢 Онлайн: **{self.server_status['online']}**\n"
                  f"🌙 Спят: **{self.server_status['sleeping']}**\n"
                  f"🚪 Заходят: **{self.server_status['joining']}**\n"
                  f"📊 Макс: **{self.config_manager.get_server_max_players()}**\n"
                  f"🔌 RCON: {'✅' if self.rcon else '❌'}",
            inline=False
        )
        
        # Информация о вайпе
        bar_length = 20
        filled = int(bar_length * wipe['cycle_progress'] / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        embed.add_field(
            name="💣 ВАЙП",
            value=f"📅 **{wipe['date']}**\n"
                  f"⏰ **{wipe['time']}**\n"
                  f"📊 Номер: **#{wipe['wipe_number']}**\n"
                  f"📈 Прогресс:\n`{bar}` {wipe['cycle_progress']}%\n"
                  f"⏳ Осталось: {wipe['days']} д. {wipe['hours']} ч. {wipe['minutes']} мин.",
            inline=False
        )
        
        # Команды
        embed.add_field(
            name="📝 ЗАМЕТКИ",
            value="`!note create <название> <текст>` - Создать\n"
                  "`!note list` - Список\n"
                  "`!note edit <id> <текст>` - Редактировать\n"
                  "`!note delete <id>` - Удалить\n"
                  "`!note remind <id> <часы>` - Напомнить",
            inline=False
        )
        
        if is_admin_user:
            embed.add_field(
                name="⚙️ НАСТРОЙКИ",
                value="`!set name <название>` - Название сервера\n"
                      "`!set ip <ip>` - IP сервера\n"
                      "`!set port <port>` - Порт\n"
                      "`!set max_players <число>` - Макс. игроков\n"
                      "`!set show` - Показать настройки",
                inline=False
            )
        
        embed.set_footer(text=f"Администратор: {ctx.author.name}")
        await ctx.send(embed=embed)
    
    @commands.command(name='status')
    async def cmd_status(self, ctx):
        """Статус сервера"""
        embed = discord.Embed(
            title="🖥️ СТАТУС СЕРВЕРА",
            description=f"**{self.config_manager.get_server_name()}**",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="🎮 ИГРОКИ",
            value=f"🟢 Онлайн: **{self.server_status['online']}**\n"
                  f"🌙 Спят: **{self.server_status['sleeping']}**\n"
                  f"🚪 Заходят: **{self.server_status['joining']}**\n"
                  f"📊 Максимум: **{self.config_manager.get_server_max_players()}**",
            inline=False
        )
        
        embed.add_field(
            name="🌐 ПОДКЛЮЧЕНИЕ",
            value=f"IP: `{self.config_manager.get_server_ip()}:{self.config_manager.get_server_port()}`\n"
                  f"RCON: {'✅ Активен' if self.rcon else '❌ Неактивен'}",
            inline=False
        )
        
        uptime = datetime.now() - self.bot_start_time
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds % 3600) // 60
        embed.set_footer(text=f"Бот работает: {uptime.days}д {hours}ч {minutes}м")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='wipe')
    async def cmd_wipe(self, ctx):
        """Информация о вайпе"""
        wipe = get_wipe_info()
        
        # Красивый прогресс-бар
        bar_length = 25
        filled = int(bar_length * wipe['cycle_progress'] / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        embed = discord.Embed(
            title="💣 ИНФОРМАЦИЯ О ВАЙПЕ",
            description=f"**{self.config_manager.get_server_name()}**\n"
                       f"🔄 Вайпы проходят каждые **14 дней** с 18.06.2026",
            color=discord.Color.purple(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="📅 ДАТА", value=wipe['date'], inline=True)
        embed.add_field(name="⏰ ВРЕМЯ", value=wipe['time'], inline=True)
        embed.add_field(name="🔢 НОМЕР", value=f"**#{wipe['wipe_number']}**", inline=True)
        embed.add_field(name="⏳ ОСТАЛОСЬ", value=f"{wipe['days']} д. {wipe['hours']} ч. {wipe['minutes']} мин.", inline=False)
        embed.add_field(name="📊 ПРОГРЕСС ЦИКЛА", value=f"`{bar}` {wipe['cycle_progress']}%", inline=False)
        
        if wipe['is_first_thursday']:
            embed.add_field(
                name="⚠️ ВНИМАНИЕ",
                value="Это первый четверг месяца! Вайп в **22:00 МСК**",
                inline=False
            )
        
        embed.set_footer(text=f"Следующий вайп: {wipe['date']} в {wipe['time']}")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='server')
    async def cmd_server(self, ctx):
        """Информация о сервере"""
        embed = discord.Embed(
            title="ℹ️ ИНФОРМАЦИЯ О СЕРВЕРЕ",
            description=f"**{self.config_manager.get_server_name()}**",
            color=discord.Color.gold()
        )
        
        embed.add_field(name="🎮 IP", value=f"`{self.config_manager.get_server_ip()}:{self.config_manager.get_server_port()}`", inline=False)
        embed.add_field(name="🔄 ВАЙП", value="Каждые 2 недели по четвергам\nПервый четверг месяца - 22:00", inline=False)
        embed.add_field(name="👥 ТИП", value="x2 | SOLO/DUO", inline=True)
        embed.add_field(name="👑 МАКС. ИГРОКОВ", value=f"{self.config_manager.get_server_max_players()}", inline=True)
        
        if self.config_manager.get('discord_invite'):
            embed.add_field(name="💬 DISCORD", value=f"[Присоединиться]({self.config_manager.get('discord_invite')})", inline=True)
        if self.config_manager.get('vk_link'):
            embed.add_field(name="📱 VK", value=f"[Группа]({self.config_manager.get('vk_link')})", inline=True)
        
        await ctx.send(embed=embed)
    
    # ========== КОМАНДЫ ЗАМЕТОК ==========
    
    @commands.command(name='note_create')
    async def note_create(self, ctx, title: str, *, content: str):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ Нет прав!")
            return
        note_id = self.notes_manager.create_note(str(ctx.author.id), title, content)
        await ctx.send(f"✅ Заметка **#{note_id} - {title}** создана!")
    
    @commands.command(name='note_list')
    async def note_list(self, ctx):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ Нет прав!")
            return
        notes = self.notes_manager.get_notes(str(ctx.author.id))
        if not notes:
            await ctx.send("📭 У вас нет заметок. Используйте `!note create`")
            return
        
        embed = discord.Embed(title=f"📝 ВАШИ ЗАМЕТКИ ({len(notes)})", color=discord.Color.blue())
        for note in notes[-10:]:
            embed.add_field(
                name=f"#{note['id']} - {note['title']}",
                value=note['content'][:150] + ('...' if len(note['content']) > 150 else ''),
                inline=False
            )
        await ctx.send(embed=embed)
    
    @commands.command(name='note_edit')
    async def note_edit(self, ctx, note_id: int, *, content: str):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ Нет прав!")
            return
        if self.notes_manager.update_note(str(ctx.author.id), note_id, content=content):
            await ctx.send(f"✅ Заметка #{note_id} обновлена!")
        else:
            await ctx.send(f"❌ Заметка #{note_id} не найдена!")
    
    @commands.command(name='note_delete')
    async def note_delete(self, ctx, note_id: int):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ Нет прав!")
            return
        if self.notes_manager.delete_note(str(ctx.author.id), note_id):
            await ctx.send(f"✅ Заметка #{note_id} удалена!")
        else:
            await ctx.send(f"❌ Заметка #{note_id} не найдена!")
    
    @commands.command(name='note_remind')
    async def note_remind(self, ctx, note_id: int, hours: int):
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ Нет прав!")
            return
        reminder_time = datetime.now() + timedelta(hours=hours)
        if self.notes_manager.update_note(str(ctx.author.id), note_id, reminder_time=reminder_time):
            await ctx.send(f"✅ Напоминание для заметки #{note_id} установлено на {reminder_time.strftime('%d.%m.%Y %H:%M')}")
        else:
            await ctx.send(f"❌ Заметка #{note_id} не найдена!")
    
    @commands.command(name='help')
    async def cmd_help(self, ctx):
        embed = discord.Embed(
            title="🤖 ПОМОЩЬ ПО КОМАНДАМ",
            description=f"**{self.config_manager.get_server_name()}**",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📊 ИНФОРМАЦИЯ",
            value="`!status` - Статус сервера\n"
                  "`!wipe` - Информация о вайпе\n"
                  "`!server` - Информация о сервере",
            inline=False
        )
        
        if await self.is_admin(ctx.author):
            embed.add_field(
                name="👑 АДМИН-КОМАНДЫ",
                value="`!admin` - Админ-панель\n"
                      "`!set name/ip/port/max_players/show` - Настройки\n"
                      "`!note create/list/edit/delete/remind` - Заметки",
                inline=False
            )
        
        embed.set_footer(text="Бот автоматически уведомляет о вайпе в канал")
        await ctx.send(embed=embed)

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    bot = HostileAdminBot()
    bot.run(DISCORD_TOKEN)
