#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import discord
from discord.ext import commands
import logging
import sys
import os
from datetime import datetime, timedelta
from config import *

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler('discord_bot.log'),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)


class HostileRustBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(command_prefix='!', intents=intents)
        
        self.game_channel = None
        self.webhook = None
        self.start_time = datetime.now()
    
    async def setup_hook(self):
        """Загрузка всех команд из папки cogs"""
        # Загружаем все коги из папки cogs
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and filename != '__init__.py':
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    log.info(f"✅ Загружен ког: {filename}")
                except Exception as e:
                    log.error(f"❌ Ошибка загрузки {filename}: {e}")
        
        # Настраиваем канал и вебхук
        self.game_channel = self.get_channel(GAME_CHAT_CHANNEL_ID)
        if self.game_channel:
            webhooks = await self.game_channel.webhooks()
            if webhooks:
                self.webhook = webhooks[0]
            else:
                self.webhook = await self.game_channel.create_webhook(name="Rust Game Chat")
            log.info("✅ Webhook настроен")
        else:
            log.error(f"❌ Канал с ID {GAME_CHAT_CHANNEL_ID} не найден!")
    
    async def on_ready(self):
        log.info("=" * 50)
        log.info(f"✅ Бот {self.user.name} запущен!")
        log.info(f"📊 ID бота: {self.user.id}")
        log.info(f"🌐 Команды загружены: {len(self.commands)}")
        log.info("=" * 50)
        
        # Устанавливаем статус
        await self.change_presence(
            activity=discord.Game(name=f"x2 | {SERVER_IP}"),
            status=discord.Status.online
        )
        
        # Отправляем приветствие
        if self.game_channel:
            embed = discord.Embed(
                title="✅ БОТ ЗАПУЩЕН",
                description=f"Связь с сервером **{SERVER_NAME}** установлена!\n\n"
                           f"🎮 **IP:** `{SERVER_IP}`\n"
                           f"🔄 **Вайп:** Каждый четверг в 12:00 МСК\n\n"
                           f"📝 **Доступные команды:**\n"
                           f"• `!ip` - IP сервера\n"
                           f"• `!info` - Информация\n"
                           f"• `!wipe` - Вайп\n"
                           f"• `!help_bot` - Помощь\n\n"
                           f"💬 Пиши в этом канале - сообщения улетят в игру!",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            await self.game_channel.send(embed=embed)
    
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        
        # Обрабатываем команды
        await self.process_commands(message)
        
        # Пересылаем сообщения в игру (если не команда)
        if message.channel.id == GAME_CHAT_CHANNEL_ID and not message.content.startswith('!'):
            await message.add_reaction('✅')
            log.info(f"📨 Из Discord в игру: {message.author.display_name}: {message.clean_content}")
            print(f"[DISCORD] {message.author.display_name}: {message.clean_content}")
    
    async def on_member_join(self, member: discord.Member):
        if self.game_channel:
            embed = discord.Embed(
                title="🟢 ДОБРО ПОЖАЛОВАТЬ!",
                description=f"{member.mention} присоединился к серверу!\n\n"
                           f"**{SERVER_NAME}** ждет тебя!\n"
                           f"🎮 IP: `{SERVER_IP}`\n\n"
                           f"Используй `!help_bot` для списка команд",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            await self.game_channel.send(embed=embed)
        
        try:
            dm_embed = discord.Embed(
                title=f"Добро пожаловать на {SERVER_NAME}!",
                description=f"Приветствуем тебя, {member.name}! 🎮\n\n"
                           f"**IP сервера:** `{SERVER_IP}`\n\n"
                           f"**Как подключиться?**\n"
                           f"1. Скопируй IP\n"
                           f"2. В Rust нажми F1\n"
                           f"3. Введи: `client.connect {SERVER_IP}`\n\n"
                           f"💬 **Чат:** Пиши в канале - сообщения увидят в игре!\n\n"
                           f"🔗 **VK:** {VK_GROUP_URL}",
                color=discord.Color.gold()
            )
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            pass


def main():
    bot = HostileRustBot()
    
    try:
        bot.run(DISCORD_TOKEN)
    except discord.LoginFailure:
        log.error("❌ Неверный токен бота! Проверьте DISCORD_TOKEN в .env")
        sys.exit(1)
    except Exception as e:
        log.error(f"❌ Ошибка запуска бота: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
