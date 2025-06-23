"""
Инициализация пакета.
"""
from .exchange.client import ExchangeClient
from .strategy.time_manager import MacroTimeManager
from .strategy.context_analyzer import ContextAnalyzer
from .strategy.zone_detector import InterestZoneDetector
from .strategy.scenario_analyzer import ScenarioAnalyzer
from .strategy.macro_executor import MacroExecutor
from .strategy.position_manager import PositionManager
from .config.config_manager import ConfigManager
from .utils.logger import setup_logger

__version__ = '1.0.0'
