"""
Модуль для исполнения макросов.
"""
import logging
import datetime
from typing import Dict, List, Optional, Tuple

from ..exchange.client import ExchangeClient
from .time_manager import MacroTimeManager
from .scenario_analyzer import ScenarioAnalyzer

class MacroExecutor:
    """
    Исполнитель макросов.
    Отслеживает активные макро-интервалы, движение цены и генерирует сигналы для входа.
    """
    
    def __init__(self, time_manager: MacroTimeManager, scenario_analyzer: ScenarioAnalyzer, exchange_client: ExchangeClient):
        """
        Инициализация исполнителя макросов.
        
        Args:
            time_manager: Менеджер временных интервалов
            scenario_analyzer: Анализатор сценариев
            exchange_client: Клиент биржи
        """
        self.time_manager = time_manager
        self.scenario_analyzer = scenario_analyzer
        self.exchange = exchange_client
        self.logger = logging.getLogger(__name__)
        
        self.active_macro = False
        self.current_scenario = None
        self.entry_signals = []
    
    async def monitor_macro_execution(self, symbol: str) -> Optional[Dict]:
        """
        Мониторинг исполнения макроса.
        
        Args:
            symbol: Торговая пара (например, 'BTCUSDT')
            
        Returns:
            Optional[Dict]: Сигнал для входа или None
        """
        # Проверка, находимся ли мы в макро-интервале
        is_macro, macro_name = self.time_manager.is_active_macro()
        
        if not is_macro:
            if self.active_macro:
                self.logger.info("Exiting macro interval")
                self.active_macro = False
            return None
        
        # Если макро только начался
        if not self.active_macro:
            self.active_macro = True
            self.logger.info(f"Entering macro interval: {macro_name}")
            
            # Анализ текущего сценария
            self.current_scenario = await self.scenario_analyzer.analyze_current_scenario(symbol)
            
            # Если нет четкого сценария, пропускаем
            if self.current_scenario["scenario"] == "no_clear_scenario":
                self.logger.info("No clear scenario detected, skipping macro")
                return None
            
            self.logger.info(f"Current scenario: {self.current_scenario['scenario']}")
        
        # Получение текущей цены
        current_price = await self.exchange.get_current_price(symbol)
        
        # Проверка исполнения сценария
        execution_result = self._check_scenario_execution(
            current_price,
            self.current_scenario
        )
        
        if execution_result["executed"]:
            # Генерация сигнала для входа
            entry_signal = self._generate_entry_signal(
                symbol,
                execution_result["type"],
                current_price,
                self.current_scenario,
                execution_result["zone"]
            )
            
            self.entry_signals.append(entry_signal)
            self.logger.info(f"Entry signal generated: {entry_signal['type']} {symbol} at {current_price}")
            return entry_signal
        
        return None
    
    def _check_scenario_execution(self, current_price: float, scenario: Dict) -> Dict:
        """
        Проверка исполнения сценария.
        
        Args:
            current_price: Текущая цена
            scenario: Текущий сценарий
            
        Returns:
            Dict: Результат проверки исполнения
        """
        # Проверка доставки цены в зону интереса
        
        if scenario["scenario"] == "bullish_continuation":
            for zone in scenario["interest_zones"]:
                if current_price >= zone["low"] and current_price <= zone["high"]:
                    return {"executed": True, "type": "buy", "zone": zone}
        
        elif scenario["scenario"] == "bearish_continuation":
            for zone in scenario["interest_zones"]:
                if current_price >= zone["low"] and current_price <= zone["high"]:
                    return {"executed": True, "type": "sell", "zone": zone}
        
        elif scenario["scenario"] == "potential_bullish_reversal":
            # Для разворотного сценария требуются дополнительные подтверждения
            if scenario["liquidity_sweep"]["detected"] and scenario["liquidity_sweep"]["type"] == "buy_stops_sweep":
                for zone in scenario["interest_zones"]:
                    if current_price >= zone["low"] and current_price <= zone["high"]:
                        return {"executed": True, "type": "buy", "zone": zone}
        
        elif scenario["scenario"] == "potential_bearish_reversal":
            # Для разворотного сценария требуются дополнительные подтверждения
            if scenario["liquidity_sweep"]["detected"] and scenario["liquidity_sweep"]["type"] == "sell_stops_sweep":
                for zone in scenario["interest_zones"]:
                    if current_price >= zone["low"] and current_price <= zone["high"]:
                        return {"executed": True, "type": "sell", "zone": zone}
        
        return {"executed": False}
    
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
            stop_loss = self._calculate_stop_loss(price, "buy", scenario, zone)
            take_profit = self._calculate_take_profit(price, stop_loss, "buy", scenario)
        else:
            # Для медвежьего сценария
            stop_loss = self._calculate_stop_loss(price, "sell", scenario, zone)
            take_profit = self._calculate_take_profit(price, stop_loss, "sell", scenario)
        
        return {
            "symbol": symbol,
            "type": signal_type,
            "price": price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "time": datetime.datetime.now(),
            "scenario": scenario["scenario"],
            "confidence": self._calculate_confidence(scenario),
            "zone_type": zone["type"]
        }
    
    def _calculate_stop_loss(self, price: float, signal_type: str, scenario: Dict, zone: Dict) -> float:
        """
        Расчет стоп-лосса на основе структуры и сценария.
        
        Args:
            price: Цена входа
            signal_type: Тип сигнала ('buy' или 'sell')
            scenario: Текущий сценарий
            zone: Зона интереса
            
        Returns:
            float: Цена стоп-лосса
        """
        # Для бычьего сценария стоп-лосс размещается под зоной интереса
        if signal_type == "buy":
            # Добавляем небольшой отступ (0.2%)
            return zone["low"] * 0.998
        
        # Для медвежьего сценария стоп-лосс размещается над зоной интереса
        else:
            # Добавляем небольшой отступ (0.2%)
            return zone["high"] * 1.002
    
    def _calculate_take_profit(self, price: float, stop_loss: float, signal_type: str, scenario: Dict) -> float:
        """
        Расчет тейк-профита с соотношением риск/прибыль.
        
        Args:
            price: Цена входа
            stop_loss: Цена стоп-лосса
            signal_type: Тип сигнала ('buy' или 'sell')
            scenario: Текущий сценарий
            
        Returns:
            float: Цена тейк-профита
        """
        # Расчет размера риска
        risk = abs(price - stop_loss)
        
        # Для основного сценария - более агрессивные цели (1:3)
        if scenario["scenario"] in ["bullish_continuation", "bearish_continuation"]:
            risk_reward_ratio = 3.0
        # Для разворотного - консервативные (1:2)
        else:
            risk_reward_ratio = 2.0
        
        # Расчет тейк-профита
        if signal_type == "buy":
            return price + (risk * risk_reward_ratio)
        else:
            return price - (risk * risk_reward_ratio)
    
    def _calculate_confidence(self, scenario: Dict) -> float:
        """
        Расчет уверенности в сигнале на основе всех факторов.
        
        Args:
            scenario: Текущий сценарий
            
        Returns:
            float: Уровень уверенности (от 0 до 1)
        """
        # Базовая уверенность
        confidence = 0.5
        
        # Увеличиваем уверенность, если есть снятие ликвидности
        if scenario["liquidity_sweep"]["detected"]:
            confidence += 0.1
        
        # Увеличиваем уверенность, если есть манипуляция
        if scenario["manipulation"]["detected"]:
            confidence += 0.1
        
        # Увеличиваем уверенность, если есть возврат в зону интереса
        if scenario["return_to_zone"]["detected"]:
            confidence += 0.1
        
        # Увеличиваем уверенность, если есть формирование структуры
        if scenario["structure_formed"]["detected"]:
            confidence += 0.1
        
        # Для основного сценария уверенность выше
        if scenario["scenario"] in ["bullish_continuation", "bearish_continuation"]:
            confidence += 0.1
        
        # Ограничиваем уверенность до 1.0
        return min(confidence, 1.0)
