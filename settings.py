#!/usr/bin/env python3
"""
Settings management for GitHub tools using SQLite database.
Securely stores tokens, paths, and configuration.
"""

import sqlite3
import json
from pathlib import Path
from typing import Any, Optional, Dict
from cryptography.fernet import Fernet
import base64
import os

class SettingsManager:
    """Secure settings storage using SQLite with encryption for sensitive data."""
    
    def __init__(self, db_path: str = "settings.db"):
        self.db_path = Path(db_path)
        self.encryption_key = self._get_or_create_encryption_key()
        self.cipher = Fernet(self.encryption_key)
        self._init_database()
        
    def _get_or_create_encryption_key(self) -> bytes:
        """Get or create encryption key for sensitive data."""
        key_file = self.db_path.parent / ".key"
        
        if key_file.exists():
            return key_file.read_bytes()
        else:
            key = Fernet.generate_key()
            key_file.write_bytes(key)
            key_file.chmod(0o600)  # Restrict permissions
            return key
            
    def _init_database(self):
        """Initialize the settings database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    encrypted BOOLEAN DEFAULT FALSE,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS profiles (
                    name TEXT PRIMARY KEY,
                    settings TEXT NOT NULL,
                    active BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            
    def _encrypt_value(self, value: str) -> str:
        """Encrypt sensitive values."""
        return self.cipher.encrypt(value.encode()).decode()
        
    def _decrypt_value(self, encrypted_value: str) -> str:
        """Decrypt sensitive values."""
        return self.cipher.decrypt(encrypted_value.encode()).decode()
        
    def set(self, key: str, value: Any, encrypted: bool = False, description: str = None):
        """Set a configuration value."""
        str_value = json.dumps(value) if not isinstance(value, str) else value
        
        if encrypted:
            str_value = self._encrypt_value(str_value)
            
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO settings (key, value, encrypted, description, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (key, str_value, encrypted, description))
            conn.commit()
            
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT value, encrypted FROM settings WHERE key = ?", (key,)
            )
            row = cursor.fetchone()
            
        if not row:
            return default
            
        value, encrypted = row
        
        if encrypted:
            value = self._decrypt_value(value)
            
        # Try to parse as JSON, fallback to string
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
            
    def delete(self, key: str) -> bool:
        """Delete a configuration value."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            conn.commit()
            return cursor.rowcount > 0
            
    def list_settings(self) -> Dict[str, Dict[str, Any]]:
        """List all settings (without decrypting sensitive values)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT key, encrypted, description, created_at, updated_at
                FROM settings ORDER BY key
            """)
            
            settings = {}
            for row in cursor.fetchall():
                key, encrypted, description, created_at, updated_at = row
                settings[key] = {
                    'encrypted': bool(encrypted),
                    'description': description,
                    'created_at': created_at,
                    'updated_at': updated_at
                }
                
        return settings
        
    def create_profile(self, name: str, settings_dict: Dict[str, Any]):
        """Create a settings profile."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO profiles (name, settings, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (name, json.dumps(settings_dict)))
            conn.commit()
            
    def load_profile(self, name: str) -> Optional[Dict[str, Any]]:
        """Load a settings profile."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT settings FROM profiles WHERE name = ?", (name,))
            row = cursor.fetchone()
            
        if row:
            return json.loads(row[0])
        return None
        
    def set_active_profile(self, name: str):
        """Set the active profile."""
        with sqlite3.connect(self.db_path) as conn:
            # Deactivate all profiles
            conn.execute("UPDATE profiles SET active = FALSE")
            # Activate the specified profile
            conn.execute("UPDATE profiles SET active = TRUE WHERE name = ?", (name,))
            conn.commit()
            
    def get_active_profile(self) -> Optional[str]:
        """Get the active profile name."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT name FROM profiles WHERE active = TRUE")
            row = cursor.fetchone()
            
        return row[0] if row else None

    # Convenience methods for common settings
    def set_github_token(self, token: str):
        """Set GitHub token (encrypted)."""
        self.set('github_token', token, encrypted=True, description='GitHub Personal Access Token')
        
    def get_github_token(self) -> Optional[str]:
        """Get GitHub token."""
        return self.get('github_token')
        
    def set_backup_directory(self, path: str):
        """Set default backup directory."""
        self.set('backup_directory', path, description='Default backup directory path')
        
    def get_backup_directory(self) -> str:
        """Get backup directory."""
        return self.get('backup_directory', './backups')
        
    def set_default_org(self, org: str):
        """Set default organization."""
        self.set('default_org', org, description='Default GitHub organization')
        
    def get_default_org(self) -> Optional[str]:
        """Get default organization."""
        return self.get('default_org')
        
    def set_parallel_workers(self, count: int):
        """Set number of parallel workers."""
        self.set('parallel_workers', count, description='Number of parallel backup workers')
        
    def get_parallel_workers(self) -> int:
        """Get number of parallel workers."""
        return self.get('parallel_workers', 4)