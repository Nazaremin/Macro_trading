"""
Модуль для бэктестирования стратегии "Макросы".
"""
import asyncio
import datetime
import logging
import os
from typing import Dict, List, Optional, Any

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter

from src.exchange.client import ExchangeClient
from src.strategy.time_manager import MacroTimeManager
from src.strategy.context_analyzer import ContextAnalyzer
from src.strategy.zone_detector import InterestZoneDetector
from src.strategy.scenario_analyzer import ScenarioAnalyzer
from src.strategy.macro_executor import MacroExecutor
from src.utils.logger import setup_logger

class MacroBacktester:
    """
    Бэктестер для стратегии "Макросы".
    Позволяет проверить стратегию на исторических данных.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Инициализация бэктестера.
        
        Args:
            config: Конфигурация
        """
        self.config = config
        self.logger = setup_logger("backtest", log_level=config.get("logging_level", "INFO"))
        
        # Инициализация клиента биржи
        self.exchange = ExchangeClient(testnet=True)
        
        # Инициализация компонентов стратегии
        self.time_manager = MacroTimeManager(config.get("macro_intervals"))
        self.context_analyzer = ContextAnalyzer(self.exchange)
        self.zone_detector = InterestZoneDetector()
        self.scenario_analyzer = ScenarioAnalyzer(self.context_analyzer, self.zone_detector, self.exchange)
        self.macro_executor = MacroExecutor(self.time_manager, self.scenario_analyzer, self.exchange)
        
        # Результаты
        self.trades = []
        self.equity_curve = []
    
    async def run_backtest(self, symbol: str, start_date: str, end_date: str, 
                         initial_capital: float = 10000) -> Dict[str, Any]:
        """
        Запуск бэктеста.
        
        Args:
            symbol: Торговая пара
            start_date: Начальная дата (формат: 'YYYY-MM-DD')
            end_date: Конечная дата (формат: 'YYYY-MM-DD')
            initial_capital: Начальный капитал
            
        Returns:
            Dict[str, Any]: Результаты бэктеста
        """
        self.logger.info(f"Starting backtest for {symbol} from {start_date} to {end_date}")
        
        try:
            # Загрузка исторических данных
            if self.config.get("data_csv_path"):
                historical_data = self._load_historical_data_from_csv(
                    self.config["data_csv_path"], start_date, end_date
                )
            else:
                # historical_data = await self._load_historical_data(symbol, start_date, end_date) # Закомментировано для использования заглушки
                historical_data = self._get_mock_historical_data(start_date, end_date)


            if not historical_data:
                self.logger.error("Failed to load historical data")
                return {
                    "success": False,
                    "message": "Failed to load historical data"
                }

            if self.config.get("data_csv_path"):
                self.logger.info(f"Loaded {len(historical_data)} data points from CSV path: {self.config.get('data_csv_path')}")
            else:
                self.logger.info(f"Loaded {len(historical_data)} historical data points (mocked)")


            # Начальный капитал
            current_capital = initial_capital
            
            # Симуляция торговли
            for day_idx, day_data in enumerate(self._group_by_day(historical_data)):
                day_date = datetime.datetime.fromtimestamp(day_data[0]['timestamp'] / 1000).strftime('%Y-%m-%d')
                self.logger.info(f"Processing day {day_idx+1}: {day_date}")
                
                # Анализ дневного контекста
                daily_context = self._simulate_context_analysis(day_data)
                
                # Проверка каждого минутного интервала
                for minute_idx, minute_data in enumerate(day_data):
                    # Преобразование времени свечи в объект datetime
                    candle_time = datetime.datetime.fromtimestamp(minute_data['timestamp'] / 1000)
                    
                    # Проверка, находимся ли мы в макро-интервале
                    is_macro = self._is_time_in_macro(candle_time)
                    
                    if is_macro:
                        # Анализ сценария
                        scenario = self._simulate_scenario_analysis(
                            day_data[:minute_idx+1],
                            daily_context
                        )
                        
                        if scenario["ready_for_macro"]:
                            # Симуляция исполнения макроса
                            entry_signal = self._simulate_macro_execution(
                                minute_data,
                                scenario
                            )
                            
                            if entry_signal:
                                # Симуляция торговли
                                trade_result = self._simulate_trade(
                                    entry_signal,
                                    day_data[minute_idx:],
                                    current_capital
                                )
                                
                                # Обновление капитала
                                current_capital += trade_result["pnl"]
                                
                                # Сохранение результатов сделки
                                self.trades.append(trade_result)
                                
                                # Обновление кривой капитала
                                self.equity_curve.append({
                                    "timestamp": minute_data['timestamp'],
                                    "capital": current_capital
                                })
                
                # Обновление кривой капитала в конце дня
                if day_data:
                    self.equity_curve.append({
                        "timestamp": day_data[-1]['timestamp'],
                        "capital": current_capital
                    })
            
            # Расчет метрик
            metrics = self._calculate_metrics(initial_capital, current_capital)
            
            self.logger.info(f"Backtest completed. Final capital: {current_capital:.2f}, Total return: {metrics['total_return']:.2f}%")
            
            return {
                "success": True,
                "initial_capital": initial_capital,
                "final_capital": current_capital,
                "total_return": metrics["total_return"],
                "trades": self.trades,
                "equity_curve": self.equity_curve,
                "metrics": metrics
            }
        finally:
            # Закрытие соединения с биржей
            # await self.exchange.close() # Закомментировано, так как биржа не используется с заглушкой
            self.logger.info("Exchange connection closed (mocked run)")
    
    # async def _load_historical_data(self, symbol: str, start_date: str, end_date: str) -> List[Dict]: # Закомментировано, чтобы использовать заглушку
    #     """
    #     Загрузка исторических данных.
    #     """
    #     try:
    #         # Преобразование дат в timestamp
    #         start_timestamp = int(datetime.datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
    #         end_timestamp = int(datetime.datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000)

    #         # Загрузка данных по частям (максимум 1000 свечей за раз)
    #         all_candles = []
    #         current_timestamp = start_timestamp

    #         while current_timestamp < end_timestamp:
    #             # Загрузка свечей
    #             candles = await self.exchange.get_candles(
    #                 symbol=symbol,
    #                 timeframe='1m',
    #                 limit=1000
    #             )

    #             if not candles:
    #                 break

    #             # Добавление свечей
    #             all_candles.extend(candles)

    #             # Обновление timestamp
    #             current_timestamp = candles[-1]['timestamp'] + 60000  # +1 минута

    #             # Пауза, чтобы не превысить лимиты API
    #             await asyncio.sleep(1)

    #         # Фильтрация по дате
    #         filtered_candles = [
    #             candle for candle in all_candles
    #             if start_timestamp <= candle['timestamp'] <= end_timestamp
    #         ]

    #         return filtered_candles

    #     except Exception as e:
    #         self.logger.error(f"Error loading historical data: {str(e)}")
    #         return []

    def _get_mock_historical_data(self, start_date_str: str, end_date_str: str) -> List[Dict]:
        """
        Генерирует моковые исторические данные для бэктестирования.
        """
        self.logger.info(f"Generating mock historical data from {start_date_str} to {end_date_str}")
        data = []
        start_dt = datetime.datetime.strptime(start_date_str, '%Y-%m-%d')
        end_dt = datetime.datetime.strptime(end_date_str, '%Y-%m-%d')
        current_dt = start_dt

        base_price = 100.0
        idx = 0
        while current_dt <= end_dt:
            for minute in range(24 * 60): # Генерируем минутные свечи
                timestamp = int(current_dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000) + minute * 60000
                # Простая синусоида для имитации колебаний цены
                open_price = base_price + np.sin(idx / 60.0) * 5
                close_price = open_price + np.random.uniform(-0.5, 0.5)
                high_price = max(open_price, close_price) + np.random.uniform(0, 0.2)
                low_price = min(open_price, close_price) - np.random.uniform(0, 0.2)
                volume = np.random.uniform(1, 10)

                data.append({
                    'timestamp': timestamp,
                    'open': open_price,
                    'high': high_price,
                    'low': low_price,
                    'close': close_price,
                    'volume': volume
                })
                idx +=1
            current_dt += datetime.timedelta(days=1)
        
        self.logger.info(f"Generated {len(data)} mock data points.")
        return data

    def _load_historical_data_from_csv(self, csv_path: str, start_date_str: str, end_date_str: str) -> List[Dict]:
        """
        Загрузка исторических данных из CSV-файла.
        Фильтрует данные по указанному диапазону дат.
        Ожидаемые колонки: timestamp, open, high, low, close, volume
        """
        self.logger.info(f"Loading historical data from CSV: {csv_path}")
        try:
            df = pd.read_csv(csv_path)

            # Преобразование timestamp в datetime для фильтрации
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')

            start_dt = datetime.datetime.strptime(start_date_str, '%Y-%m-%d')
            # Для end_date берем конец дня, чтобы включить все свечи этого дня
            end_dt = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59, microsecond=999999)

            # Фильтрация по дате
            df_filtered = df[(df['datetime'] >= start_dt) & (df['datetime'] <= end_dt)]

            if df_filtered.empty:
                self.logger.warning(f"No data found in CSV for the period {start_date_str} - {end_date_str}")
                return []

            # Преобразование DataFrame обратно в список словарей
            # Убедимся, что все необходимые колонки имеют правильный тип
            df_filtered = df_filtered[['timestamp', 'open', 'high', 'low', 'close', 'volume']].astype({
                'timestamp': 'int64', # Убедимся, что timestamp - это int
                'open': 'float',
                'high': 'float',
                'low': 'float',
                'close': 'float',
                'volume': 'float'
            })

            historical_data = df_filtered.to_dict('records')
            self.logger.info(f"Loaded {len(historical_data)} data points from CSV for the specified period.")
            return historical_data

        except FileNotFoundError:
            self.logger.error(f"CSV file not found: {csv_path}")
            return []
        except Exception as e:
            self.logger.error(f"Error loading data from CSV {csv_path}: {str(e)}")
            return []

    # Закомментировал оригинальную функцию _load_historical_data
    # async def _load_historical_data(self, symbol: str, start_date: str, end_date: str) -> List[Dict]:
    #     """
    #     Загрузка исторических данных.

    #     Args:
    #         symbol: Торговая пара
    #         start_date: Начальная дата
    #         end_date: Конечная дата

    #     Returns:
    #         List[Dict]: Исторические данные
    #     """
    #     try:
    #         # Преобразование дат в timestamp
    #         start_timestamp = int(datetime.datetime.strptime(start_date, '%Y-%m-%d').timestamp() * 1000)
    #         end_timestamp = int(datetime.datetime.strptime(end_date, '%Y-%m-%d').timestamp() * 1000)

    #         # Загрузка данных по частям (максимум 1000 свечей за раз)
    #         all_candles = []
    #         current_timestamp = start_timestamp

    #         while current_timestamp < end_timestamp:
    #             # Загрузка свечей
    #             candles = await self.exchange.get_candles(
    #                 symbol=symbol,
    #                 timeframe='1m',
    #                 limit=1000
    #             )
                
    #             if not candles:
    #                 break
                
    #             # Добавление свечей
    #             all_candles.extend(candles)
                
    #             # Обновление timestamp
    #             current_timestamp = candles[-1]['timestamp'] + 60000  # +1 минута
                
    #             # Пауза, чтобы не превысить лимиты API
    #             await asyncio.sleep(1)
            
    #         # Фильтрация по дате
    #         filtered_candles = [
    #             candle for candle in all_candles
    #             if start_timestamp <= candle['timestamp'] <= end_timestamp
    #         ]
            
    #         return filtered_candles
            
    #     except Exception as e:
    #         self.logger.error(f"Error loading historical data: {str(e)}")
    #         return []
    
    def _group_by_day(self, candles: List[Dict]) -> List[List[Dict]]:
        """
        Группировка свечей по дням.
        
        Args:
            candles: Список свечей
            
        Returns:
            List[List[Dict]]: Список списков свечей, сгруппированных по дням
        """
        if not candles:
            return []
        
        # Группировка по дням
        days = {}
        
        for candle in candles:
            # Получение даты
            date = datetime.datetime.fromtimestamp(candle['timestamp'] / 1000).strftime('%Y-%m-%d')
            
            # Добавление свечи в соответствующий день
            if date not in days:
                days[date] = []
            
            days[date].append(candle)
        
        # Сортировка дней
        sorted_days = sorted(days.items(), key=lambda x: x[0])
        
        # Возвращаем только списки свечей
        return [day_candles for _, day_candles in sorted_days]
    
    def _simulate_context_analysis(self, day_data: List[Dict]) -> Dict:
        """
        Симуляция анализа контекста.
        
        Args:
            day_data: Данные за день
            
        Returns:
            Dict: Результаты анализа контекста
        """
        # Упрощенная версия анализа контекста
        
        # Определение тренда
        if len(day_data) < 5:
            trend = "neutral"
        else:
            # Рассчитываем EMA
            closes = [candle['close'] for candle in day_data]
            ema20 = self._calculate_ema(closes, 20)
            ema50 = self._calculate_ema(closes, 50)
            
            if ema20[-1] > ema50[-1]:
                trend = "bullish"
            elif ema20[-1] < ema50[-1]:
                trend = "bearish"
            else:
                trend = "neutral"
        
        # Поиск ключевых уровней
        key_levels = self._find_key_levels(day_data)
        
        # Определение дисбаланса
        imbalances = self.zone_detector.find_imbalances(day_data)
        
        # Анализ ликвидности
        liquidity_zones = self._analyze_liquidity(day_data)
        
        return {
            "trend": trend,
            "key_levels": key_levels,
            "imbalances": imbalances,
            "liquidity_zones": liquidity_zones,
            "has_clear_direction": True if trend != "neutral" else False,
            "market_activity": "medium"  # Упрощение
        }
    
    def _calculate_ema(self, data: List[float], period: int) -> List[float]:
        """
        Расчет экспоненциальной скользящей средней.
        
        Args:
            data: Список значений
            period: Период
            
        Returns:
            List[float]: Список значений EMA
        """
        if len(data) < period:
            return data
        
        # Коэффициент сглаживания
        alpha = 2 / (period + 1)
        
        # Расчет EMA
        ema = [data[0]]
        
        for i in range(1, len(data)):
            ema.append(alpha * data[i] + (1 - alpha) * ema[i-1])
        
        return ema
    
    def _find_key_levels(self, candles: List[Dict]) -> List[Dict]:
        """
        Поиск ключевых уровней.
        
        Args:
            candles: Список свечей
            
        Returns:
            List[Dict]: Список ключевых уровней
        """
        # Упрощенная версия поиска ключевых уровней
        key_levels = []
        
        if len(candles) < 5:
            return key_levels
        
        # Находим локальные максимумы и минимумы
        for i in range(2, len(candles) - 2):
            # Проверка на локальный максимум
            if (candles[i]['high'] > candles[i-1]['high'] and 
                candles[i]['high'] > candles[i-2]['high'] and
                candles[i]['high'] > candles[i+1]['high'] and
                candles[i]['high'] > candles[i+2]['high']):
                
                key_levels.append({
                    "type": "resistance",
                    "price": candles[i]['high'],
                    "strength": 1.0
                })
            
            # Проверка на локальный минимум
            if (candles[i]['low'] < candles[i-1]['low'] and 
                candles[i]['low'] < candles[i-2]['low'] and
                candles[i]['low'] < candles[i+1]['low'] and
                candles[i]['low'] < candles[i+2]['low']):
                
                key_levels.append({
                    "type": "support",
                    "price": candles[i]['low'],
                    "strength": 1.0
                })
        
        return key_levels
    
    def _analyze_liquidity(self, candles: List[Dict]) -> List[Dict]:
        """
        Анализ ликвидности.
        
        Args:
            candles: Список свечей
            
        Returns:
            List[Dict]: Список зон ликвидности
        """
        # Упрощенная версия анализа ликвидности
        liquidity_zones = []
        
        if len(candles) < 5:
            return liquidity_zones
        
        # Находим экстремумы как зоны ликвидности
        for i in range(2, len(candles) - 2):
            # Зона ликвидности над локальным максимумом
            if (candles[i]['high'] > candles[i-1]['high'] and 
                candles[i]['high'] > candles[i-2]['high'] and
                candles[i]['high'] > candles[i+1]['high'] and
                candles[i]['high'] > candles[i+2]['high']):
                
                liquidity_zones.append({
                    "type": "sell_stops",
                    "price": candles[i]['high'],
                    "strength": 1.0
                })
            
            # Зона ликвидности под локальным минимумом
            if (candles[i]['low'] < candles[i-1]['low'] and 
                candles[i]['low'] < candles[i-2]['low'] and
                candles[i]['low'] < candles[i+1]['low'] and
                candles[i]['low'] < candles[i+2]['low']):
                
                liquidity_zones.append({
                    "type": "buy_stops",
                    "price": candles[i]['low'],
                    "strength": 1.0
                })
        
        return liquidity_zones
    
    def _is_time_in_macro(self, candle_time: datetime.datetime) -> bool:
        """
        Проверка, находится ли время в макро-интервале.
        
        Args:
            candle_time: Время свечи
            
        Returns:
            bool: True, если время в макро-интервале
        """
        # Преобразование в нью-йоркское время
        ny_time = candle_time.astimezone(self.time_manager.timezone)
        current_time_str = ny_time.strftime("%H:%M")
        
        # Проверка каждого интервала
        for interval in self.time_manager.primary_intervals:
            if self.time_manager._is_time_in_range(current_time_str, interval["start"], interval["end"]):
                return True
        
        return False
    
    def _simulate_scenario_analysis(self, candles: List[Dict], daily_context: Dict) -> Dict:
        """
        Симуляция анализа сценария.
        
        Args:
            candles: Список свечей
            daily_context: Дневной контекст
            
        Returns:
            Dict: Результаты анализа сценария
        """
        # Упрощенная версия анализа сценария
        
        # Проверка на снятие ликвидности
        liquidity_sweep = self._detect_liquidity_sweep(candles, daily_context["liquidity_zones"])
        
        # Проверка на манипуляцию
        manipulation = self._detect_manipulation(candles)
        
        # Определение зон интереса
        order_blocks = self.zone_detector.find_order_blocks(candles, "bullish" if daily_context["trend"] == "bullish" else "bearish")
        imbalances = self.zone_detector.find_imbalances(candles)
        interest_zones = self.zone_detector.combine_interest_zones(
            order_blocks,
            imbalances,
            daily_context["key_levels"]
        )
        
        # Проверка возврата в зону интереса
        return_to_zone = self._check_return_to_zone(candles, interest_zones)
        
        # Проверка формирования структуры
        structure_formed = self._check_structure_formation(candles)
        
        # Определение текущего сценария
        scenario = self._determine_scenario(
            daily_context["trend"],
            liquidity_sweep,
            manipulation,
            return_to_zone,
            structure_formed
        )
        
        return {
            "scenario": scenario,
            "liquidity_sweep": liquidity_sweep,
            "manipulation": manipulation,
            "interest_zones": interest_zones,
            "return_to_zone": return_to_zone,
            "structure_formed": structure_formed,
            "ready_for_macro": scenario in [
                "bullish_continuation", 
                "bearish_continuation", 
                "potential_bullish_reversal", 
                "potential_bearish_reversal"
            ]
        }
    
    def _detect_liquidity_sweep(self, candles: List[Dict], liquidity_zones: List[Dict]) -> Dict:
        """
        Определение снятия ликвидности.
        
        Args:
            candles: Список свечей
            liquidity_zones: Зоны ликвидности
            
        Returns:
            Dict: Информация о снятии ликвидности
        """
        # Упрощенная версия определения снятия ликвидности
        if not candles or len(candles) < 10 or not liquidity_zones:
            return {"detected": False}
        
        # Последние 10 свечей
        recent_candles = candles[-10:]
        
        # Проверяем, достигла ли цена зон ликвидности
        for zone in liquidity_zones:
            zone_price = zone["price"]
            zone_type = zone["type"]
            
            for candle in recent_candles:
                # Для зоны ликвидности над рынком (sell_stops)
                if zone_type == "sell_stops" and candle["high"] >= zone_price:
                    # Проверяем, был ли возврат после снятия ликвидности
                    if candle["close"] < zone_price:
                        return {
                            "detected": True,
                            "type": "sell_stops_sweep",
                            "price": zone_price,
                            "strength": zone["strength"]
                        }
                
                # Для зоны ликвидности под рынком (buy_stops)
                elif zone_type == "buy_stops" and candle["low"] <= zone_price:
                    # Проверяем, был ли возврат после снятия ликвидности
                    if candle["close"] > zone_price:
                        return {
                            "detected": True,
                            "type": "buy_stops_sweep",
                            "price": zone_price,
                            "strength": zone["strength"]
                        }
        
        return {"detected": False}
    
    def _detect_manipulation(self, candles: List[Dict]) -> Dict:
        """
        Выявление манипуляций.
        
        Args:
            candles: Список свечей
            
        Returns:
            Dict: Информация о манипуляции
        """
        # Упрощенная версия выявления манипуляций
        if not candles or len(candles) < 20:
            return {"detected": False}
        
        # Последние 20 свечей
        recent_candles = candles[-20:]
        
        # Ищем резкие движения с последующим возвратом
        for i in range(2, len(recent_candles) - 2):
            # Бычья манипуляция (резкий рост с последующим падением)
            if (recent_candles[i]["high"] > recent_candles[i-1]["high"] * 1.01 and  # Резкий рост (более 1%)
                recent_candles[i+1]["low"] < recent_candles[i]["low"]):  # Последующее падение
                
                return {
                    "detected": True,
                    "type": "bullish_manipulation",
                    "index": i,
                    "price": recent_candles[i]["high"]
                }
            
            # Медвежья манипуляция (резкое падение с последующим ростом)
            if (recent_candles[i]["low"] < recent_candles[i-1]["low"] * 0.99 and  # Резкое падение (более 1%)
                recent_candles[i+1]["high"] > recent_candles[i]["high"]):  # Последующий рост
                
                return {
                    "detected": True,
                    "type": "bearish_manipulation",
                    "index": i,
                    "price": recent_candles[i]["low"]
                }
        
        return {"detected": False}
    
    def _check_return_to_zone(self, candles: List[Dict], interest_zones: List[Dict]) -> Dict:
        """
        Проверка возврата цены в зону интереса.
        
        Args:
            candles: Список свечей
            interest_zones: Зоны интереса
            
        Returns:
            Dict: Информация о возврате в зону
        """
        # Упрощенная версия проверки возврата в зону
        if not candles or not interest_zones:
            return {"detected": False}
        
        # Последняя цена
        last_price = candles[-1]["close"]
        
        # Проверяем, находится ли цена в одной из зон интереса
        for zone in interest_zones:
            if last_price >= zone["low"] and last_price <= zone["high"]:
                return {
                    "detected": True,
                    "zone_type": zone["type"],
                    "zone_low": zone["low"],
                    "zone_high": zone["high"],
                    "strength": zone["strength"]
                }
        
        return {"detected": False}
    
    def _check_structure_formation(self, candles: List[Dict]) -> Dict:
        """
        Проверка формирования структуры.
        
        Args:
            candles: Список свечей
            
        Returns:
            Dict: Информация о формировании структуры
        """
        # Упрощенная версия проверки формирования структуры
        if not candles or len(candles) < 5:
            return {"detected": False}
        
        # Последние 5 свечей
        recent_candles = candles[-5:]
        
        # Проверяем формирование бычьей структуры (восходящие минимумы)
        bullish_structure = True
        for i in range(1, len(recent_candles)):
            if recent_candles[i]["low"] < recent_candles[i-1]["low"]:
                bullish_structure = False
                break
        
        if bullish_structure:
            return {
                "detected": True,
                "type": "bullish_structure",
                "strength": 1.0
            }
        
        # Проверяем формирование медвежьей структуры (нисходящие максимумы)
        bearish_structure = True
        for i in range(1, len(recent_candles)):
            if recent_candles[i]["high"] > recent_candles[i-1]["high"]:
                bearish_structure = False
                break
        
        if bearish_structure:
            return {
                "detected": True,
                "type": "bearish_structure",
                "strength": 1.0
            }
        
        return {"detected": False}
    
    def _determine_scenario(self, trend: str, liquidity_sweep: Dict, manipulation: Dict, 
                          return_to_zone: Dict, structure_formed: Dict) -> str:
        """
        Определение текущего сценария на основе всех факторов.
        
        Args:
            trend: Глобальный тренд
            liquidity_sweep: Информация о снятии ликвидности
            manipulation: Информация о манипуляции
            return_to_zone: Информация о возврате в зону
            structure_formed: Информация о формировании структуры
            
        Returns:
            str: Текущий сценарий
        """
        # Бычий сценарий продолжения
        if (trend == "bullish" and 
            liquidity_sweep.get("detected", False) and 
            return_to_zone.get("detected", False) and 
            structure_formed.get("detected", False) and 
            structure_formed.get("type") == "bullish_structure"):
            
            return "bullish_continuation"
        
        # Медвежий сценарий продолжения
        if (trend == "bearish" and 
            liquidity_sweep.get("detected", False) and 
            return_to_zone.get("detected", False) and 
            structure_formed.get("detected", False) and 
            structure_formed.get("type") == "bearish_structure"):
            
            return "bearish_continuation"
        
        # Потенциальный разворот (снятие ликвидности без возврата в зону)
        if (liquidity_sweep.get("detected", False) and 
            not return_to_zone.get("detected", False) and 
            manipulation.get("detected", False)):
            
            if liquidity_sweep.get("type") == "sell_stops_sweep":
                return "potential_bearish_reversal"
            elif liquidity_sweep.get("type") == "buy_stops_sweep":
                return "potential_bullish_reversal"
        
        # Нет четкого сценария
        return "no_clear_scenario"
    
    def _simulate_macro_execution(self, candle: Dict, scenario: Dict) -> Optional[Dict]:
        """
        Симуляция исполнения макроса.
        
        Args:
            candle: Текущая свеча
            scenario: Текущий сценарий
            
        Returns:
            Optional[Dict]: Сигнал для входа или None
        """
        # Упрощенная версия исполнения макроса
        
        # Проверка исполнения сценария
        current_price = candle["close"]
        
        # Проверка доставки цены в зону интереса
        if scenario["scenario"] == "bullish_continuation":
            for zone in scenario["interest_zones"]:
                if current_price >= zone["low"] and current_price <= zone["high"]:
                    # Генерация сигнала для входа
                    return self._generate_entry_signal(
                        "BTCUSDT",  # Упрощение
                        "buy",
                        current_price,
                        scenario,
                        zone
                    )
        
        elif scenario["scenario"] == "bearish_continuation":
            for zone in scenario["interest_zones"]:
                if current_price >= zone["low"] and current_price <= zone["high"]:
                    # Генерация сигнала для входа
                    return self._generate_entry_signal(
                        "BTCUSDT",  # Упрощение
                        "sell",
                        current_price,
                        scenario,
                        zone
                    )
        
        elif scenario["scenario"] == "potential_bullish_reversal":
            # Для разворотного сценария требуются дополнительные подтверждения
            if scenario["liquidity_sweep"]["detected"] and scenario["liquidity_sweep"]["type"] == "buy_stops_sweep":
                for zone in scenario["interest_zones"]:
                    if current_price >= zone["low"] and current_price <= zone["high"]:
                        # Генерация сигнала для входа
                        return self._generate_entry_signal(
                            "BTCUSDT",  # Упрощение
                            "buy",
                            current_price,
                            scenario,
                            zone
                        )
        
        elif scenario["scenario"] == "potential_bearish_reversal":
            # Для разворотного сценария требуются дополнительные подтверждения
            if scenario["liquidity_sweep"]["detected"] and scenario["liquidity_sweep"]["type"] == "sell_stops_sweep":
                for zone in scenario["interest_zones"]:
                    if current_price >= zone["low"] and current_price <= zone["high"]:
                        # Генерация сигнала для входа
                        return self._generate_entry_signal(
                            "BTCUSDT",  # Упрощение
                            "sell",
                            current_price,
                            scenario,
                            zone
                        )
        
        return None
    
    def _generate_entry_signal(self, symbol: str, signal_type: str, price: float, 
                             scenario: Dict, zone: Dict) -> Dict:
        """
        Генерация сигнала для входа.
        
        Args:
            symbol: Торговая пара
            signal_type: Тип сигнала ('buy' или 'sell')
            price: Цена входа
            scenario: Текущий сценарий
            zone: Зона интереса
            
        Returns:
            Dict: Сигнал для входа
        """
        # Расчет стоп-лосса и тейк-профита
        
        if signal_type == "buy":
            # Для бычьего сценария
            stop_loss = zone["low"] * 0.998  # -0.2%
            
            # Для основного сценария - более агрессивные цели (1:3)
            if scenario["scenario"] in ["bullish_continuation", "bearish_continuation"]:
                risk = price - stop_loss
                take_profit = price + (risk * 3.0)
            # Для разворотного - консервативные (1:2)
            else:
                risk = price - stop_loss
                take_profit = price + (risk * 2.0)
        else:
            # Для медвежьего сценария
            stop_loss = zone["high"] * 1.002  # +0.2%
            
            # Для основного сценария - более агрессивные цели (1:3)
            if scenario["scenario"] in ["bullish_continuation", "bearish_continuation"]:
                risk = stop_loss - price
                take_profit = price - (risk * 3.0)
            # Для разворотного - консервативные (1:2)
            else:
                risk = stop_loss - price
                take_profit = price - (risk * 2.0)
        
        return {
            "symbol": symbol,
            "type": signal_type,
            "price": price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "time": datetime.datetime.now(),
            "scenario": scenario["scenario"],
            "confidence": 0.7,  # Упрощение
            "zone_type": zone["type"]
        }
    
    def _simulate_trade(self, signal: Dict, future_candles: List[Dict], current_capital: float) -> Dict:
        """
        Симуляция торговли.
        
        Args:
            signal: Сигнал для входа
            future_candles: Будущие свечи
            current_capital: Текущий капитал
            
        Returns:
            Dict: Результат торговли
        """
        # Расчет размера позиции
        risk_amount = current_capital * self.config.get("risk_per_trade", 0.02)
        price_distance = abs(signal["price"] - signal["stop_loss"])
        position_size = risk_amount / price_distance
        
        # Инициализация результата
        trade_result = {
            "symbol": signal["symbol"],
            "type": signal["type"],
            "entry_price": signal["price"],
            "stop_loss": signal["stop_loss"],
            "take_profit": signal["take_profit"],
            "position_size": position_size,
            "entry_time": signal["time"],
            "scenario": signal["scenario"],
            "exit_price": None,
            "exit_time": None,
            "exit_reason": None,
            "pnl": 0,
            "pnl_percent": 0
        }
        
        # Симуляция торговли
        for i, candle in enumerate(future_candles):
            # Проверка стоп-лосса
            if signal["type"] == "buy" and candle["low"] <= signal["stop_loss"]:
                trade_result["exit_price"] = signal["stop_loss"]
                trade_result["exit_time"] = datetime.datetime.fromtimestamp(candle["timestamp"] / 1000)
                trade_result["exit_reason"] = "stop_loss"
                break
            
            elif signal["type"] == "sell" and candle["high"] >= signal["stop_loss"]:
                trade_result["exit_price"] = signal["stop_loss"]
                trade_result["exit_time"] = datetime.datetime.fromtimestamp(candle["timestamp"] / 1000)
                trade_result["exit_reason"] = "stop_loss"
                break
            
            # Проверка тейк-профита
            if signal["type"] == "buy" and candle["high"] >= signal["take_profit"]:
                trade_result["exit_price"] = signal["take_profit"]
                trade_result["exit_time"] = datetime.datetime.fromtimestamp(candle["timestamp"] / 1000)
                trade_result["exit_reason"] = "take_profit"
                break
            
            elif signal["type"] == "sell" and candle["low"] <= signal["take_profit"]:
                trade_result["exit_price"] = signal["take_profit"]
                trade_result["exit_time"] = datetime.datetime.fromtimestamp(candle["timestamp"] / 1000)
                trade_result["exit_reason"] = "take_profit"
                break
            
            # Если это последняя свеча и сделка не закрыта
            if i == len(future_candles) - 1:
                trade_result["exit_price"] = candle["close"]
                trade_result["exit_time"] = datetime.datetime.fromtimestamp(candle["timestamp"] / 1000)
                trade_result["exit_reason"] = "end_of_data"
        
        # Расчет P&L
        if signal["type"] == "buy":
            trade_result["pnl"] = (trade_result["exit_price"] - trade_result["entry_price"]) * trade_result["position_size"]
        else:
            trade_result["pnl"] = (trade_result["entry_price"] - trade_result["exit_price"]) * trade_result["position_size"]
        
        trade_result["pnl_percent"] = (trade_result["pnl"] / current_capital) * 100
        
        return trade_result
    
    def _calculate_metrics(self, initial_capital: float, final_capital: float) -> Dict:
        """
        Расчет метрик эффективности.
        
        Args:
            initial_capital: Начальный капитал
            final_capital: Конечный капитал
            
        Returns:
            Dict: Метрики эффективности
        """
        # Расчет общей доходности
        total_return = ((final_capital / initial_capital) - 1) * 100
        
        # Расчет винрейта
        if not self.trades:
            win_rate = 0
        else:
            winning_trades = sum(1 for trade in self.trades if trade["pnl"] > 0)
            win_rate = (winning_trades / len(self.trades)) * 100
        
        # Расчет профит-фактора
        total_profit = sum(trade["pnl"] for trade in self.trades if trade["pnl"] > 0)
        total_loss = abs(sum(trade["pnl"] for trade in self.trades if trade["pnl"] < 0))
        
        if total_loss == 0:
            profit_factor = float('inf') if total_profit > 0 else 0
        else:
            profit_factor = total_profit / total_loss
        
        # Расчет максимальной просадки
        if not self.equity_curve:
            max_drawdown = 0
        else:
            # Преобразование в DataFrame для удобства расчетов
            equity_df = pd.DataFrame(self.equity_curve)
            
            # Расчет максимальной просадки
            equity_df['peak'] = equity_df['capital'].cummax()
            equity_df['drawdown'] = (equity_df['capital'] - equity_df['peak']) / equity_df['peak'] * 100
            max_drawdown = abs(equity_df['drawdown'].min())
        
        return {
            "total_return": total_return,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
            "total_trades": len(self.trades),
            "winning_trades": sum(1 for trade in self.trades if trade["pnl"] > 0),
            "losing_trades": sum(1 for trade in self.trades if trade["pnl"] < 0)
        }
    
    def visualize_results(self, save_path: Optional[str] = None) -> None:
        """
        Визуализация результатов бэктеста.
        
        Args:
            save_path: Путь для сохранения графика
        """
        if not self.equity_curve:
            self.logger.warning("No equity curve data to visualize")
            return
        
        # Создание DataFrame для удобства визуализации
        equity_df = pd.DataFrame(self.equity_curve)
        equity_df['timestamp'] = pd.to_datetime(equity_df['timestamp'], unit='ms')
        
        # Создание графика
        plt.figure(figsize=(12, 6))
        
        # График кривой капитала
        plt.plot(equity_df['timestamp'], equity_df['capital'], label='Equity Curve')
        
        # Добавление точек входа и выхода
        for trade in self.trades:
            entry_time = trade.get("entry_time")
            exit_time = trade.get("exit_time")
            
            if isinstance(entry_time, str):
                entry_time = datetime.datetime.fromisoformat(entry_time)
            
            if isinstance(exit_time, str):
                exit_time = datetime.datetime.fromisoformat(exit_time)
            
            if entry_time and exit_time:
                if trade["type"] == "buy":
                    plt.scatter(entry_time, trade["entry_price"], color='green', marker='^', s=100)
                    
                    if trade["exit_reason"] == "stop_loss":
                        plt.scatter(exit_time, trade["exit_price"], color='red', marker='v', s=100)
                    else:
                        plt.scatter(exit_time, trade["exit_price"], color='blue', marker='v', s=100)
                else:
                    plt.scatter(entry_time, trade["entry_price"], color='red', marker='v', s=100)
                    
                    if trade["exit_reason"] == "stop_loss":
                        plt.scatter(exit_time, trade["exit_price"], color='red', marker='^', s=100)
                    else:
                        plt.scatter(exit_time, trade["exit_price"], color='blue', marker='^', s=100)
        
        # Настройка графика
        plt.title('Backtest Results')
        plt.xlabel('Date')
        plt.ylabel('Capital')
        plt.grid(True)
        plt.legend()
        
        # Форматирование дат на оси X
        plt.gca().xaxis.set_major_formatter(DateFormatter('%Y-%m-%d'))
        plt.gcf().autofmt_xdate()
        
        # Сохранение или отображение графика
        if save_path:
            plt.savefig(save_path)
            self.logger.info(f"Results visualization saved to {save_path}")
        else:
            plt.show()

async def run_backtest(symbol: str, start_date: str, end_date: str, config_path: str = None, data_csv_path: str = None):
    """
    Запуск бэктеста из командной строки.
    
    Args:
        symbol: Торговая пара
        start_date: Начальная дата
        end_date: Конечная дата
        config_path: Путь к конфигурационному файлу
        data_csv_path: Путь к CSV файлу с историческими данными (опционально)
    """
    # Загрузка конфигурации
    if config_path:
        with open(config_path, 'r') as f:
            config = json.load(f)
    else:
        # Конфигурация по умолчанию
        config = {
            "testnet": True,
            "symbols": [symbol],
            "risk_per_trade": 0.02,
            "check_interval": 60,
            "macro_intervals": [
                {"start": "09:50", "end": "10:10", "name": "NY Morning"},
                {"start": "10:50", "end": "11:10", "name": "NY Mid-Morning"}
            ],
            "logging_level": "INFO"
        }
    
    # Если указан путь к CSV, добавляем его в конфигурацию
    if data_csv_path:
        config["data_csv_path"] = data_csv_path

    try:
        # Создание и запуск бэктестера
        backtester = MacroBacktester(config)
        results = await backtester.run_backtest(symbol, start_date, end_date)
        
        if results["success"]:
            print(f"Backtest completed successfully!")
            print(f"Initial capital: ${results['initial_capital']:.2f}")
            print(f"Final capital: ${results['final_capital']:.2f}")
            print(f"Total return: {results['metrics']['total_return']:.2f}%")
            print(f"Win rate: {results['metrics']['win_rate']:.2f}%")
            print(f"Profit factor: {results['metrics']['profit_factor']:.2f}")
            print(f"Max drawdown: {results['metrics']['max_drawdown']:.2f}%")
            print(f"Total trades: {results['metrics']['total_trades']}")
            
            # Визуализация результатов
            backtester.visualize_results("backtest_results.png")
        else:
            print(f"Backtest failed: {results['message']}")
    finally:
        # Закрытие соединения с биржей
        await backtester.exchange.close()

if __name__ == "__main__":
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description='Run backtest for Macro Trading Bot')
    parser.add_argument('--symbol', type=str, default='BTCUSDT', help='Trading pair')
    parser.add_argument('--start', type=str, required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--config', type=str, help='Path to config file')
    parser.add_argument('--data-csv', type=str, help='Path to CSV file with historical data')
    
    args = parser.parse_args()
    
    asyncio.run(run_backtest(args.symbol, args.start, args.end, args.config, data_csv_path=args.data_csv))
