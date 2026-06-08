import discord
from discord.ext import commands
from datetime import datetime, timedelta
from config import *

class GameChatCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return
        if message.channel.id == GAME_CHAT_CHANNEL_ID:
            if not message.content.startswith('!'):
                await message.add_reaction('✅')

    @commands.command(name='ip')
    async def cmd_ip(self, ctx):
        await ctx.send(f"IP сервера: `{SERVER_IP}`")

    @commands.command(name='info')
    async def cmd_info(self, ctx):
        embed = discord.Embed(title=f"Информация о {SERVER_NAME}", color=discord.Color.gold())
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
        await ctx.send(f"Следующий вайп: {next_wipe.strftime('%d.%m.%Y в 12:00')}\nОсталось: {delta.days} д. {delta.seconds//3600} ч.")

    @commands.command(name='help_bot')
    async def cmd_help(self, ctx):
        embed = discord.Embed(title="Команды", color=discord.Color.blue())
        embed.add_field(name="!ip", value="IP сервера")
        embed.add_field(name="!info", value="Информация")
        embed.add_field(name="!wipe", value="Вайп")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(GameChatCog(bot))
