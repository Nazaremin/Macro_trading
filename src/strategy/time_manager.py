"""
Модуль для управления временными интервалами макросов.
"""
import datetime
import logging
from typing import Dict, List, Optional, Tuple

import pytz

class MacroTimeManager:
    """
    Управление временными интервалами макросов.
    Отслеживает активные макро-интервалы и время до следующего интервала.
    """
    
    def __init__(self, primary_intervals: Optional[List[Dict]] = None):
        """
        Инициализация менеджера временных интервалов.
        
        Args:
            primary_intervals: Список интервалов в формате 
                [{"start": "09:50", "end": "10:10", "name": "NY Morning"}, ...]
        """
        self.logger = logging.getLogger(__name__)
        
        # Стандартные интервалы по Нью-Йорку
        self.primary_intervals = primary_intervals or [
            {"start": "09:50", "end": "10:10", "name": "NY Morning"},
            {"start": "10:50", "end": "11:10", "name": "NY Mid-Morning"}
        ]
        
        # Временная зона Нью-Йорка
        self.timezone = pytz.timezone('America/New_York')
        
        self.logger.info(f"Time manager initialized with {len(self.primary_intervals)} intervals")
    
    def is_active_macro(self, tolerance_minutes: int = 2) -> Tuple[bool, Optional[str]]:
        """
        Проверяет, находимся ли мы в активном макро-интервале.
        
        Args:
            tolerance_minutes: Допустимое отклонение в минутах
            
        Returns:
            Tuple[bool, Optional[str]]: (активен ли макрос, название макроса)
        """
        ny_time = datetime.datetime.now(self.timezone)
        current_time_str = ny_time.strftime("%H:%M")
        
        for interval in self.primary_intervals:
            # Проверка с учетом допустимого отклонения
            if self._is_time_in_range(current_time_str, interval["start"], interval["end"], tolerance_minutes):
                self.logger.debug(f"Active macro detected: {interval['name']}")
                return True, interval["name"]
        
        return False, None
    
    def time_to_next_macro(self) -> int:
        """
        Возвращает время до следующего макро-интервала в минутах.
        
        Returns:
            int: Количество минут до следующего макро-интервала
        """
        ny_time = datetime.datetime.now(self.timezone)
        current_minutes = ny_time.hour * 60 + ny_time.minute
        
        # Преобразуем все интервалы в минуты от начала дня
        interval_minutes = []
        for interval in self.primary_intervals:
            start_hour, start_minute = map(int, interval["start"].split(":"))
            start_minutes = start_hour * 60 + start_minute
            interval_minutes.append(start_minutes)
        
        # Сортируем интервалы
        interval_minutes.sort()
        
        # Находим ближайший интервал
        next_interval = None
        for minutes in interval_minutes:
            if minutes > current_minutes:
                next_interval = minutes
                break
        
        # Если нет интервалов сегодня, берем первый на завтра
        if next_interval is None and interval_minutes:
            next_interval = interval_minutes[0] + 24 * 60
        
        # Вычисляем разницу в минутах
        if next_interval is not None:
            minutes_to_next = next_interval - current_minutes
            self.logger.debug(f"Next macro in {minutes_to_next} minutes")
            return minutes_to_next
        
        # Если интервалы не заданы
        self.logger.warning("No macro intervals defined")
        return 0
    
    def _is_time_in_range(self, current_time: str, start_time: str, end_time: str, 
                         tolerance_minutes: int = 0) -> bool:
        """
        Проверяет, находится ли текущее время в заданном диапазоне.
        
        Args:
            current_time: Текущее время в формате "HH:MM"
            start_time: Начало интервала в формате "HH:MM"
            end_time: Конец интервала в формате "HH:MM"
            tolerance_minutes: Допустимое отклонение в минутах
            
        Returns:
            bool: True, если время в диапазоне, иначе False
        """
        # Преобразуем все времена в минуты от начала дня
        current_hour, current_minute = map(int, current_time.split(":"))
        current_minutes = current_hour * 60 + current_minute
        
        start_hour, start_minute = map(int, start_time.split(":"))
        start_minutes = start_hour * 60 + start_minute
        
        end_hour, end_minute = map(int, end_time.split(":"))
        end_minutes = end_hour * 60 + end_minute
        
        # Учитываем допустимое отклонение
        adjusted_start = start_minutes - tolerance_minutes
        adjusted_end = end_minutes + tolerance_minutes
        
        return adjusted_start <= current_minutes <= adjusted_end
