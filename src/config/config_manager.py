"""
Модуль для управления конфигурацией бота.
"""
import json
import logging
import os
from typing import Dict, Any

class ConfigManager:
    """
    Менеджер конфигурации.
    Загружает и сохраняет настройки бота.
    """
    
    def __init__(self, config_path: str):
        """
        Инициализация менеджера конфигурации.
        
        Args:
            config_path: Путь к конфигурационному файлу
        """
        self.logger = logging.getLogger(__name__)
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """
        Загрузка конфигурации из файла.
        
        Returns:
            Dict[str, Any]: Конфигурация
        """
        try:
            # Проверяем, существует ли директория
            config_dir = os.path.dirname(self.config_path)
            if not os.path.exists(config_dir):
                os.makedirs(config_dir)
                
            # Проверяем, существует ли файл
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                    self.logger.info(f"Configuration loaded from {self.config_path}")
                    return config
            else:
                # Создание конфигурации по умолчанию
                default_config = {
                    "api_key": "",
                    "api_secret": "",
                    "testnet": True,
                    "symbols": ["BTCUSDT", "ETHUSDT"],
                    "risk_per_trade": 0.02,
                    "check_interval": 60,
                    "macro_intervals": [
                        {"start": "09:50", "end": "10:10", "name": "NY Morning"},
                        {"start": "10:50", "end": "11:10", "name": "NY Mid-Morning"}
                    ],
                    "logging_level": "INFO"
                }
                
                self._save_config(default_config)
                self.logger.info(f"Default configuration created at {self.config_path}")
                return default_config
                
        except Exception as e:
            self.logger.error(f"Error loading configuration: {str(e)}")
            # В случае ошибки возвращаем базовую конфигурацию
            return {
                "api_key": "",
                "api_secret": "",
                "testnet": True,
                "symbols": ["BTCUSDT"],
                "risk_per_trade": 0.02,
                "check_interval": 60,
                "macro_intervals": [
                    {"start": "09:50", "end": "10:10", "name": "NY Morning"},
                    {"start": "10:50", "end": "11:10", "name": "NY Mid-Morning"}
                ],
                "logging_level": "INFO"
            }
    
    def _save_config(self, config: Dict[str, Any] = None) -> None:
        """
        Сохранение конфигурации в файл.
        
        Args:
            config: Конфигурация для сохранения
        """
        if config is None:
            config = self.config
        
        try:
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=4)
                self.logger.info(f"Configuration saved to {self.config_path}")
        except Exception as e:
            self.logger.error(f"Error saving configuration: {str(e)}")
    
    def update_config(self, key: str, value: Any) -> None:
        """
        Обновление значения в конфигурации.
        
        Args:
            key: Ключ
            value: Значение
        """
        self.config[key] = value
        self._save_config()
        self.logger.info(f"Configuration updated: {key} = {value}")
    
    def get_config(self) -> Dict[str, Any]:
        """
        Получение текущей конфигурации.
        
        Returns:
            Dict[str, Any]: Конфигурация
        """
        return self.config
