import socket
import struct
import logging

log = logging.getLogger(__name__)


class RCONClient:
    def __init__(self, host, port, password):
        self.host = host
        self.port = port
        self.password = password
        self.socket = None
    
    def connect(self):
        """Подключение к RCON"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)
            self.socket.connect((self.host, self.port))
            
            packet_id = 1
            packet_type = 3
            
            body = self.password
            packet = struct.pack('<ii', packet_id, packet_type) + body.encode('utf-8') + b'\x00\x00'
            packet_len = len(packet)
            self.socket.send(struct.pack('<i', packet_len) + packet)
            
            response = self._receive_packet()
            if response and response['type'] == 2:
                log.info("Подключен к RCON")
                return True
            
            return False
        except Exception as e:
            log.error(f"Ошибка RCON: {e}")
            return False
    
    def _receive_packet(self):
        """Получение пакета"""
        try:
            len_data = self.socket.recv(4)
            if len(len_data) < 4:
                return None
            packet_len = struct.unpack('<i', len_data)[0]
            packet = self.socket.recv(packet_len)
            packet_id, packet_type = struct.unpack('<ii', packet[:8])
            body = packet[8:-2].decode('utf-8')
            return {'id': packet_id, 'type': packet_type, 'body': body}
        except Exception as e:
            log.error(f"Ошибка получения пакета: {e}")
            return None
    
    def send_chat_message(self, message):
        """Отправка сообщения в чат"""
        command = f'say "{message}"'
        return self._send_command(command)
    
    def _send_command(self, command):
        """Отправка команды"""
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
            response = self._receive_packet()
            return response['body'] if response else None
        except Exception as e:
            log.error(f"Ошибка отправки команды: {e}")
            return None
    
    def close(self):
        if self.socket:
            self.socket.close()
            self.socket = None
