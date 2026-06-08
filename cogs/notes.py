import discord
from discord.ext import commands
from datetime import datetime
import json
from pathlib import Path

from config import *


class NotesCog(commands.Cog):
    """Команды для заметок"""
    
    def __init__(self, bot):
        self.bot = bot
        self.notes_file = Path("data/notes.json")
        self.load_notes()
    
    def load_notes(self):
        """Загрузка заметок из файла"""
        if self.notes_file.exists():
            with open(self.notes_file, 'r', encoding='utf-8') as f:
                self.notes = json.load(f)
        else:
            self.notes = {}
    
    def save_notes(self):
        """Сохранение заметок в файл"""
        self.notes_file.parent.mkdir(exist_ok=True)
        with open(self.notes_file, 'w', encoding='utf-8') as f:
            json.dump(self.notes, f, indent=2, ensure_ascii=False)
    
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
    
    @commands.command(name='note_create')
    async def create_note(self, ctx, title: str, *, content: str):
        """Создать заметку: !note_create Название Текст заметки"""
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ У вас нет прав администратора!", delete_after=5)
            return
        
        user_id = str(ctx.author.id)
        if user_id not in self.notes:
            self.notes[user_id] = []
        
        note = {
            'id': len(self.notes[user_id]) + 1,
            'title': title,
            'content': content,
            'created_at': datetime.now().isoformat()
        }
        
        self.notes[user_id].append(note)
        self.save_notes()
        
        embed = discord.Embed(
            title="✅ ЗАМЕТКА СОЗДАНА",
            description=f"**#{note['id']} - {title}**\n\n{content}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
    
    @commands.command(name='note_list')
    async def list_notes(self, ctx):
        """Список заметок"""
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ У вас нет прав администратора!", delete_after=5)
            return
        
        user_id = str(ctx.author.id)
        notes = self.notes.get(user_id, [])
        
        if not notes:
            await ctx.send("📭 У вас нет заметок. Используйте `!note_create`")
            return
        
        embed = discord.Embed(
            title=f"📝 ВАШИ ЗАМЕТКИ ({len(notes)})",
            color=discord.Color.blue()
        )
        
        for note in notes[-10:]:
            embed.add_field(
                name=f"#{note['id']} - {note['title']}",
                value=note['content'][:100] + ('...' if len(note['content']) > 100 else ''),
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='note_delete')
    async def delete_note(self, ctx, note_id: int):
        """Удалить заметку: !note_delete ID"""
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ У вас нет прав администратора!", delete_after=5)
            return
        
        user_id = str(ctx.author.id)
        notes = self.notes.get(user_id, [])
        
        for i, note in enumerate(notes):
            if note['id'] == note_id:
                notes.pop(i)
                # Перенумеровываем заметки
                for j, n in enumerate(notes):
                    n['id'] = j + 1
                self.save_notes()
                await ctx.send(f"✅ Заметка #{note_id} удалена!")
                return
        
        await ctx.send(f"❌ Заметка #{note_id} не найдена!")
    
    @commands.command(name='note_edit')
    async def edit_note(self, ctx, note_id: int, *, content: str):
        """Редактировать заметку: !note_edit ID Новый текст"""
        if not await self.is_admin(ctx.author):
            await ctx.send("❌ У вас нет прав администратора!", delete_after=5)
            return
        
        user_id = str(ctx.author.id)
        notes = self.notes.get(user_id, [])
        
        for note in notes:
            if note['id'] == note_id:
                note['content'] = content
                self.save_notes()
                await ctx.send(f"✅ Заметка #{note_id} обновлена!")
                return
        
        await ctx.send(f"❌ Заметка #{note_id} не найдена!")


async def setup(bot):
    await bot.add_cog(NotesCog(bot))
