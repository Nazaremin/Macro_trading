"""
Модуль для анализа сценариев рынка.
"""
import logging
from typing import Dict, List, Optional

from ..exchange.client import ExchangeClient
from .context_analyzer import ContextAnalyzer
from .zone_detector import InterestZoneDetector

class ScenarioAnalyzer:
    """
    Анализатор сценариев рынка.
    Определяет текущий сценарий, выявляет манипуляции и снятие ликвидности,
    отслеживает возврат цены в зону интереса и подтверждение структуры для входа.
    """
    
    def __init__(self, context_analyzer: ContextAnalyzer, zone_detector: InterestZoneDetector, exchange_client: ExchangeClient):
        """
        Инициализация анализатора сценариев.
        
        Args:
            context_analyzer: Анализатор контекста
            zone_detector: Детектор зон интереса
            exchange_client: Клиент биржи
        """
        self.context_analyzer = context_analyzer
        self.zone_detector = zone_detector
        self.exchange = exchange_client
        self.logger = logging.getLogger(__name__)
    
    async def analyze_current_scenario(self, symbol: str) -> Dict:
        """
        Анализ текущего сценария рынка.
        
        Args:
            symbol: Торговая пара (например, 'BTCUSDT')
            
        Returns:
            Dict: Результаты анализа сценария
        """
        # Получение контекста
        context = await self.context_analyzer.analyze_daily_context(symbol)
        
        # Получение минутных свечей для анализа текущей сессии
        minute_candles = await self.exchange.get_candles(symbol, '1m', limit=300)
        
        # Проверка на снятие ликвидности
        liquidity_sweep = self._detect_liquidity_sweep(minute_candles, context["liquidity_zones"])
        
        # Проверка на манипуляцию
        manipulation = self._detect_manipulation(minute_candles)
        
        # Определение зон интереса
        order_blocks = self.zone_detector.find_order_blocks(minute_candles, "bullish" if context["trend"] == "bullish" else "bearish")
        imbalances = self.zone_detector.find_imbalances(minute_candles)
        interest_zones = self.zone_detector.combine_interest_zones(
            order_blocks,
            imbalances,
            context["key_levels"]
        )
        
        # Проверка возврата в зону интереса
        return_to_zone = self._check_return_to_zone(minute_candles, interest_zones)
        
        # Проверка формирования структуры
        structure_formed = self._check_structure_formation(minute_candles)
        
        # Определение текущего сценария
        scenario = self._determine_scenario(
            context["trend"],
            liquidity_sweep,
            manipulation,
            return_to_zone,
            structure_formed
        )
        
        result = {
            "scenario": scenario,
            "liquidity_sweep": liquidity_sweep,
            "manipulation": manipulation,
            "interest_zones": interest_zones,
            "return_to_zone": return_to_zone,
            "structure_formed": structure_formed,
            "ready_for_macro": self._is_ready_for_macro(scenario)
        }
        
        self.logger.info(f"Scenario analysis for {symbol}: {scenario}, ready_for_macro={result['ready_for_macro']}")
        return result
    
    def _detect_liquidity_sweep(self, candles: List[Dict], liquidity_zones: List[Dict]) -> Dict:
        """
        Определение снятия ликвидности.
        
        Args:
            candles: Список свечей
            liquidity_zones: Зоны ликвидности
            
        Returns:
            Dict: Информация о снятии ликвидности
        """
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
    
    def _is_ready_for_macro(self, scenario: str) -> bool:
        """
        Проверка готовности к макро-интервалу.
        
        Args:
            scenario: Текущий сценарий
            
        Returns:
            bool: True, если готов к макро-интервалу
        """
        return scenario in [
            "bullish_continuation", 
            "bearish_continuation", 
            "potential_bullish_reversal", 
            "potential_bearish_reversal"
        ]
