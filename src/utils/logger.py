"""
Модуль для настройки логирования.
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

def setup_logger(name: str, log_level: str = "INFO", log_file: str = None) -> logging.Logger:
    """
    Настройка логгера.
    
    Args:
        name: Имя логгера
        log_level: Уровень логирования
        log_file: Путь к файлу логов
        
    Returns:
        logging.Logger: Настроенный логгер
    """
    # Создаем логгер
    logger = logging.getLogger(name)
    
    # Устанавливаем уровень логирования
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)
    
    # Если логгер уже настроен, возвращаем его
    if logger.handlers:
        return logger
    
    # Формат логов
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Обработчик для вывода в консоль
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Обработчик для записи в файл
    if log_file:
        # Создаем директорию для логов, если она не существует
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        # Настраиваем ротацию логов (максимум 5 файлов по 5 МБ)
        file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger
