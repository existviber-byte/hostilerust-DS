import os
from dotenv import load_dotenv

load_dotenv()

# Discord токен
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

# Webhook для отправки сообщений из игры в Discord
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# ID канала для игрового чата
GAME_CHAT_CHANNEL_ID = int(os.getenv('GAME_CHAT_CHANNEL_ID', 0))

# IP сервера x2
SERVER_IP = os.getenv('SERVER_IP', '37.230.137.6:20600')
SERVER_NAME = "HOSTILE RUST | x2 | SOLO/DUO"

# RCON настройки
RCON_HOST = os.getenv('RCON_HOST', '37.230.137.6')
RCON_PORT = int(os.getenv('RCON_PORT', 20602))
RCON_PASSWORD = os.getenv('RCON_PASSWORD', '')

# Ссылки
VK_GROUP_URL = os.getenv('VK_GROUP_URL', 'https://vk.com/hostile_rust')
DISCORD_INVITE = os.getenv('DISCORD_INVITE', 'https://discord.gg/invite')

# ID роли администратора (опционально)
ADMIN_ROLE_ID = int(os.getenv('ADMIN_ROLE_ID', 0))

# Эмодзи
EMOJIS = {
    'game': '🎮',
    'discord': '💬',
    'join': '🟢',
    'leave': '🔴',
    'error': '❌',
    'success': '✅',
    'warning': '⚠️',
    'wipe': '💣',
    'note': '📝',
    'admin': '👑',
    'ticket': '🎫'
}
