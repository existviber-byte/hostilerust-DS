#!/usr/bin/env python3
"""
Hostile Admin Bot - Discord бот для администрации Rust сервера
Функции:
- Управление заметками с напоминаниями в ЛС
- Мониторинг сервера (онлайн, спящие игроки)
- Уведомления о вайпе в заданный канал
- Статус бота с информацией о сервере
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
from typing import Optional, Dict, List, Tuple
from dotenv import load_dotenv

load_dotenv()

# ========== НАСТРОЙКИ ИЗ ПЕРЕМЕННЫХ ==========
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
ADMIN_ROLE_ID = int(os.getenv('ADMIN_ROLE_ID', 0))
WIPE_CHANNEL_ID = int(os.getenv('WIPE_CHANNEL_ID', 0))  # Канал для уведомлений о вайпе

# Настройки сервера Rust
RUST_SERVER_IP = os.getenv('RUST_SERVER_IP', '37.230.137.6')
RUST_SERVER_PORT = int(os.getenv('RUST_SERVER_PORT', 20602))
RUST_SERVER_PASSWORD = os.getenv('RUST_SERVER_PASSWORD', '')
RUST_SERVER_NAME = os.getenv('RUST_SERVER_NAME', 'HOSTILE RUST | x2 | SOLO/DUO')

# Настройки вайпа (четверг = 3, 0 = понедельник)
WIPE_DAY = 3  # Четверг
WIPE_HOUR_NORMAL = 12    # 12:00 МСК
WIPE_HOUR_FIRST = 22     # 22:00 МСК для первого четверга месяца

# Настройки обновления статуса (в секундах)
STATUS_UPDATE_INTERVAL = 60  # Обновление статуса бота каждую минуту
SERVER_STATUS_INTERVAL = 300  # Обновление данных с сервера каждые 5 минут

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
log = logging.getLogger(__name__)

# ========== RCON КЛИЕНТ ДЛЯ ПОЛУЧЕНИЯ СТАТУСА ==========
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
            log.error(f"❌ RCON ошибка: {e}")
            return None
    
    def get_server_status(self) -> Dict:
        """Получение статуса сервера"""
        result = self.send_command("status")
        if not result:
            return {'online': 0, 'sleeping': 0, 'max': 0, 'players': []}
        
        online = 0
        sleeping = 0
        max_players = 0
        players = []
        
        for line in result.split('\n'):
            # Парсим количество игроков
            if 'connected' in line.lower() and 'players' in line.lower():
                numbers = re.findall(r'\d+', line)
                if len(numbers) >= 2:
                    online = int(numbers[0])
                    max_players = int(numbers[1])
            
            # Парсим спящих
            if 'sleeping' in line.lower():
                numbers = re.findall(r'\d+', line)
                if numbers:
                    sleeping = int(numbers[0])
            
            # Парсим список игроков
            if 'steamid' in line.lower():
                parts = line.split()
                for i, part in enumerate(parts):
                    if 'steamid' in part.lower() and i + 1 < len(parts):
                        players.append(parts[i + 1])
        
        return {
            'online': online,
            'sleeping': sleeping,
            'max': max_players,
            'players': players
        }
    
    def close(self):
        if self.socket:
            self.socket.close()
            self.socket = None

# ========== УПРАВЛЕНИЕ ЗАМЕТКАМИ ==========
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
                log.info(f"📝 Загружено заметок для {len(self.notes)} пользователей")
            except Exception as e:
                log.error(f"Ошибка загрузки заметок: {e}")
                self.notes = {}
        else:
            self.data_file.parent.mkdir(exist_ok=True)
            self.save()
    
    def save(self):
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.notes, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.error(f"Ошибка сохранения заметок: {e}")
    
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
    
    def get_due_reminders(self) -> List[Tuple[str, Dict]]:
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

# ========== РАСЧЕТ ВАЙПА ==========
def is_first_thursday(date: datetime) -> bool:
    """Проверка, является ли дата первым четвергом месяца"""
    return date.day <= 7 and date.weekday() == 3

def get_next_wipe() -> datetime:
    """Расчет даты следующего вайпа"""
    now = datetime.now()
    
    days_until_thursday = (WIPE_DAY - now.weekday()) % 7
    if days_until_thursday == 0 and now.hour >= WIPE_HOUR_NORMAL:
        days_until_thursday = 7
    
    next_wipe = now + timedelta(days=days_until_thursday)
    wipe_hour = WIPE_HOUR_FIRST if is_first_thursday(next_wipe) else WIPE_HOUR_NORMAL
    next_wipe = next_wipe.replace(hour=wipe_hour, minute=0, second=0, microsecond=0)
    
    return next_wipe

def get_wipe_info() -> dict:
    """Получение информации о вайпе"""
    next_wipe = get_next_wipe()
    now = datetime.now()
    delta = next_wipe - now
    
    is_first = is_first_thursday(next_wipe)
    wipe_time = "22:00 МСК" if is_first else "12:00 МСК"
    
    return {
        'date': next_wipe.strftime('%d.%m.%Y'),
        'time': wipe_time,
        'days': delta.days,
        'hours': delta.seconds // 3600,
        'minutes': (delta.seconds % 3600) // 60,
        'is_first_thursday': is_first,
        'timestamp': next_wipe
    }

# ========== БОТ ==========
class HostileAdminBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(command_prefix='!', intents=intents)
        
        self.rcon: Optional[RCONClient] = None
        self.notes_manager = NotesManager()
        self.wipe_channel: Optional[discord.TextChannel] = None
        self.server_status = {'online': 0, 'sleeping': 0, 'max': 0, 'players': []}
        self.last_wipe_notified = None
        self.bot_start_time = datetime.now()
    
    async def setup_hook(self):
        """Настройка при запуске"""
        # Подключаем RCON
        if RUST_SERVER_PASSWORD:
            self.rcon = RCONClient(RUST_SERVER_IP, RUST_SERVER_PORT, RUST_SERVER_PASSWORD)
            await asyncio.get_event_loop().run_in_executor(None, self.rcon.connect)
            log.info("🔌 RCON инициализирован")
        else:
            log.warning("⚠️ RCON пароль не задан! Статус сервера не будет обновляться")
        
        # Получаем канал для уведомлений о вайпе
        if WIPE_CHANNEL_ID:
            self.wipe_channel = self.get_channel(WIPE_CHANNEL_ID)
            if self.wipe_channel:
                log.info(f"📢 Канал уведомлений о вайпе: #{self.wipe_channel.name}")
            else:
                log.warning(f"⚠️ Канал с ID {WIPE_CHANNEL_ID} не найден!")
        
        # Запускаем фоновые задачи
        self.update_server_status.start()
        self.update_bot_status.start()
        self.check_reminders.start()
        self.check_wipe_notification.start()
    
    async def on_ready(self):
        """Событие при запуске"""
        log.info("=" * 50)
        log.info(f"✅ Бот {self.user.name} запущен!")
        log.info(f"📊 ID бота: {self.user.id}")
        log.info(f"🎮 Сервер: {RUST_SERVER_NAME}")
        log.info(f"🌐 IP: {RUST_SERVER_IP}:{RUST_SERVER_PORT}")
        log.info("=" * 50)
    
    async def is_admin(self, user: discord.User) -> bool:
        """Проверка прав администратора"""
        if ADMIN_ROLE_ID == 0:
            return True
        
        for guild in self.guilds:
            member = guild.get_member(user.id)
            if member:
                admin_role = guild.get_role(ADMIN_ROLE_ID)
                if admin_role and admin_role in member.roles:
                    return True
                if member.guild_permissions.administrator:
                    return True
        return False
    
    # ========== ФОНОВЫЕ ЗАДАЧИ ==========
    
    @tasks.loop(seconds=SERVER_STATUS_INTERVAL)
    async def update_server_status(self):
        """Обновление статуса сервера"""
        if not self.rcon:
            return
        
        try:
            status = await asyncio.get_event_loop().run_in_executor(
                None, self.rcon.get_server_status
            )
            self.server_status = status
            log.info(f"📊 Статус сервера: {status['online']}/{status['max']} игроков, {status['sleeping']} спят")
        except Exception as e:
            log.error(f"❌ Ошибка обновления статуса: {e}")
    
    @tasks.loop(seconds=STATUS_UPDATE_INTERVAL)
    async def update_bot_status(self):
        """Обновление статуса бота (онлайн/оффлайн)"""
        if self.rcon and self.server_status['online'] > 0:
            status_text = f"🟢 {self.server_status['online']}/{self.server_status['max']} | {RUST_SERVER_IP}"
            activity = discord.Game(name=status_text)
            await self.change_presence(activity=activity, status=discord.Status.online)
        elif self.rcon:
            status_text = f"🌙 0/{self.server_status['max']} | {RUST_SERVER_IP}"
            activity = discord.Game(name=status_text)
            await self.change_presence(activity=activity, status=discord.Status.idle)
        else:
            status_text = f"⚠️ RCON | {RUST_SERVER_IP}"
            activity = discord.Game(name=status_text)
            await self.change_presence(activity=activity, status=discord.Status.dnd)
    
    @tasks.loop(minutes=1)
    async def check_reminders(self):
        """Проверка напоминаний о заметках"""
        due_reminders = self.notes_manager.get_due_reminders()
        
        for user_id_str, note in due_reminders:
            try:
                user = await self.fetch_user(int(user_id_str))
                if user:
                    embed = discord.Embed(
                        title="📝 НАПОМИНАНИЕ",
                        description=f"**{note['title']}**\n\n{note['content']}",
                        color=discord.Color.blue(),
                        timestamp=datetime.now()
                    )
                    embed.set_footer(text=f"Заметка #{note['id']}")
                    await user.send(embed=embed)
                    self.notes_manager.mark_reminded(user_id_str, note['id'])
                    log.info(f"🔔 Отправлено напоминание пользователю {user_id_str}: {note['title']}")
            except Exception as e:
                log.error(f"❌ Ошибка отправки напоминания: {e}")
    
    @tasks.loop(hours=1)
    async def check_wipe_notification(self):
        """Проверка и отправка уведомлений о вайпе"""
        if not self.wipe_channel:
            return
        
        wipe = get_wipe_info()
        
        # Уведомление за 1 день
        if wipe['days'] == 1 and wipe['hours'] <= 12:
            if self.last_wipe_notified != '1day':
                embed = discord.Embed(
                    title="💣 ВАЙП ЗАВТРА!",
                    description=f"**{RUST_SERVER_NAME}**\n\n"
                               f"📅 Дата: {wipe['date']}\n"
                               f"⏰ Время: {wipe['time']}\n\n"
                               f"⚠️ Не забудьте подготовиться к вайпу!",
                    color=discord.Color.orange(),
                    timestamp=datetime.now()
                )
                await self.wipe_channel.send(embed=embed)
                self.last_wipe_notified = '1day'
                log.info("📢 Отправлено уведомление о вайпе за день")
        
        # Уведомление за 1 час
        elif wipe['days'] == 0 and wipe['hours'] <= 1 and wipe['hours'] > 0:
            if self.last_wipe_notified != '1hour':
                embed = discord.Embed(
                    title="⚠️ ВАЙП ЧЕРЕЗ ЧАС!",
                    description=f"**{RUST_SERVER_NAME}**\n\n"
                               f"⏰ Вайп в {wipe['time']}\n\n"
                               f"🔄 Сервер будет перезагружен!",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                await self.wipe_channel.send(embed=embed)
                self.last_wipe_notified = '1hour'
                log.info("📢 Отправлено уведомление о вайпе за час")
        
        # Уведомление о начале вайпа
        elif wipe['days'] == 0 and wipe['hours'] == 0 and wipe['minutes'] <= 10:
            if self.last_wipe_notified != 'now':
                embed = discord.Embed(
                    title="💣 НАЧАЛСЯ ВАЙП!",
                    description=f"**{RUST_SERVER_NAME}**\n\n"
                               f"🔄 Сервер перезагружается...\n"
                               f"💫 Скоро сервер снова будет доступен!",
                    color=discord.Color.purple(),
                    timestamp=datetime.now()
                )
                await self.wipe_channel.send(embed=embed)
                self.last_wipe_notified = 'now'
                log.info("📢 Отправлено уведомление о начале вайпа")
        
        # Сбрасываем флаг после вайпа
        elif wipe['days'] > 1:
            self.last_wipe_notified = None
    
    # ========== КОМАНДЫ ==========
    
    @commands.command(name='admin')
    async def cmd_admin_panel(self, ctx):
        """Админ-панель"""
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ У вас нет прав администратора!", delete_after=5)
            return
        
        wipe = get_wipe_info()
        
        embed = discord.Embed(
            title="👑 АДМИН-ПАНЕЛЬ",
            description=f"**{RUST_SERVER_NAME}**",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        
        # Статус сервера
        embed.add_field(
            name="🖥️ СТАТУС СЕРВЕРА",
            value=f"🟢 Онлайн: **{self.server_status['online']}**\n"
                  f"🌙 Спят: **{self.server_status['sleeping']}**\n"
                  f"📊 Максимум: **{self.server_status['max']}**\n"
                  f"🔌 RCON: {'✅' if self.rcon else '❌'}",
            inline=False
        )
        
        # Информация о вайпе
        embed.add_field(
            name="💣 ВАЙП",
            value=f"📅 {wipe['date']}\n"
                  f"⏰ {wipe['time']}\n"
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
        
        embed.add_field(
            name="📊 ИНФОРМАЦИЯ",
            value="`!status` - Статус сервера\n"
                  "`!wipe` - Вайп\n"
                  "`!server` - Информация о сервере\n"
                  "`!help` - Помощь",
            inline=False
        )
        
        embed.set_footer(text=f"Администратор: {ctx.author.name}")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='status')
    async def cmd_status(self, ctx):
        """Статус сервера"""
        embed = discord.Embed(
            title="🖥️ СТАТУС СЕРВЕРА",
            description=f"**{RUST_SERVER_NAME}**",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="🎮 ИГРОКИ",
            value=f"{'🟢' if self.server_status['online'] > 0 else '🔴'} Онлайн: **{self.server_status['online']}**\n"
                  f"🌙 Спят: **{self.server_status['sleeping']}**\n"
                  f"📊 Максимум: **{self.server_status['max']}**",
            inline=False
        )
        
        embed.add_field(
            name="🌐 ПОДКЛЮЧЕНИЕ",
            value=f"IP: `{RUST_SERVER_IP}:{RUST_SERVER_PORT}`\n"
                  f"RCON: {'✅ Подключен' if self.rcon else '❌ Не подключен'}",
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
        
        # Прогресс бар
        total_seconds = 14 * 24 * 3600
        remaining_seconds = max(0, (wipe['timestamp'] - datetime.now()).total_seconds())
        progress = int((total_seconds - remaining_seconds) / total_seconds * 100)
        progress = min(100, max(0, progress))
        
        bar_length = 20
        filled = int(bar_length * progress / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        embed = discord.Embed(
            title="💣 ИНФОРМАЦИЯ О ВАЙПЕ",
            description=f"**{RUST_SERVER_NAME}**",
            color=discord.Color.purple(),
            timestamp=datetime.now()
        )
        
        embed.add_field(name="📅 ДАТА", value=wipe['date'], inline=True)
        embed.add_field(name="⏰ ВРЕМЯ", value=wipe['time'], inline=True)
        embed.add_field(name="🔄 ПЕРИОД", value="Каждые 2 недели", inline=True)
        embed.add_field(
            name="⏳ ОСТАЛОСЬ",
            value=f"{wipe['days']} д. {wipe['hours']} ч. {wipe['minutes']} мин.",
            inline=False
        )
        embed.add_field(name="📊 ПРОГРЕСС", value=f"`{bar}` {progress}%", inline=False)
        
        if wipe['is_first_thursday']:
            embed.add_field(
                name="⚠️ ВНИМАНИЕ",
                value="Это первый четверг месяца! Вайп в 22:00 МСК",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='server')
    async def cmd_server(self, ctx):
        """Информация о сервере"""
        embed = discord.Embed(
            title="ℹ️ ИНФОРМАЦИЯ О СЕРВЕРЕ",
            description=f"**{RUST_SERVER_NAME}**",
            color=discord.Color.gold()
        )
        
        embed.add_field(name="🎮 IP", value=f"`{RUST_SERVER_IP}:{RUST_SERVER_PORT}`", inline=False)
        embed.add_field(
            name="🔄 ВАЙП",
            value="Каждый четверг в 12:00 МСК\nПервый четверг месяца в 22:00 МСК",
            inline=False
        )
        embed.add_field(name="👥 ТИП", value="x2 | SOLO/DUO", inline=True)
        embed.add_field(name="👑 МАКС. ИГРОКОВ", value="50", inline=True)
        
        await ctx.send(embed=embed)
    
    # ========== КОМАНДЫ ЗАМЕТОК ==========
    
    @commands.command(name='note_create')
    async def cmd_note_create(self, ctx, title: str, *, content: str):
        """Создать заметку: !note_create Название Текст"""
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ У вас нет прав!", delete_after=5)
            return
        
        note_id = self.notes_manager.create_note(str(ctx.author.id), title, content)
        
        embed = discord.Embed(
            title="✅ ЗАМЕТКА СОЗДАНА",
            description=f"**#{note_id} - {title}**\n\n{content}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
    
    @commands.command(name='note_list')
    async def cmd_note_list(self, ctx):
        """Список заметок"""
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ У вас нет прав!", delete_after=5)
            return
        
        notes = self.notes_manager.get_notes(str(ctx.author.id))
        
        if not notes:
            await ctx.send("📭 У вас нет заметок. Используйте `!note create`")
            return
        
        embed = discord.Embed(
            title=f"📝 ВАШИ ЗАМЕТКИ ({len(notes)})",
            color=discord.Color.blue()
        )
        
        for note in notes[-10:]:
            reminder_text = ""
            if note.get('reminder_time'):
                rt = datetime.fromisoformat(note['reminder_time'])
                reminder_text = f"\n🔔 Напоминание: {rt.strftime('%d.%m.%Y %H:%M')}"
            
            embed.add_field(
                name=f"#{note['id']} - {note['title']}",
                value=f"{note['content'][:200]}{'...' if len(note['content']) > 200 else ''}{reminder_text}",
                inline=False
            )
        
        if len(notes) > 10:
            embed.set_footer(text=f"Показано 10 из {len(notes)} заметок")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='note_edit')
    async def cmd_note_edit(self, ctx, note_id: int, *, content: str):
        """Редактировать заметку: !note_edit ID Новый текст"""
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ У вас нет прав!", delete_after=5)
            return
        
        if self.notes_manager.update_note(str(ctx.author.id), note_id, content=content):
            await ctx.send(f"✅ Заметка #{note_id} обновлена!")
        else:
            await ctx.send(f"❌ Заметка #{note_id} не найдена!")
    
    @commands.command(name='note_delete')
    async def cmd_note_delete(self, ctx, note_id: int):
        """Удалить заметку: !note_delete ID"""
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ У вас нет прав!", delete_after=5)
            return
        
        if self.notes_manager.delete_note(str(ctx.author.id), note_id):
            await ctx.send(f"✅ Заметка #{note_id} удалена!")
        else:
            await ctx.send(f"❌ Заметка #{note_id} не найдена!")
    
    @commands.command(name='note_remind')
    async def cmd_note_remind(self, ctx, note_id: int, hours: int):
        """Установить напоминание: !note_remind ID Часы"""
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ У вас нет прав!", delete_after=5)
            return
        
        reminder_time = datetime.now() + timedelta(hours=hours)
        
        if self.notes_manager.update_note(str(ctx.author.id), note_id, reminder_time=reminder_time):
            await ctx.send(f"✅ Напоминание для заметки #{note_id} установлено на {reminder_time.strftime('%d.%m.%Y %H:%M')}")
        else:
            await ctx.send(f"❌ Заметка #{note_id} не найдена!")
    
    @commands.command(name='help')
    async def cmd_help(self, ctx):
        """Помощь по командам"""
        is_admin_user = await self.is_admin(ctx.author)
        
        embed = discord.Embed(
            title="🤖 ПОМОЩЬ ПО КОМАНДАМ",
            description=f"**{RUST_SERVER_NAME}**",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📊 ИНФОРМАЦИЯ",
            value="`!status` - Статус сервера\n"
                  "`!wipe` - Информация о вайпе\n"
                  "`!server` - Информация о сервере",
            inline=False
        )
        
        if is_admin_user:
            embed.add_field(
                name="👑 АДМИН-КОМАНДЫ",
                value="`!admin` - Админ-панель\n"
                      "`!note create <название> <текст>` - Создать заметку\n"
                      "`!note list` - Список заметок\n"
                      "`!note edit <id> <текст>` - Редактировать\n"
                      "`!note delete <id>` - Удалить\n"
                      "`!note remind <id> <часы>` - Напомнить",
                inline=False
            )
        else:
            embed.add_field(
                name="🔒 АДМИН-КОМАНДЫ",
                value="Доступны только администраторам сервера",
                inline=False
            )
        
        embed.set_footer(text="Бот автоматически уведомляет о вайпе в канал")
        
        await ctx.send(embed=embed)

# ========== ЗАПУСК ==========
def main():
    if not DISCORD_TOKEN:
        log.error("❌ DISCORD_TOKEN не задан! Проверьте .env файл")
        return
    
    bot = HostileAdminBot()
    
    try:
        bot.run(DISCORD_TOKEN)
    except discord.LoginFailure:
        log.error("❌ Неверный токен бота! Проверьте DISCORD_TOKEN")
    except Exception as e:
        log.error(f"❌ Ошибка запуска бота: {e}")

if __name__ == "__main__":
    main()
