"""
Основной модуль бота для торговли по стратегии "Макросы".
"""
import asyncio
import logging
import os
import sys
from typing import Dict, List, Optional

from .config.config_manager import ConfigManager
from .exchange.client import ExchangeClient
from .strategy.time_manager import MacroTimeManager
from .strategy.context_analyzer import ContextAnalyzer
from .strategy.zone_detector import InterestZoneDetector
from .strategy.scenario_analyzer import ScenarioAnalyzer
from .strategy.macro_executor import MacroExecutor
from .strategy.position_manager import PositionManager
from .utils.logger import setup_logger

class MacroTradingBot:
    """
    Основной класс бота для торговли по стратегии "Макросы".
    Объединяет все компоненты системы и управляет основным циклом работы.
    """
    
    def __init__(self, config_path: str = "config/config.json"):
        """
        Инициализация бота.
        
        Args:
            config_path: Путь к конфигурационному файлу
        """
        # Настройка логирования
        self.logger = setup_logger("macro_bot")
        self.logger.info("Initializing Macro Trading Bot")
        
        # Загрузка конфигурации
        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.get_config()
        
        # Инициализация клиента биржи
        self.exchange = ExchangeClient(
            api_key=self.config["api_key"],
            api_secret=self.config["api_secret"],
            testnet=self.config["testnet"]
        )
        
        # Инициализация компонентов стратегии
        self.time_manager = MacroTimeManager(self.config.get("macro_intervals"))
        self.context_analyzer = ContextAnalyzer(self.exchange)
        self.zone_detector = InterestZoneDetector()
        self.scenario_analyzer = ScenarioAnalyzer(self.context_analyzer, self.zone_detector, self.exchange)
        self.macro_executor = MacroExecutor(self.time_manager, self.scenario_analyzer, self.exchange)
        self.position_manager = PositionManager(self.exchange, self.config.get("risk_per_trade", 0.02))
        
        # Настройки
        self.symbols = self.config["symbols"]
        self.check_interval = self.config.get("check_interval", 60)  # секунды
        
        # Состояние
        self.running = False
    
    async def start(self):
        """
        Запуск бота.
        """
        self.running = True
        self.logger.info("Bot started")
        
        try:
            while self.running:
                try:
                    # Проверка для каждого символа
                    for symbol in self.symbols:
                        await self._process_symbol(symbol)
                    
                    # Проверка открытых позиций
                    await self._check_positions()
                    
                    # Пауза перед следующей проверкой
                    await asyncio.sleep(self.check_interval)
                    
                except Exception as e:
                    self.logger.error(f"Error in main loop: {str(e)}")
                    await asyncio.sleep(self.check_interval)
        
        finally:
            # Закрытие соединения с биржей
            await self.exchange.close()
            self.logger.info("Bot stopped")
    
    async def stop(self):
        """
        Остановка бота.
        """
        self.running = False
        self.logger.info("Stopping bot...")
    
    async def _process_symbol(self, symbol: str):
        """
        Обработка одного символа.
        
        Args:
            symbol: Торговая пара
        """
        # Проверка макро-интервала
        is_macro, macro_name = self.time_manager.is_active_macro()
        
        if is_macro:
            self.logger.info(f"Active macro detected for {symbol}: {macro_name}")
            
            # Мониторинг исполнения макроса
            entry_signal = await self.macro_executor.monitor_macro_execution(symbol)
            
            if entry_signal:
                self.logger.info(f"Entry signal generated for {symbol}: {entry_signal['type']}")
                
                # Исполнение сигнала
                result = await self.position_manager.execute_entry_signal(entry_signal)
                self.logger.info(result["message"])
        
        else:
            # Вне макро-интервала - подготовка и анализ
            await self._prepare_for_next_macro(symbol)
    
    async def _prepare_for_next_macro(self, symbol: str):
        """
        Подготовка к следующему макро-интервалу.
        
        Args:
            symbol: Торговая пара
        """
        # Анализ контекста
        context = await self.context_analyzer.analyze_daily_context(symbol)
        
        # Определение зон интереса
        minute_candles = await self.exchange.get_candles(symbol, '1m', limit=300)
        order_blocks = self.zone_detector.find_order_blocks(minute_candles, "bullish" if context["trend"] == "bullish" else "bearish")
        imbalances = self.zone_detector.find_imbalances(minute_candles)
        interest_zones = self.zone_detector.combine_interest_zones(
            order_blocks,
            imbalances,
            context["key_levels"]
        )
        
        # Логирование информации
        time_to_next = self.time_manager.time_to_next_macro()
        self.logger.info(f"Next macro for {symbol} in {time_to_next} minutes. Trend: {context['trend']}")
        
        # Если до следующего макро-интервала осталось менее 5 минут, выполняем предварительный анализ сценария
        if time_to_next <= 5:
            scenario = await self.scenario_analyzer.analyze_current_scenario(symbol)
            self.logger.info(f"Pre-macro scenario for {symbol}: {scenario['scenario']}, ready: {scenario['ready_for_macro']}")
    
    async def _check_positions(self):
        """
        Проверка открытых позиций.
        """
        updated_positions = await self.position_manager.check_positions()
        
        for position in updated_positions:
            if position.get("status") == "closed":
                self.logger.info(f"Position for {position['symbol']} closed")
            else:
                self.logger.debug(f"Position for {position['symbol']}: Entry: {position['entry_price']}, Current: {position.get('current_price')}, P&L: {position.get('pnl')}")

def main():
    """
    Точка входа для запуска бота.
    """
    # Настройка пути к конфигурационному файлу
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "config.json")
    
    # Создание и запуск бота
    bot = MacroTradingBot(config_path)
    
    # Обработка сигналов завершения
    loop = asyncio.get_event_loop()
    
    try:
        loop.run_until_complete(bot.start())
    except KeyboardInterrupt:
        loop.run_until_complete(bot.stop())
    finally:
        loop.close()

if __name__ == "__main__":
    main()
