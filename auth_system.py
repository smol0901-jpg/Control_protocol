"""
Система авторизации и управления пользователями
"""
import json
import hashlib
import secrets
import base64
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import bcrypt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from dataclasses import dataclass, asdict
import threading
import time


@dataclass
class User:
    """Модель пользователя"""
    username: str
    password_hash: str
    role: str  # 'admin', 'developer', 'viewer'
    created_at: str
    last_login: Optional[str] = None
    login_count: int = 0
    permissions: List[str] = None
    
    def __post_init__(self):
        if self.permissions is None:
            self.permissions = []


@dataclass
class Session:
    """Сессия пользователя"""
    username: str
    token: str
    created_at: str
    expires_at: str
    ip_address: str = "localhost"


class AuthSystem:
    """Система авторизации"""
    
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        self.users_file = self.config_dir / "users.json"
        self.sessions_file = self.config_dir / "sessions.json"
        self.key_file = self.config_dir / ".encryption_key"
        
        # Инициализация шифрования
        self.cipher = self._init_encryption()
        
        # Загрузка данных
        self.users: Dict[str, User] = self._load_users()
        self.sessions: Dict[str, Session] = self._load_sessions()
        
        # Блокировка для потокобезопасности
        self.lock = threading.Lock()
        
        # Создаем админа по умолчанию если нет пользователей
        if not self.users:
            self._create_default_admin()
        
        # Запускаем очистку просроченных сессий
        self._start_session_cleaner()
    
    def _init_encryption(self) -> Fernet:
        """Инициализация шифрования"""
        if self.key_file.exists():
            with open(self.key_file, 'rb') as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            # Защита файла ключа
            import os
            os.chmod(self.key_file, 0o600)
        
        return Fernet(key)
    
    def _load_users(self) -> Dict[str, User]:
        """Загрузка пользователей"""
        if not self.users_file.exists():
            return {}
        
        try:
            with open(self.users_file, 'rb') as f:
                encrypted_data = f.read()
            
            decrypted_data = self.cipher.decrypt(encrypted_data)
            users_data = json.loads(decrypted_data)
            
            return {
                username: User(**data)
                for username, data in users_data.items()
            }
        except Exception as e:
            print(f"Ошибка загрузки пользователей: {e}")
            return {}
    
    def _save_users(self):
        """Сохранение пользователей"""
        try:
            users_data = {
                username: asdict(user)
                for username, user in self.users.items()
            }
            
            json_data = json.dumps(users_data, indent=2)
            encrypted_data = self.cipher.encrypt(json_data.encode())
            
            with open(self.users_file, 'wb') as f:
                f.write(encrypted_data)
        except Exception as e:
            print(f"Ошибка сохранения пользователей: {e}")
    
    def _load_sessions(self) -> Dict[str, Session]:
        """Загрузка сессий"""
        if not self.sessions_file.exists():
            return {}
        
        try:
            with open(self.sessions_file, 'r') as f:
                sessions_data = json.load(f)
            
            return {
                token: Session(**data)
                for token, data in sessions_data.items()
            }
        except:
            return {}
    
    def _save_sessions(self):
        """Сохранение сессий"""
        try:
            sessions_data = {
                token: asdict(session)
                for token, session in self.sessions.items()
            }
            
            with open(self.sessions_file, 'w') as f:
                json.dump(sessions_data, f, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения сессий: {e}")
    
    def _create_default_admin(self):
        """Создание администратора по умолчанию"""
        admin = User(
            username="admin",
            password_hash=self._hash_password("admin123!"),
            role="admin",
            created_at=datetime.now().isoformat(),
            permissions=["all"]
        )
        self.users["admin"] = admin
        self._save_users()
        print("Создан администратор по умолчанию: admin / admin123!")
    
    def _hash_password(self, password: str) -> str:
        """Хеширование пароля"""
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode(), salt).decode()
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Проверка пароля"""
        try:
            return bcrypt.checkpw(password.encode(), password_hash.encode())
        except:
            return False
    
    def _generate_token(self) -> str:
        """Генерация токена сессии"""
        return secrets.token_hex(32)
    
    def _start_session_cleaner(self):
        """Запуск очистки просроченных сессий"""
        def cleaner():
            while True:
                time.sleep(300)  # Каждые 5 минут
                self._clean_expired_sessions()
        
        thread = threading.Thread(target=cleaner, daemon=True)
        thread.start()
    
    def _clean_expired_sessions(self):
        """Очистка просроченных сессий"""
        with self.lock:
            now = datetime.now()
            expired = []
            
            for token, session in self.sessions.items():
                expires_at = datetime.fromisoformat(session.expires_at)
                if now > expires_at:
                    expired.append(token)
            
            for token in expired:
                del self.sessions[token]
            
            if expired:
                self._save_sessions()
    
    def login(self, username: str, password: str, ip_address: str = "localhost") -> Optional[str]:
        """
        Авторизация пользователя
        Возвращает токен сессии или None
        """
        with self.lock:
            if username not in self.users:
                return None
            
            user = self.users[username]
            
            if not self._verify_password(password, user.password_hash):
                return None
            
            # Обновляем информацию о пользователе
            user.last_login = datetime.now().isoformat()
            user.login_count += 1
            self._save_users()
            
            # Создаем сессию
            token = self._generate_token()
            session = Session(
                username=username,
                token=token,
                created_at=datetime.now().isoformat(),
                expires_at=(datetime.now() + timedelta(hours=24)).isoformat(),
                ip_address=ip_address
            )
            
            self.sessions[token] = session
            self._save_sessions()
            
            return token
    
    def logout(self, token: str) -> bool:
        """Выход из системы"""
        with self.lock:
            if token in self.sessions:
                del self.sessions[token]
                self._save_sessions()
                return True
            return False
    
    def validate_session(self, token: str) -> Optional[User]:
        """Проверка сессии"""
        with self.lock:
            if token not in self.sessions:
                return None
            
            session = self.sessions[token]
            expires_at = datetime.fromisoformat(session.expires_at)
            
            if datetime.now() > expires_at:
                del self.sessions[token]
                self._save_sessions()
                return None
            
            return self.users.get(session.username)
    
    def create_user(self, admin_token: str, username: str, password: str, 
                   role: str = "viewer", permissions: List[str] = None) -> bool:
        """
        Создание нового пользователя (только для админа)
        """
        admin = self.validate_session(admin_token)
        if not admin or admin.role != "admin":
            return False
        
        with self.lock:
            if username in self.users:
                return False
            
            if permissions is None:
                permissions = []
            
            user = User(
                username=username,
                password_hash=self._hash_password(password),
                role=role,
                created_at=datetime.now().isoformat(),
                permissions=permissions or []
            )
            
            self.users[username] = user
            self._save_users()
            return True
    
    def delete_user(self, admin_token: str, username: str) -> bool:
        """Удаление пользователя"""
        admin = self.validate_session(admin_token)
        if not admin or admin.role != "admin":
            return False
        
        with self.lock:
            if username not in self.users or username == "admin":
                return False
            
            del self.users[username]
            self._save_users()
            
            # Удаляем сессии пользователя
            sessions_to_delete = []
            for token, session in self.sessions.items():
                if session.username == username:
                    sessions_to_delete.append(token)
            
            for token in sessions_to_delete:
                del self.sessions[token]
            self._save_sessions()
            
            return True
    
    def get_user_info(self, token: str) -> Optional[Dict]:
        """Получение информации о пользователе"""
        user = self.validate_session(token)
        if not user:
            return None
        
        return {
            "username": user.username,
            "role": user.role,
            "login_count": user.login_count,
            "last_login": user.last_login,
            "permissions": user.permissions
        }
    
    def change_password(self, token: str, old_password: str, new_password: str) -> bool:
        """Смена пароля"""
        user = self.validate_session(token)
        if not user:
            return False
        
        with self.lock:
            if not self._verify_password(old_password, user.password_hash):
                return False
            
            user.password_hash = self._hash_password(new_password)
            self._save_users()
            return True


# Декоратор для проверки авторизации
def require_auth(auth_system: AuthSystem):
    """Декоратор для функций требующих авторизации"""
    def decorator(func):
        def wrapper(token, *args, **kwargs):
            user = auth_system.validate_session(token)
            if not user:
                raise PermissionError("Требуется авторизация")
            return func(user, *args, **kwargs)
        return wrapper
    return decorator