"""
Модуль для анализа контекста рынка.
"""
import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..exchange.client import ExchangeClient

class ContextAnalyzer:
    """
    Анализатор контекста рынка.
    Определяет глобальный тренд, ключевые уровни, дисбалансы и зоны ликвидности.
    """
    
    def __init__(self, exchange_client: ExchangeClient):
        """
        Инициализация анализатора контекста.
        
        Args:
            exchange_client: Клиент биржи для получения данных
        """
        self.exchange = exchange_client
        self.logger = logging.getLogger(__name__)
    
    async def analyze_daily_context(self, symbol: str) -> Dict:
        """
        Анализ дневного контекста.
        
        Args:
            symbol: Торговая пара (например, 'BTCUSDT')
            
        Returns:
            Dict: Результаты анализа контекста
        """
        # Получение дневных свечей
        daily_candles = await self.exchange.get_candles(symbol, '1d', limit=10)
        
        # Определение тренда
        trend = self._calculate_trend(daily_candles)
        
        # Поиск ключевых уровней
        key_levels = self._find_key_levels(daily_candles)
        
        # Определение дисбаланса
        imbalances = self._find_imbalances(daily_candles)
        
        # Анализ ликвидности
        liquidity_zones = self._analyze_liquidity(daily_candles)
        
        result = {
            "trend": trend,
            "key_levels": key_levels,
            "imbalances": imbalances,
            "liquidity_zones": liquidity_zones,
            "has_clear_direction": self._has_clear_direction(daily_candles),
            "market_activity": self._calculate_market_activity(daily_candles)
        }
        
        self.logger.info(f"Daily context analysis for {symbol}: trend={trend}, clear_direction={result['has_clear_direction']}")
        return result
    
    def _calculate_trend(self, candles: List[Dict]) -> str:
        """
        Определение тренда на основе свечей.
        
        Args:
            candles: Список свечей
            
        Returns:
            str: 'bullish', 'bearish' или 'neutral'
        """
        if not candles or len(candles) < 5:
            return "neutral"
        
        # Создаем DataFrame для удобства анализа
        df = pd.DataFrame(candles)
        
        # Рассчитываем EMA
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        
        # Определяем тренд на основе положения цены относительно EMA
        last_close = df['close'].iloc[-1]
        last_ema20 = df['ema20'].iloc[-1]
        last_ema50 = df['ema50'].iloc[-1]
        
        # Проверяем направление EMA
        ema20_slope = df['ema20'].iloc[-1] - df['ema20'].iloc[-3]
        ema50_slope = df['ema50'].iloc[-1] - df['ema50'].iloc[-3]
        
        # Определяем тренд
        if last_close > last_ema20 > last_ema50 and ema20_slope > 0 and ema50_slope > 0:
            return "bullish"
        elif last_close < last_ema20 < last_ema50 and ema20_slope < 0 and ema50_slope < 0:
            return "bearish"
        else:
            return "neutral"
    
    def _find_key_levels(self, candles: List[Dict]) -> List[Dict]:
        """
        Поиск ключевых уровней поддержки и сопротивления.
        
        Args:
            candles: Список свечей
            
        Returns:
            List[Dict]: Список ключевых уровней
        """
        if not candles or len(candles) < 5:
            return []
        
        key_levels = []
        
        # Создаем DataFrame для удобства анализа
        df = pd.DataFrame(candles)
        
        # Находим локальные максимумы и минимумы
        for i in range(2, len(df) - 2):
            # Проверка на локальный максимум
            if (df['high'].iloc[i] > df['high'].iloc[i-1] and 
                df['high'].iloc[i] > df['high'].iloc[i-2] and
                df['high'].iloc[i] > df['high'].iloc[i+1] and
                df['high'].iloc[i] > df['high'].iloc[i+2]):
                
                key_levels.append({
                    "type": "resistance",
                    "price": df['high'].iloc[i],
                    "strength": self._calculate_level_strength(df, i, "resistance")
                })
            
            # Проверка на локальный минимум
            if (df['low'].iloc[i] < df['low'].iloc[i-1] and 
                df['low'].iloc[i] < df['low'].iloc[i-2] and
                df['low'].iloc[i] < df['low'].iloc[i+1] and
                df['low'].iloc[i] < df['low'].iloc[i+2]):
                
                key_levels.append({
                    "type": "support",
                    "price": df['low'].iloc[i],
                    "strength": self._calculate_level_strength(df, i, "support")
                })
        
        # Сортируем уровни по силе
        key_levels.sort(key=lambda x: x["strength"], reverse=True)
        
        # Ограничиваем количество уровней
        return key_levels[:5]
    
    def _calculate_level_strength(self, df: pd.DataFrame, index: int, level_type: str) -> float:
        """
        Расчет силы уровня поддержки или сопротивления.
        
        Args:
            df: DataFrame со свечами
            index: Индекс свечи с уровнем
            level_type: Тип уровня ('support' или 'resistance')
            
        Returns:
            float: Сила уровня
        """
        # Базовая сила
        strength = 1.0
        
        # Увеличиваем силу, если уровень тестировался несколько раз
        price = df['low'].iloc[index] if level_type == "support" else df['high'].iloc[index]
        price_range = 0.002 * price  # 0.2% диапазон
        
        # Проверяем, сколько раз цена приближалась к уровню
        tests = 0
        for i in range(len(df)):
            if i == index:
                continue
                
            if level_type == "support" and abs(df['low'].iloc[i] - price) < price_range:
                tests += 1
            elif level_type == "resistance" and abs(df['high'].iloc[i] - price) < price_range:
                tests += 1
        
        # Увеличиваем силу на основе количества тестов
        strength += tests * 0.5
        
        # Увеличиваем силу, если уровень является круглым числом
        if self._is_round_number(price):
            strength += 1.0
        
        return strength
    
    def _is_round_number(self, price: float) -> bool:
        """
        Проверяет, является ли цена круглым числом.
        
        Args:
            price: Цена для проверки
            
        Returns:
            bool: True, если цена является круглым числом
        """
        # Проверка на круглые тысячи
        if price >= 1000 and price % 1000 < 10:
            return True
        
        # Проверка на круглые сотни
        if price >= 100 and price % 100 < 1:
            return True
        
        # Проверка на круглые десятки
        if price >= 10 and price % 10 < 0.1:
            return True
        
        # Проверка на круглые единицы
        if price >= 1 and price % 1 < 0.01:
            return True
        
        return False
    
    def _find_imbalances(self, candles: List[Dict]) -> List[Dict]:
        """
        Поиск зон дисбаланса (ценовых гэпов).
        
        Args:
            candles: Список свечей
            
        Returns:
            List[Dict]: Список зон дисбаланса
        """
        if not candles or len(candles) < 3:
            return []
        
        imbalances = []
        
        for i in range(1, len(candles) - 1):
            # Бычий дисбаланс (гэп вверх)
            if candles[i]['low'] > candles[i-1]['high']:
                imbalance = {
                    "type": "bullish",
                    "top": candles[i]['low'],
                    "bottom": candles[i-1]['high'],
                    "size": candles[i]['low'] - candles[i-1]['high']
                }
                imbalances.append(imbalance)
            
            # Медвежий дисбаланс (гэп вниз)
            if candles[i]['high'] < candles[i-1]['low']:
                imbalance = {
                    "type": "bearish",
                    "top": candles[i-1]['low'],
                    "bottom": candles[i]['high'],
                    "size": candles[i-1]['low'] - candles[i]['high']
                }
                imbalances.append(imbalance)
        
        # Сортируем по размеру дисбаланса
        imbalances.sort(key=lambda x: x["size"], reverse=True)
        
        return imbalances
    
    def _analyze_liquidity(self, candles: List[Dict]) -> List[Dict]:
        """
        Определение зон ликвидности.
        
        Args:
            candles: Список свечей
            
        Returns:
            List[Dict]: Список зон ликвидности
        """
        if not candles or len(candles) < 5:
            return []
        
        liquidity_zones = []
        
        # Создаем DataFrame для удобства анализа
        df = pd.DataFrame(candles)
        
        # Находим скопления стоп-лоссов (экстремумы)
        for i in range(2, len(df) - 2):
            # Зона ликвидности над локальным максимумом
            if (df['high'].iloc[i] > df['high'].iloc[i-1] and 
                df['high'].iloc[i] > df['high'].iloc[i-2] and
                df['high'].iloc[i] > df['high'].iloc[i+1] and
                df['high'].iloc[i] > df['high'].iloc[i+2]):
                
                liquidity_zones.append({
                    "type": "sell_stops",  # Скопление стоп-лоссов продавцов
                    "price": df['high'].iloc[i],
                    "strength": self._calculate_liquidity_strength(df, i, "high")
                })
            
            # Зона ликвидности под локальным минимумом
            if (df['low'].iloc[i] < df['low'].iloc[i-1] and 
                df['low'].iloc[i] < df['low'].iloc[i-2] and
                df['low'].iloc[i] < df['low'].iloc[i+1] and
                df['low'].iloc[i] < df['low'].iloc[i+2]):
                
                liquidity_zones.append({
                    "type": "buy_stops",  # Скопление стоп-лоссов покупателей
                    "price": df['low'].iloc[i],
                    "strength": self._calculate_liquidity_strength(df, i, "low")
                })
        
        # Добавляем круглые уровни как потенциальные зоны ликвидности
        last_price = df['close'].iloc[-1]
        
        # Ближайшие круглые уровни выше текущей цены
        for multiplier in [1.05, 1.1, 1.2]:
            round_price = self._round_to_significant(last_price * multiplier)
            liquidity_zones.append({
                "type": "psychological_resistance",
                "price": round_price,
                "strength": 1.0
            })
        
        # Ближайшие круглые уровни ниже текущей цены
        for multiplier in [0.95, 0.9, 0.8]:
            round_price = self._round_to_significant(last_price * multiplier)
            liquidity_zones.append({
                "type": "psychological_support",
                "price": round_price,
                "strength": 1.0
            })
        
        # Сортируем зоны по силе
        liquidity_zones.sort(key=lambda x: x["strength"], reverse=True)
        
        return liquidity_zones
    
    def _calculate_liquidity_strength(self, df: pd.DataFrame, index: int, price_type: str) -> float:
        """
        Расчет силы зоны ликвидности.
        
        Args:
            df: DataFrame со свечами
            index: Индекс свечи с зоной ликвидности
            price_type: Тип цены ('high' или 'low')
            
        Returns:
            float: Сила зоны ликвидности
        """
        # Базовая сила
        strength = 1.0
        
        # Увеличиваем силу, если зона не была пробита
        price = df[price_type].iloc[index]
        
        # Проверяем, была ли зона пробита после формирования
        was_broken = False
        for i in range(index + 1, len(df)):
            if price_type == "high" and df['high'].iloc[i] > price:
                was_broken = True
                break
            elif price_type == "low" and df['low'].iloc[i] < price:
                was_broken = True
                break
        
        if not was_broken:
            strength += 1.0
        
        # Увеличиваем силу, если зона является круглым числом
        if self._is_round_number(price):
            strength += 0.5
        
        return strength
    
    def _round_to_significant(self, price: float) -> float:
        """
        Округляет цену до значимого уровня.
        
        Args:
            price: Исходная цена
            
        Returns:
            float: Округленная цена
        """
        if price >= 10000:
            return round(price / 1000) * 1000
        elif price >= 1000:
            return round(price / 100) * 100
        elif price >= 100:
            return round(price / 10) * 10
        elif price >= 10:
            return round(price)
        elif price >= 1:
            return round(price * 10) / 10
        else:
            return round(price * 100) / 100
    
    def _has_clear_direction(self, candles: List[Dict]) -> bool:
        """
        Определяет, имеет ли рынок четкое направление.
        
        Args:
            candles: Список свечей
            
        Returns:
            bool: True, если рынок имеет четкое направление
        """
        if not candles or len(candles) < 5:
            return False
        
        # Создаем DataFrame для удобства анализа
        df = pd.DataFrame(candles)
        
        # Рассчитываем ADX (Average Directional Index)
        # Упрощенная версия для демонстрации
        high_changes = df['high'].diff()
        low_changes = df['low'].diff()
        
        plus_dm = high_changes.copy()
        plus_dm[plus_dm < 0] = 0
        plus_dm[low_changes * -1 > high_changes] = 0
        
        minus_dm = low_changes.copy() * -1
        minus_dm[minus_dm < 0] = 0
        minus_dm[high_changes > minus_dm] = 0
        
        tr1 = df['high'] - df['low']
        tr2 = (df['high'] - df['close'].shift(1)).abs()
        tr3 = (df['low'] - df['close'].shift(1)).abs()
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        atr = tr.rolling(window=14).mean()
        
        plus_di = 100 * (plus_dm.rolling(window=14).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=14).mean() / atr)
        
        dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
        adx = dx.rolling(window=14).mean()
        
        # ADX > 25 указывает на сильный тренд
        last_adx = adx.iloc[-1]
        
        return not np.isnan(last_adx) and last_adx > 25
    
    def _calculate_market_activity(self, candles: List[Dict]) -> str:
        """
        Расчет активности рынка.
        
        Args:
            candles: Список свечей
            
        Returns:
            str: 'high', 'medium' или 'low'
        """
        if not candles or len(candles) < 5:
            return "low"
        
        # Создаем DataFrame для удобства анализа
        df = pd.DataFrame(candles)
        
        # Рассчитываем средний размер свечи за последние 5 дней
        recent_candles = df.iloc[-5:]
        avg_range = ((recent_candles['high'] - recent_candles['low']) / recent_candles['low']).mean() * 100
        
        # Определяем активность на основе среднего размера свечи
        if avg_range > 3.0:  # Более 3% в среднем
            return "high"
        elif avg_range > 1.5:  # Более 1.5% в среднем
            return "medium"
        else:
            return "low"
