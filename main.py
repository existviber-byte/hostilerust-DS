#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Hostile Rust Discord Bot
Бот для связи чата Discord с игровым сервером Rust (x2)
"""

import discord
from discord.ext import commands, tasks
import asyncio
import logging
import sys
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
        """Настройка при запуске"""
        # Получаем канал для чата
        self.game_channel = self.get_channel(GAME_CHAT_CHANNEL_ID)
        if self.game_channel:
            webhooks = await self.game_channel.webhooks()
            if webhooks:
                self.webhook = webhooks[0]
            else:
                self.webhook = await self.game_channel.create_webhook(name="Rust Game Chat")
            log.info("✅ Webhook для игрового чата настроен")
        else:
            log.error(f"❌ Канал с ID {GAME_CHAT_CHANNEL_ID} не найден!")
    
    async def on_ready(self):
        """Событие при запуске"""
        log.info("=" * 50)
        log.info(f"✅ Бот {self.user.name} запущен!")
        log.info(f"📊 ID бота: {self.user.id}")
        log.info(f"🌐 Сервер: {SERVER_NAME}")
        log.info(f"🌐 IP: {SERVER_IP}")
        log.info("=" * 50)
        
        # Устанавливаем статус
        await self.change_presence(
            activity=discord.Game(name=f"x2 | {SERVER_IP}"),
            status=discord.Status.online
        )
        
        # Отправляем приветствие в канал
        if self.game_channel:
            embed = discord.Embed(
                title="✅ БОТ ЗАПУЩЕН",
                description=f"Связь с сервером **{SERVER_NAME}** установлена!\n\n"
                           f"📌 **Как это работает:**\n"
                           f"• Сообщения из игры будут появляться здесь\n"
                           f"• Твои сообщения в этом канале будут отправляться в игру\n\n"
                           f"🎮 **IP сервера:** `{SERVER_IP}`\n\n"
                           f"🔄 **Вайп:** Каждый четверг в 12:00 МСК\n\n"
                           f"🔗 **Полезные ссылки:**\n"
                           f"• VK: {VK_GROUP_URL}",
                color=discord.Color.green(),
                timestamp=datetime.now()
            )
            await self.game_channel.send(embed=embed)
    
    async def on_message(self, message: discord.Message):
        """Обработка сообщений в Discord"""
        if message.author.bot:
            return
        
        if message.channel.id != GAME_CHAT_CHANNEL_ID:
            return
        
        # Игнорируем команды
        if message.content.startswith('!'):
            await self.process_commands(message)
            return
        
        # Отправляем подтверждение
        await message.add_reaction('✅')
        
        # Логируем сообщение
        log.info(f"📨 Из Discord в игру: {message.author.display_name}: {message.clean_content}")
        
        # TODO: Отправка в игру через RCON (будет добавлено позже)
        # Сейчас просто выводим в консоль
        print(f"[DISCORD] {message.author.display_name}: {message.clean_content}")
        
        await self.process_commands(message)
    
    async def on_member_join(self, member: discord.Member):
        """Приветствие нового участника"""
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
        
        # Отправляем ЛС новичку
        try:
            dm_embed = discord.Embed(
                title=f"Добро пожаловать на {SERVER_NAME}!",
                description=f"Приветствуем тебя, {member.name}! 🎮\n\n"
                           f"**IP сервера:** `{SERVER_IP}`\n\n"
                           f"**Как подключиться?**\n"
                           f"1. Скопируй IP сервера\n"
                           f"2. В Rust нажми F1\n"
                           f"3. Введи: `client.connect {SERVER_IP}`\n\n"
                           f"**Чат с игроками:**\n"
                           f"Пиши сообщения в этом канале - их увидят в игре!\n\n"
                           f"🔗 **Наша группа VK:** {VK_GROUP_URL}",
                color=discord.Color.gold()
            )
            await member.send(embed=dm_embed)
        except discord.Forbidden:
            log.warning(f"Не удалось отправить ЛС пользователю {member.name}")
    
    # ========== КОМАНДЫ ==========
    
    @commands.command(name='ip')
    async def cmd_ip(self, ctx):
        """Показать IP сервера"""
        embed = discord.Embed(
            title="🎮 IP СЕРВЕРА",
            description=f"`{SERVER_IP}`\n\n"
                       f"**Как подключиться:**\n"
                       f"1. Скопируй IP\n"
                       f"2. В игре нажми F1\n"
                       f"3. Введи: `client.connect {SERVER_IP}`",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
    
    @commands.command(name='info')
    async def cmd_info(self, ctx):
        """Информация о сервере"""
        embed = discord.Embed(
            title=f"ℹ️ ИНФОРМАЦИЯ О {SERVER_NAME}",
            color=discord.Color.gold()
        )
        embed.add_field(name="🎮 IP сервера", value=f"`{SERVER_IP}`", inline=False)
        embed.add_field(name="🔄 Вайп", value="Каждый четверг в 12:00 МСК\nПервый четверг месяца в 22:00 МСК", inline=False)
        embed.add_field(name="💬 Чат", value="Общайся с игроками в этом канале!", inline=False)
        embed.add_field(name="🔗 VK", value=f"[Наша группа]({VK_GROUP_URL})", inline=True)
        await ctx.send(embed=embed)
    
    @commands.command(name='wipe')
    async def cmd_wipe(self, ctx):
        """Информация о вайпе"""
        now = datetime.now()
        
        # Находим следующий четверг
        days_until_thursday = (3 - now.weekday()) % 7
        if days_until_thursday == 0 and now.hour >= 12:
            days_until_thursday = 7
        
        next_thursday = now + timedelta(days=days_until_thursday)
        
        # Проверяем первый четверг месяца
        is_first = next_thursday.day <= 7 and next_thursday.weekday() == 3
        wipe_time = "22:00" if is_first else "12:00"
        
        next_wipe = next_thursday.replace(hour=12 if not is_first else 22, minute=0, second=0, microsecond=0)
        
        delta = next_wipe - now
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        
        embed = discord.Embed(
            title="💣 ИНФОРМАЦИЯ О ВАЙПЕ",
            description=f"**{SERVER_NAME}**",
            color=discord.Color.purple()
        )
        embed.add_field(name="📅 Дата", value=next_wipe.strftime('%d.%m.%Y'), inline=True)
        embed.add_field(name="⏰ Время", value=f"{wipe_time} МСК", inline=True)
        embed.add_field(name="⏳ Осталось", value=f"{days} д. {hours} ч. {minutes} мин.", inline=False)
        embed.add_field(name="🔄 Периодичность", value="Раз в 2 недели", inline=False)
        
        if is_first:
            embed.add_field(name="⚠️ Важно", value="Первый четверг месяца — вайп в 22:00!", inline=False)
        
        await ctx.send(embed=embed)
    
    @commands.command(name='help_bot')
    async def cmd_help(self, ctx):
        """Помощь по боту"""
        embed = discord.Embed(
            title="🤖 ПОМОЩЬ ПО БОТУ",
            description="Бот для связи чата Discord с игровым сервером Rust",
            color=discord.Color.blue()
        )
        embed.add_field(name="!ip", value="Показать IP сервера", inline=False)
        embed.add_field(name="!info", value="Информация о сервере", inline=False)
        embed.add_field(name="!wipe", value="Информация о вайпе", inline=False)
        embed.add_field(name="!help_bot", value="Показать эту справку", inline=False)
        embed.add_field(name="💬 Чат", value="Просто пиши в этот канал - сообщения улетят в игру!", inline=False)
        await ctx.send(embed=embed)


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
