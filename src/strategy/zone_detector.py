"""
Модуль для определения зон интереса на рынке.
"""
import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

class InterestZoneDetector:
    """
    Детектор зон интереса на рынке.
    Выявляет ордерблоки, зоны дисбаланса и точки предыдущих импульсов.
    """
    
    def __init__(self):
        """
        Инициализация детектора зон интереса.
        """
        self.logger = logging.getLogger(__name__)
    
    def find_order_blocks(self, candles: List[Dict], direction: str = "bullish") -> List[Dict]:
        """
        Поиск ордерблоков в заданном направлении.
        
        Args:
            candles: Список свечей
            direction: Направление ('bullish' или 'bearish')
            
        Returns:
            List[Dict]: Список ордерблоков
        """
        order_blocks = []
        
        if len(candles) < 4:
            return order_blocks
        
        if direction == "bullish":
            # Поиск бычьих ордерблоков
            # Обычно это последняя свеча перед импульсом вверх
            for i in range(1, len(candles) - 2):
                if (candles[i+1]['close'] > candles[i+1]['open'] and  # Бычья свеча
                    candles[i+2]['close'] > candles[i+1]['close'] and  # Продолжение движения
                    candles[i]['close'] < candles[i]['open']):  # Медвежья свеча перед импульсом
                    
                    order_block = {
                        "type": "bullish",
                        "high": candles[i]['high'],
                        "low": candles[i]['low'],
                        "strength": self._calculate_ob_strength(candles, i, "bullish"),
                        "index": i
                    }
                    order_blocks.append(order_block)
        
        elif direction == "bearish":
            # Поиск медвежьих ордерблоков
            for i in range(1, len(candles) - 2):
                if (candles[i+1]['close'] < candles[i+1]['open'] and  # Медвежья свеча
                    candles[i+2]['close'] < candles[i+1]['close'] and  # Продолжение движения
                    candles[i]['close'] > candles[i]['open']):  # Бычья свеча перед импульсом
                    
                    order_block = {
                        "type": "bearish",
                        "high": candles[i]['high'],
                        "low": candles[i]['low'],
                        "strength": self._calculate_ob_strength(candles, i, "bearish"),
                        "index": i
                    }
                    order_blocks.append(order_block)
        
        # Сортируем по силе
        order_blocks.sort(key=lambda x: x["strength"], reverse=True)
        
        self.logger.debug(f"Found {len(order_blocks)} {direction} order blocks")
        return order_blocks
    
    def _calculate_ob_strength(self, candles: List[Dict], index: int, direction: str) -> float:
        """
        Расчет силы ордерблока.
        
        Args:
            candles: Список свечей
            index: Индекс свечи с ордерблоком
            direction: Направление ('bullish' или 'bearish')
            
        Returns:
            float: Сила ордерблока
        """
        # Базовая сила
        strength = 1.0
        
        # Увеличиваем силу, если ордерблок не был пробит
        was_broken = False
        
        if direction == "bullish":
            # Для бычьего ордерблока проверяем, опускалась ли цена ниже его нижней границы
            for i in range(index + 3, len(candles)):
                if candles[i]['low'] < candles[index]['low']:
                    was_broken = True
                    break
        else:
            # Для медвежьего ордерблока проверяем, поднималась ли цена выше его верхней границы
            for i in range(index + 3, len(candles)):
                if candles[i]['high'] > candles[index]['high']:
                    was_broken = True
                    break
        
        if not was_broken:
            strength += 1.0
        
        # Увеличиваем силу, если после ордерблока был сильный импульс
        impulse_strength = 0.0
        
        if direction == "bullish":
            # Для бычьего ордерблока измеряем силу восходящего импульса
            max_high = max(c['high'] for c in candles[index+1:min(index+6, len(candles))])
            impulse_size = (max_high - candles[index]['low']) / candles[index]['low'] * 100
            impulse_strength = min(impulse_size / 2, 2.0)  # Максимум 2.0
        else:
            # Для медвежьего ордерблока измеряем силу нисходящего импульса
            min_low = min(c['low'] for c in candles[index+1:min(index+6, len(candles))])
            impulse_size = (candles[index]['high'] - min_low) / candles[index]['high'] * 100
            impulse_strength = min(impulse_size / 2, 2.0)  # Максимум 2.0
        
        strength += impulse_strength
        
        return strength
    
    def find_imbalances(self, candles: List[Dict]) -> List[Dict]:
        """
        Поиск зон дисбаланса (ценовых гэпов).
        
        Args:
            candles: Список свечей
            
        Returns:
            List[Dict]: Список зон дисбаланса
        """
        imbalances = []
        
        if len(candles) < 3:
            return imbalances
        
        for i in range(1, len(candles) - 1):
            # Бычий дисбаланс
            if candles[i]['low'] > candles[i-1]['high']:
                imbalance = {
                    "type": "bullish",
                    "top": candles[i]['low'],
                    "bottom": candles[i-1]['high'],
                    "size": candles[i]['low'] - candles[i-1]['high'],
                    "index": i
                }
                imbalances.append(imbalance)
            
            # Медвежий дисбаланс
            if candles[i]['high'] < candles[i-1]['low']:
                imbalance = {
                    "type": "bearish",
                    "top": candles[i-1]['low'],
                    "bottom": candles[i]['high'],
                    "size": candles[i-1]['low'] - candles[i]['high'],
                    "index": i
                }
                imbalances.append(imbalance)
        
        # Сортируем по размеру дисбаланса
        imbalances.sort(key=lambda x: x["size"], reverse=True)
        
        self.logger.debug(f"Found {len(imbalances)} imbalances")
        return imbalances
    
    def find_previous_impulse_points(self, candles: List[Dict]) -> List[Dict]:
        """
        Поиск точек предыдущих импульсов.
        
        Args:
            candles: Список свечей
            
        Returns:
            List[Dict]: Список точек импульсов
        """
        impulse_points = []
        
        if len(candles) < 5:
            return impulse_points
        
        # Создаем DataFrame для удобства анализа
        df = pd.DataFrame(candles)
        
        # Рассчитываем изменение цены для каждой свечи
        df['price_change'] = (df['close'] - df['open']) / df['open'] * 100
        
        # Находим свечи с сильным движением (более 1%)
        strong_moves = []
        for i in range(len(df)):
            if abs(df['price_change'].iloc[i]) > 1.0:
                strong_moves.append({
                    "index": i,
                    "direction": "bullish" if df['price_change'].iloc[i] > 0 else "bearish",
                    "strength": abs(df['price_change'].iloc[i])
                })
        
        # Для каждого сильного движения находим точку начала импульса
        for move in strong_moves:
            i = move["index"]
            
            if i < 2:
                continue
                
            if move["direction"] == "bullish":
                # Для бычьего импульса ищем предшествующую консолидацию или разворот
                if (df['low'].iloc[i-1] < df['low'].iloc[i-2] and 
                    df['low'].iloc[i] > df['low'].iloc[i-1]):
                    
                    impulse_points.append({
                        "type": "bullish_impulse_start",
                        "price": df['low'].iloc[i-1],
                        "strength": move["strength"],
                        "index": i-1
                    })
            else:
                # Для медвежьего импульса ищем предшествующую консолидацию или разворот
                if (df['high'].iloc[i-1] > df['high'].iloc[i-2] and 
                    df['high'].iloc[i] < df['high'].iloc[i-1]):
                    
                    impulse_points.append({
                        "type": "bearish_impulse_start",
                        "price": df['high'].iloc[i-1],
                        "strength": move["strength"],
                        "index": i-1
                    })
        
        # Сортируем по силе
        impulse_points.sort(key=lambda x: x["strength"], reverse=True)
        
        self.logger.debug(f"Found {len(impulse_points)} previous impulse points")
        return impulse_points
    
    def combine_interest_zones(self, order_blocks: List[Dict], imbalances: List[Dict], 
                             key_levels: List[Dict]) -> List[Dict]:
        """
        Объединение всех зон интереса.
        
        Args:
            order_blocks: Список ордерблоков
            imbalances: Список зон дисбаланса
            key_levels: Список ключевых уровней
            
        Returns:
            List[Dict]: Объединенный список зон интереса
        """
        interest_zones = []
        
        # Добавляем ордерблоки
        for ob in order_blocks:
            interest_zones.append({
                "type": f"{ob['type']}_order_block",
                "high": ob['high'],
                "low": ob['low'],
                "strength": ob['strength']
            })
        
        # Добавляем зоны дисбаланса
        for imb in imbalances:
            interest_zones.append({
                "type": f"{imb['type']}_imbalance",
                "high": imb['top'],
                "low": imb['bottom'],
                "strength": imb['size'] * 2  # Умножаем на 2, чтобы дать больший вес дисбалансам
            })
        
        # Добавляем ключевые уровни
        for level in key_levels:
            # Создаем небольшую зону вокруг уровня
            price = level['price']
            margin = price * 0.001  # 0.1% от цены
            
            interest_zones.append({
                "type": level['type'],
                "high": price + margin,
                "low": price - margin,
                "strength": level['strength']
            })
        
        # Сортируем по силе
        interest_zones.sort(key=lambda x: x["strength"], reverse=True)
        
        # Ограничиваем количество зон
        return interest_zones[:10]
