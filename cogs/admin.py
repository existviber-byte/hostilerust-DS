import discord
from discord.ext import commands
from datetime import datetime

from config import *


class AdminCog(commands.Cog):
    """Админ-команды"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def is_admin(self, user: discord.User) -> bool:
        """Проверка прав администратора"""
        if ADMIN_ROLE_ID == 0:
            return False
        
        guild = self.bot.get_channel(GAME_CHAT_CHANNEL_ID).guild
        if not guild:
            return False
        
        member = guild.get_member(user.id)
        if not member:
            return False
        
        if member.guild_permissions.administrator:
            return True
        
        admin_role = guild.get_role(ADMIN_ROLE_ID)
        if admin_role and admin_role in member.roles:
            return True
        
        return False
    
    @commands.command(name='admin')
    async def admin_panel(self, ctx):
        """Админ-панель"""
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ У вас нет прав администратора!", delete_after=5)
            return
        
        embed = discord.Embed(
            title="👑 АДМИН-ПАНЕЛЬ",
            description="Выберите действие:",
            color=discord.Color.gold(),
            timestamp=datetime.now()
        )
        embed.add_field(
            name="📝 Заметки", 
            value="`!note_create` - Создать\n`!note_list` - Список\n`!note_delete` - Удалить", 
            inline=True
        )
        embed.add_field(
            name="📊 Статистика", 
            value="`!stats` - Показать статистику", 
            inline=True
        )
        embed.add_field(
            name="🔄 Обновить статус", 
            value="`!status` - Обновить статус бота", 
            inline=True
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='stats')
    async def show_stats(self, ctx):
        """Показать статистику бота"""
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ У вас нет прав администратора!", delete_after=5)
            return
        
        uptime = datetime.now() - self.bot.start_time
        hours = uptime.seconds // 3600
        minutes = (uptime.seconds % 3600) // 60
        
        embed = discord.Embed(
            title="📊 СТАТИСТИКА БОТА",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        embed.add_field(name="⏰ Аптайм", value=f"{uptime.days} д. {hours} ч. {minutes} мин.", inline=True)
        embed.add_field(name="👥 Серверов", value=len(self.bot.guilds), inline=True)
        embed.add_field(name="💬 Канал", value=f"<#{GAME_CHAT_CHANNEL_ID}>", inline=True)
        
        await ctx.send(embed=embed)
    
    @commands.command(name='status')
    async def update_status(self, ctx):
        """Обновить статус бота"""
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ У вас нет прав администратора!", delete_after=5)
            return
        
        await self.bot.change_presence(
            activity=discord.Game(name=f"x2 | {SERVER_IP}"),
            status=discord.Status.online
        )
        await ctx.send("✅ Статус бота обновлен!")


async def setup(bot):
    await bot.add_cog(AdminCog(bot))
