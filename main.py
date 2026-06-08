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
            self.socket.settimeout(5)
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
            
            log.info("RCON подключен успешно")
            return True
        except Exception as e:
            log.error(f"RCON ошибка при подключении: {e}")
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
            
            # Получаем ответ
            len_data = self.socket.recv(4)
            if len(len_data) < 4:
                return None
            packet_len = struct.unpack('<i', len_data)[0]
            response = self.socket.recv(packet_len)
            
            # Парсим ответ
            if len(response) > 8:
                body = response[8:-2].decode('utf-8')
                return body
            return None
        except Exception as e:
            log.error(f"Ошибка отправки RCON команды: {e}")
            return None
    
    def send_chat_message(self, message):
        """Отправка сообщения в игровой чат"""
        # Экранируем кавычки
        message = message.replace('"', '\\"')
        command = f'say "{message}"'
        return self.send_command(command)
    
    def close(self):
        if self.socket:
            self.socket.close()
            self.socket = None

class HostileRustBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(command_prefix='!', intents=intents)
        
        self.game_channel = None
        self.webhook = None
        self.rcon = None
        self.start_time = datetime.now()
    
    async def setup_hook(self):
        # Настраиваем канал
        self.game_channel = self.get_channel(GAME_CHAT_CHANNEL_ID)
        if self.game_channel:
            webhooks = await self.game_channel.webhooks()
            if webhooks:
                self.webhook = webhooks[0]
            else:
                self.webhook = await self.game_channel.create_webhook(name="Rust Game Chat")
            log.info("Webhook настроен")
        
        # Подключаемся к RCON
        if RCON_PASSWORD:
            self.rcon = RCONClient(RCON_HOST, RCON_PORT, RCON_PASSWORD)
            await asyncio.get_event_loop().run_in_executor(None, self.rcon.connect)
            log.info("RCON инициализирован")
        else:
            log.warning("RCON пароль не задан! Сообщения из Discord не будут уходить в игру")
    
    async def on_ready(self):
        log.info("=" * 50)
        log.info(f"Бот {self.user.name} запущен!")
        log.info(f"Сервер: {SERVER_NAME}")
        log.info(f"IP: {SERVER_IP}")
        log.info(f"RCON: {'Подключен' if self.rcon else 'Не настроен'}")
        log.info("=" * 50)
        
        await self.change_presence(activity=discord.Game(name=f"x2 | {SERVER_IP}"))
        
        # Отправляем приветствие в канал
        if self.game_channel:
            embed = discord.Embed(
                title="✅ БОТ ЗАПУЩЕН",
                description=f"Связь с сервером установлена!\n\n"
                           f"🎮 IP: `{SERVER_IP}`\n"
                           f"💬 Пишите в этом канале - сообщения уйдут в игру!",
                color=discord.Color.green()
            )
            await self.game_channel.send(embed=embed)
    
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        
        if message.channel.id != GAME_CHAT_CHANNEL_ID:
            await self.process_commands(message)
            return
        
        if message.content.startswith('!'):
            await self.process_commands(message)
            return
        
        # Отправляем в игру
        if self.rcon:
            game_message = f"[DISCORD] {message.author.display_name}: {message.clean_content}"
            
            # Отправляем через RCON
            result = await asyncio.get_event_loop().run_in_executor(
                None, self.rcon.send_chat_message, game_message
            )
            
            if result is not None:
                await message.add_reaction('✅')
                log.info(f"В игру: {message.author.display_name}: {message.clean_content}")
            else:
                await message.add_reaction('❌')
                log.error(f"Не удалось отправить в игру: {message.author.display_name}: {message.clean_content}")
        else:
            await message.add_reaction('⚠️')
            log.warning("RCON не настроен - сообщение не отправлено")
    
    # Команды
    @commands.command(name='ip')
    async def cmd_ip(self, ctx):
        await ctx.send(f"🎮 IP сервера: `{SERVER_IP}`")
    
    @commands.command(name='info')
    async def cmd_info(self, ctx):
        embed = discord.Embed(title=f"ℹ️ {SERVER_NAME}", color=discord.Color.gold())
        embed.add_field(name="IP", value=f"`{SERVER_IP}`")
        embed.add_field(name="Вайп", value="Каждый четверг в 12:00 МСК")
        await ctx.send(embed=embed)
    
    @commands.command(name='wipe')
    async def cmd_wipe(self, ctx):
        now = datetime.now()
        days = (3 - now.weekday()) % 7
        if days == 0 and now.hour >= 12:
            days = 7
        next_wipe = now + timedelta(days=days)
        next_wipe = next_wipe.replace(hour=12, minute=0)
        delta = next_wipe - now
        await ctx.send(f"💣 Следующий вайп: {next_wipe.strftime('%d.%m.%Y в 12:00')}\n⏳ Осталось: {delta.days} д. {delta.seconds//3600} ч.")
    
    @commands.command(name='rcon')
    async def cmd_rcon_test(self, ctx):
        """Проверка RCON подключения"""
        if not self.rcon:
            await ctx.send("❌ RCON не настроен! Добавьте переменные: RCON_HOST, RCON_PORT, RCON_PASSWORD")
            return
        
        await ctx.send("🔄 Проверка RCON подключения...")
        
        result = await asyncio.get_event_loop().run_in_executor(
            None, self.rcon.send_command, "status"
        )
        
        if result:
            await ctx.send(f"✅ RCON работает!\n```{result[:500]}```")
        else:
            await ctx.send("❌ RCON не отвечает! Проверьте:\n1. RCON включен в server.cfg\n2. Правильный порт\n3. Правильный пароль")
    
    @commands.command(name='help_bot')
    async def cmd_help(self, ctx):
        embed = discord.Embed(title="🤖 Команды", color=discord.Color.blue())
        embed.add_field(name="!ip", value="IP сервера")
        embed.add_field(name="!info", value="Информация о сервере")
        embed.add_field(name="!wipe", value="Информация о вайпе")
        embed.add_field(name="!rcon", value="Проверка RCON (админ)")
        await ctx.send(embed=embed)

if __name__ == "__main__":
    bot = HostileRustBot()
    bot.run(DISCORD_TOKEN)
