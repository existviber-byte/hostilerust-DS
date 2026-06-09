#!/usr/bin/env python3
"""
Hostile Admin Bot - Discord бот для администрации Rust сервера
Функции:
- Управление заметками с напоминаниями
- Мониторинг сервера (онлайн, вайпы)
- Уведомления о вайпе
"""

import discord
from discord.ext import commands, tasks
import asyncio
import aiohttp
import json
import logging
import os
import socket
import struct
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# ========== НАСТРОЙКИ ==========
# Discord
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
ADMIN_ROLE_ID = int(os.getenv('ADMIN_ROLE_ID', 0))
NOTIFICATION_CHANNEL_ID = int(os.getenv('NOTIFICATION_CHANNEL_ID', 0))

# Сервер Rust
RUST_SERVER_IP = os.getenv('RUST_SERVER_IP', '37.230.137.6')
RUST_SERVER_PORT = int(os.getenv('RUST_SERVER_PORT', 20602))
RUST_SERVER_PASSWORD = os.getenv('RUST_SERVER_PASSWORD', '')
RUST_SERVER_NAME = os.getenv('RUST_SERVER_NAME', 'HOSTILE RUST | x2 | SOLO/DUO')

# Настройки
WIPE_DAY = int(os.getenv('WIPE_DAY', 3))  # 3 = Thursday (0=Monday, 3=Thursday)
WIPE_HOUR = int(os.getenv('WIPE_HOUR', 12))  # 12:00 MSK (обычный четверг)
WIPE_SPECIAL_HOUR = int(os.getenv('WIPE_SPECIAL_HOUR', 22))  # 22:00 для первого четверга месяца

# Эмодзи
EMOJIS = {
    'online': '🟢',
    'sleeping': '🌙',
    'offline': '🔴',
    'wipe': '💣',
    'note': '📝',
    'admin': '👑',
    'success': '✅',
    'error': '❌',
    'warning': '⚠️',
    'clock': '⏰',
    'server': '🖥️'
}

# ========== ЛОГИРОВАНИЕ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('admin_bot.log'),
        logging.StreamHandler()
    ]
)
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
            
            # Аутентификация
            packet_id = 1
            packet_type = 3
            body = self.password
            packet = struct.pack('<ii', packet_id, packet_type) + body.encode('utf-8') + b'\x00\x00'
            packet_len = len(packet)
            self.socket.send(struct.pack('<i', packet_len) + packet)
            
            # Получаем ответ
            len_data = self.socket.recv(4)
            if len(len_data) < 4:
                return False
            packet_len = struct.unpack('<i', len_data)[0]
            self.socket.recv(packet_len)
            
            log.info("RCON подключен")
            return True
        except Exception as e:
            log.error(f"RCON ошибка подключения: {e}")
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
            
            # Получаем ответ
            len_data = self.socket.recv(4)
            if len(len_data) < 4:
                return None
            packet_len = struct.unpack('<i', len_data)[0]
            response = self.socket.recv(packet_len)
            
            if len(response) > 8:
                return response[8:-2].decode('utf-8')
            return None
        except Exception as e:
            log.error(f"RCON ошибка команды: {e}")
            return None
    
    def get_server_status(self) -> Dict:
        """Получение статуса сервера"""
        result = self.send_command("status")
        if not result:
            return {'players_online': 0, 'players_sleeping': 0, 'players_max': 0, 'server_info': 'Нет данных'}
        
        lines = result.split('\n')
        players_online = 0
        players_sleeping = 0
        players_max = 0
        
        # Парсим статус
        for line in lines:
            if 'connected' in line.lower() and 'players' in line.lower():
                # Формат: "Connected players: 5/50" или подобное
                import re
                numbers = re.findall(r'\d+', line)
                if len(numbers) >= 2:
                    players_online = int(numbers[0])
                    players_max = int(numbers[1])
            elif 'sleeping' in line.lower():
                numbers = re.findall(r'\d+', line)
                if numbers:
                    players_sleeping = int(numbers[0])
        
        return {
            'players_online': players_online,
            'players_sleeping': players_sleeping,
            'players_max': players_max,
            'server_info': result[:500] if result else 'Нет данных'
        }
    
    def close(self):
        if self.socket:
            self.socket.close()
            self.socket = None

# ========== УПРАВЛЕНИЕ ЗАМЕТКАМИ ==========
class NotesManager:
    def __init__(self, data_file: str = "data/notes.json"):
        self.data_file = Path(data_file)
        self.notes: Dict[str, List[Dict]] = {}
        self.load()
    
    def load(self):
        """Загрузка заметок из файла"""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    self.notes = json.load(f)
                log.info(f"Загружено заметок для {len(self.notes)} пользователей")
            except Exception as e:
                log.error(f"Ошибка загрузки заметок: {e}")
                self.notes = {}
        else:
            self.data_file.parent.mkdir(exist_ok=True)
            self.save()
    
    def save(self):
        """Сохранение заметок в файл"""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.notes, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.error(f"Ошибка сохранения заметок: {e}")
    
    def create_note(self, user_id: str, title: str, content: str, reminder_time: Optional[datetime] = None) -> int:
        """Создание заметки"""
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
        """Получение всех заметок пользователя"""
        return self.notes.get(user_id, [])
    
    def get_note(self, user_id: str, note_id: int) -> Optional[Dict]:
        """Получение конкретной заметки"""
        for note in self.notes.get(user_id, []):
            if note['id'] == note_id:
                return note
        return None
    
    def update_note(self, user_id: str, note_id: int, title: str = None, content: str = None, reminder_time: datetime = None) -> bool:
        """Обновление заметки"""
        for note in self.notes.get(user_id, []):
            if note['id'] == note_id:
                if title is not None:
                    note['title'] = title
                if content is not None:
                    note['content'] = content
                if reminder_time is not None:
                    note['reminder_time'] = reminder_time.isoformat()
                    note['is_reminded'] = False
                note['updated_at'] = datetime.now().isoformat()
                self.save()
                return True
        return False
    
    def delete_note(self, user_id: str, note_id: int) -> bool:
        """Удаление заметки"""
        notes = self.notes.get(user_id, [])
        for i, note in enumerate(notes):
            if note['id'] == note_id:
                notes.pop(i)
                # Перенумерация
                for j, n in enumerate(notes):
                    n['id'] = j + 1
                self.save()
                return True
        return False
    
    def get_due_reminders(self) -> List[Tuple[str, Dict]]:
        """Получение просроченных напоминаний"""
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
        """Отметить напоминание как отправленное"""
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
    """Расчет следующей даты вайпа"""
    now = datetime.now()
    
    # Находим следующий четверг
    days_until_thursday = (WIPE_DAY - now.weekday()) % 7
    if days_until_thursday == 0 and now.hour >= WIPE_HOUR:
        days_until_thursday = 7
    
    next_wipe = now + timedelta(days=days_until_thursday)
    
    # Определяем время вайпа
    if is_first_thursday(next_wipe):
        wipe_hour = WIPE_SPECIAL_HOUR
        wipe_type = "специальный (22:00)"
    else:
        wipe_hour = WIPE_HOUR
        wipe_type = "обычный (12:00)"
    
    next_wipe = next_wipe.replace(hour=wipe_hour, minute=0, second=0, microsecond=0)
    
    return next_wipe

def get_wipe_info() -> dict:
    """Получение информации о вайпе"""
    next_wipe = get_next_wipe()
    now = datetime.now()
    delta = next_wipe - now
    
    is_first = is_first_thursday(next_wipe)
    
    return {
        'date': next_wipe.strftime('%d.%m.%Y'),
        'time': "22:00 МСК" if is_first else "12:00 МСК",
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
        self.notification_channel: Optional[discord.TextChannel] = None
        self.last_wipe_notified = None
        self.server_status = {'players_online': 0, 'players_sleeping': 0, 'players_max': 0}
    
    async def setup_hook(self):
        """Настройка при запуске"""
        # Подключаем RCON
        if RUST_SERVER_PASSWORD:
            self.rcon = RCONClient(RUST_SERVER_IP, RUST_SERVER_PORT, RUST_SERVER_PASSWORD)
            await asyncio.get_event_loop().run_in_executor(None, self.rcon.connect)
            log.info("RCON инициализирован")
        else:
            log.warning("RCON пароль не задан! Статус сервера не будет обновляться")
        
        # Получаем канал для уведомлений
        if NOTIFICATION_CHANNEL_ID:
            self.notification_channel = self.get_channel(NOTIFICATION_CHANNEL_ID)
            if self.notification_channel:
                log.info(f"Канал уведомлений: #{self.notification_channel.name}")
            else:
                log.warning(f"Канал с ID {NOTIFICATION_CHANNEL_ID} не найден!")
        
        # Запускаем задачи
        self.update_server_status.start()
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
        
        # Обновляем статус
        await self.update_bot_status()
        
        # Отправляем приветствие админу
        if self.notification_channel:
            embed = discord.Embed(
                title=f"{EMOJIS['success']} БОТ ЗАПУЩЕН",
                description=f"**{RUST_SERVER_NAME}**\n"
                           f"IP: `{RUST_SERVER_IP}:{RUST_SERVER_PORT}`\n\n"
                           f"Доступные команды: `!help_admin`",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            await self.notification_channel.send(embed=embed)
    
    async def update_bot_status(self):
        """Обновление статуса бота"""
        wipe_info = get_wipe_info()
        status_text = f"x2 | {RUST_SERVER_IP} | вайп: {wipe_info['date']}"
        await self.change_presence(activity=discord.Game(name=status_text))
    
    # ========== ФОНОВЫЕ ЗАДАЧИ ==========
    
    @tasks.loop(minutes=5)
    async def update_server_status(self):
        """Обновление статуса сервера (каждые 5 минут)"""
        if not self.rcon:
            return
        
        try:
            status = await asyncio.get_event_loop().run_in_executor(
                None, self.rcon.get_server_status
            )
            self.server_status = status
            
            # Обновляем название канала (если нужно)
            if self.notification_channel:
                # Можно обновлять название канала с онлайном
                pass
            
            log.info(f"Статус сервера: {status['players_online']}/{status['players_max']} игроков ({status['players_sleeping']} спят)")
        except Exception as e:
            log.error(f"Ошибка обновления статуса: {e}")
    
    @tasks.loop(minutes=1)
    async def check_reminders(self):
        """Проверка напоминаний (каждую минуту)"""
        due_reminders = self.notes_manager.get_due_reminders()
        
        for user_id_str, note in due_reminders:
            try:
                user_id = int(user_id_str)
                user = await self.fetch_user(user_id)
                if user:
                    embed = discord.Embed(
                        title=f"{EMOJIS['note']} НАПОМИНАНИЕ",
                        description=f"**{note['title']}**\n\n{note['content']}",
                        color=discord.Color.blue(),
                        timestamp=datetime.now()
                    )
                    embed.set_footer(text=f"Заметка #{note['id']}")
                    await user.send(embed=embed)
                    self.notes_manager.mark_reminded(user_id_str, note['id'])
                    log.info(f"Отправлено напоминание пользователю {user_id}: {note['title']}")
            except Exception as e:
                log.error(f"Ошибка отправки напоминания: {e}")
    
    @tasks.loop(hours=1)
    async def check_wipe_notification(self):
        """Проверка и отправка уведомления о вайпе (каждый час)"""
        if not self.notification_channel:
            return
        
        wipe_info = get_wipe_info()
        
        # Уведомление за 1 день до вайпа
        if wipe_info['days'] == 1 and wipe_info['hours'] <= 12:
            if self.last_wipe_notified != '1day':
                embed = discord.Embed(
                    title=f"{EMOJIS['wipe']} ВАЙП ЗАВТРА!",
                    description=f"**{RUST_SERVER_NAME}**\n\n"
                               f"📅 Дата: {wipe_info['date']}\n"
                               f"⏰ Время: {wipe_info['time']}\n\n"
                               f"⚠️ Не забудьте подготовиться!",
                    color=discord.Color.orange(),
                    timestamp=datetime.now()
                )
                await self.notification_channel.send(embed=embed)
                self.last_wipe_notified = '1day'
                log.info("Отправлено уведомление о вайпе за день")
        
        # Уведомление за 1 час до вайпа
        elif wipe_info['days'] == 0 and wipe_info['hours'] <= 1:
            if self.last_wipe_notified != '1hour':
                embed = discord.Embed(
                    title=f"{EMOJIS['warning']} ВАЙП ЧЕРЕЗ ЧАС!",
                    description=f"**{RUST_SERVER_NAME}**\n\n"
                               f"⏰ Вайп в {wipe_info['time']}\n\n"
                               f"🔄 Сервер будет перезагружен!",
                    color=discord.Color.red(),
                    timestamp=datetime.now()
                )
                await self.notification_channel.send(embed=embed)
                self.last_wipe_notified = '1hour'
                log.info("Отправлено уведомление о вайпе за час")
        
        # Уведомление о начале вайпа
        elif wipe_info['days'] == 0 and wipe_info['hours'] == 0 and wipe_info['minutes'] <= 10:
            if self.last_wipe_notified != 'now':
                embed = discord.Embed(
                    title=f"{EMOJIS['wipe']} НАЧАЛСЯ ВАЙП!",
                    description=f"**{RUST_SERVER_NAME}**\n\n"
                               f"🔄 Сервер перезагружается...\n"
                               f"💫 Скоро сервер снова будет доступен!",
                    color=discord.Color.purple(),
                    timestamp=datetime.now()
                )
                await self.notification_channel.send(embed=embed)
                self.last_wipe_notified = 'now'
                log.info("Отправлено уведомление о начале вайпа")
        
        # Сбрасываем флаг после вайпа
        elif wipe_info['days'] > 1:
            self.last_wipe_notified = None
    
    # ========== КОМАНДЫ АДМИНА ==========
    
    async def is_admin(self, user: discord.User) -> bool:
        """Проверка прав администратора"""
        if ADMIN_ROLE_ID == 0:
            return True  # Если роль не задана, доступ есть у всех
        
        for guild in self.guilds:
            member = guild.get_member(user.id)
            if member:
                admin_role = guild.get_role(ADMIN_ROLE_ID)
                if admin_role and admin_role in member.roles:
                    return True
                if member.guild_permissions.administrator:
                    return True
        return False
    
    @commands.command(name='admin')
    async def admin_panel(self, ctx):
        """Админ-панель"""
        if not await self.is_admin(ctx.author):
            await ctx.send(f"{EMOJIS['error']} У вас нет прав администратора!", delete_after=5)
            return
        
        embed = discord.Embed(
            title=f"{EMOJIS['admin']} АДМИН-ПАНЕЛЬ",
            description=f"**{RUST_SERVER_NAME}**",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        
        # Статус сервера
        embed.add_field(
            name="🎮 СТАТУС СЕРВЕРА",
            value=f"🟢 Онлайн: {self.server_status['players_online']}\n"
                  f"🌙 Спят: {self.server_status['players_sleeping']}\n"
                  f"📊 Макс: {self.server_status['players_max']}",
            inline=False
        )
        
        # Информация о вайпе
        wipe = get_wipe_info()
        embed.add_field(
            name=f"{EMOJIS['wipe']} ВАЙП",
            value=f"📅 {wipe['date']}\n"
                  f"⏰ {wipe['time']}\n"
                  f"⏳ Осталось: {wipe['days']} д. {wipe['hours']} ч. {wipe['minutes']} мин.",
            inline=False
        )
        
        # Команды
        embed.add_field(
            name="📝 ЗАМЕТКИ",
            value="`!note create <название> <текст>` - Создать заметку\n"
                  "`!note list` - Список заметок\n"
                  "`!note edit <id> <новый текст>` - Редактировать\n"
                  "`!note delete <id>` - Удалить\n"
                  "`!note remind <id> <часы>` - Установить напоминание",
            inline=False
        )
        
        embed.add_field(
            name="🔧 ДРУГИЕ КОМАНДЫ",
            value="`!status` - Статус сервера\n"
                  "`!wipe` - Информация о вайпе\n"
                  "`!server` - Информация о сервере\n"
                  "`!help_admin` - Помощь",
            inline=False
        )
        
        embed.set_footer(text=f"Администратор: {ctx.author.name}")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='status')
    async def server_status_cmd(self, ctx):
        """Статус сервера"""
        embed = discord.Embed(
            title=f"{EMOJIS['server']} СТАТУС СЕРВЕРА",
            description=f"**{RUST_SERVER_NAME}**",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name="🎮 ИГРОКИ",
            value=f"{EMOJIS['online']} Онлайн: **{self.server_status['players_online']}**\n"
                  f"{EMOJIS['sleeping']} Спят: **{self.server_status['players_sleeping']}**\n"
                  f"📊 Максимум: **{self.server_status['players_max']}**",
            inline=False
        )
        
        embed.add_field(
            name="🌐 ПОДКЛЮЧЕНИЕ",
            value=f"IP: `{RUST_SERVER_IP}:{RUST_SERVER_PORT}`\n"
                  f"RCON: {'✅ Подключен' if self.rcon else '❌ Не подключен'}",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='wipe')
    async def wipe_info_cmd(self, ctx):
        """Информация о вайпе"""
        wipe = get_wipe_info()
        
        # Прогресс бар
        total_seconds = 14 * 24 * 3600  # 2 недели в секундах
        remaining_seconds = (wipe['timestamp'] - datetime.now()).total_seconds()
        progress = max(0, min(100, int((total_seconds - remaining_seconds) / total_seconds * 100)))
        
        bar_length = 20
        filled = int(bar_length * progress / 100)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        embed = discord.Embed(
            title=f"{EMOJIS['wipe']} ИНФОРМАЦИЯ О ВАЙПЕ",
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
        embed.add_field(
            name="📊 ПРОГРЕСС",
            value=f"`{bar}` {progress}%",
            inline=False
        )
        
        if wipe['is_first_thursday']:
            embed.add_field(
                name="⚠️ ВНИМАНИЕ",
                value="Это первый четверг месяца! Вайп в 22:00 МСК",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='server')
    async def server_info_cmd(self, ctx):
        """Информация о сервере"""
        embed = discord.Embed(
            title=f"ℹ️ ИНФОРМАЦИЯ О СЕРВЕРЕ",
            description=f"**{RUST_SERVER_NAME}**",
            color=discord.Color.gold()
        )
        
        embed.add_field(name="🎮 IP", value=f"`{RUST_SERVER_IP}:{RUST_SERVER_PORT}`", inline=False)
        embed.add_field(name="🔄 ВАЙП", value="Каждый четверг в 12:00 МСК\nПервый четверг месяца в 22:00 МСК", inline=False)
        embed.add_field(name="👥 МАКСИМУМ ИГРОКОВ", value="50", inline=True)
        embed.add_field(name="🌍 ТИП", value="x2 | SOLO/DUO", inline=True)
        
        await ctx.send(embed=embed)
    
    # ========== КОМАНДЫ ЗАМЕТОК ==========
    
    @commands.command(name='note_create')
    async def note_create(self, ctx, title: str, *, content: str):
        """Создать заметку: !note_create Название Текст"""
        if not await self.is_admin(ctx.author):
            await ctx.send(f"{EMOJIS['error']} У вас нет прав!", delete_after=5)
            return
        
        note_id = self.notes_manager.create_note(str(ctx.author.id), title, content)
        
        embed = discord.Embed(
            title=f"{EMOJIS['success']} ЗАМЕТКА СОЗДАНА",
            description=f"**#{note_id} - {title}**\n\n{content}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
    
    @commands.command(name='note_list')
    async def note_list(self, ctx):
        """Список заметок"""
        if not await self.is_admin(ctx.author):
            await ctx.send(f"{EMOJIS['error']} У вас нет прав!", delete_after=5)
            return
        
        notes = self.notes_manager.get_notes(str(ctx.author.id))
        
        if not notes:
            await ctx.send(f"{EMOJIS['note']} У вас нет заметок. Используйте `!note create`")
            return
        
        embed = discord.Embed(
            title=f"{EMOJIS['note']} ВАШИ ЗАМЕТКИ ({len(notes)})",
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
    async def note_edit(self, ctx, note_id: int, *, content: str):
        """Редактировать заметку: !note_edit ID Новый текст"""
        if not await self.is_admin(ctx.author):
            await ctx.send(f"{EMOJIS['error']} У вас нет прав!", delete_after=5)
            return
        
        if self.notes_manager.update_note(str(ctx.author.id), note_id, content=content):
            await ctx.send(f"{EMOJIS['success']} Заметка #{note_id} обновлена!")
        else:
            await ctx.send(f"{EMOJIS['error']} Заметка #{note_id} не найдена!")
    
    @commands.command(name='note_delete')
    async def note_delete(self, ctx, note_id: int):
        """Удалить заметку: !note_delete ID"""
        if not await self.is_admin(ctx.author):
            await ctx.send(f"{EMOJIS['error']} У вас нет прав!", delete_after=5)
            return
        
        if self.notes_manager.delete_note(str(ctx.author.id), note_id):
            await ctx.send(f"{EMOJIS['success']} Заметка #{note_id} удалена!")
        else:
            await ctx.send(f"{EMOJIS['error']} Заметка #{note_id} не найдена!")
    
    @commands.command(name='note_remind')
    async def note_remind(self, ctx, note_id: int, hours: int):
        """Установить напоминание для заметки: !note_remind ID Часы"""
        if not await self.is_admin(ctx.author):
            await ctx.send(f"{EMOJIS['error']} У вас нет прав!", delete_after=5)
            return
        
        reminder_time = datetime.now() + timedelta(hours=hours)
        
        if self.notes_manager.update_note(str(ctx.author.id), note_id, reminder_time=reminder_time):
            await ctx.send(f"{EMOJIS['success']} Напоминание для заметки #{note_id} установлено на {reminder_time.strftime('%d.%m.%Y %H:%M')}")
        else:
            await ctx.send(f"{EMOJIS['error']} Заметка #{note_id} не найдена!")
    
    # ========== ВСПОМОГАТЕЛЬНЫЕ КОМАНДЫ ==========
    
    @commands.command(name='help_admin')
    async def help_admin(self, ctx):
        """Помощь по командам"""
        embed = discord.Embed(
            title="🤖 ПОМОЩЬ ПО КОМАНДАМ",
            description=f"**{RUST_SERVER_NAME}**",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📊 ИНФОРМАЦИЯ",
            value="`!admin` - Админ-панель\n"
                  "`!status` - Статус сервера\n"
                  "`!wipe` - Информация о вайпе\n"
                  "`!server` - Информация о сервере",
            inline=False
        )
        
        embed.add_field(
            name="📝 ЗАМЕТКИ",
            value="`!note create <название> <текст>` - Создать\n"
                  "`!note list` - Список\n"
                  "`!note edit <id> <текст>` - Редактировать\n"
                  "`!note delete <id>` - Удалить\n"
                  "`!note remind <id> <часы>` - Напоминание",
            inline=False
        )
        
        embed.add_field(
            name="🔔 УВЕДОМЛЕНИЯ",
            value="Бот автоматически уведомит о вайпе:\n"
                  "• За 1 день до вайпа\n"
                  "• За 1 час до вайпа\n"
                  "• В момент вайпа",
            inline=False
        )
        
        await ctx.send(embed=embed)

# ========== ЗАПУСК ==========
def main():
    bot = HostileAdminBot()
    
    try:
        bot.run(DISCORD_TOKEN)
    except discord.LoginFailure:
        log.error("❌ Неверный токен бота! Проверьте DISCORD_TOKEN в .env")
    except Exception as e:
        log.error(f"❌ Ошибка запуска бота: {e}")

if __name__ == "__main__":
    main()
