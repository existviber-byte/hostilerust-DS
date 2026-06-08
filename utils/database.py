import sqlite3
from pathlib import Path
from datetime import datetime
import logging

log = logging.getLogger(__name__)


class Database:
    def __init__(self):
        self.data_dir = Path("data")
        self.data_dir.mkdir(exist_ok=True)
        self.db_path = self.data_dir / "bot.db"
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_db(self):
        """Инициализация базы данных"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                author TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE DEFAULT CURRENT_DATE,
                messages_count INTEGER DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()
        log.info("База данных инициализирована")
    
    def add_message(self, source, author, message):
        """Добавление сообщения в лог"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO messages (source, author, message)
            VALUES (?, ?, ?)
        ''', (source, author, message))
        conn.commit()
        conn.close()
    
    def get_stats(self):
        """Получение статистики"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM messages')
        total = cursor.fetchone()[0]
        conn.close()
        return {'total_messages': total}
