"""
Модуль для управления позициями.
"""
import logging
import datetime
from typing import Dict, List, Optional

from ..exchange.client import ExchangeClient

class PositionManager:
    """
    Менеджер позиций.
    Управляет открытием и закрытием позиций, расчетом размера позиции,
    установкой стоп-лоссов и тейк-профитов.
    """
    
    def __init__(self, exchange_client: ExchangeClient, risk_per_trade: float = 0.02):
        """
        Инициализация менеджера позиций.
        
        Args:
            exchange_client: Клиент биржи
            risk_per_trade: Риск на сделку (доля от депозита, по умолчанию 2%)
        """
        self.exchange = exchange_client
        self.risk_per_trade = risk_per_trade
        self.logger = logging.getLogger(__name__)
        self.open_positions = {}
    
    async def execute_entry_signal(self, signal: Dict) -> Dict:
        """
        Исполнение сигнала входа.
        
        Args:
            signal: Сигнал для входа
            
        Returns:
            Dict: Результат исполнения
        """
        # Расчет размера позиции
        account_balance = await self.exchange.get_account_balance()
        position_size = self._calculate_position_size(
            signal["price"],
            signal["stop_loss"],
            account_balance
        )
        
        self.logger.info(f"Executing {signal['type']} signal for {signal['symbol']} at {signal['price']}")
        self.logger.info(f"Position size: {position_size}, Stop-loss: {signal['stop_loss']}, Take-profit: {signal['take_profit']}")
        
        try:
            # Открытие позиции
            order_result = await self.exchange.create_order(
                symbol=signal["symbol"],
                side=signal["type"],
                quantity=position_size,
                price=signal["price"]
            )
            
            if order_result["status"] == "FILLED":
                # Установка стоп-лосса
                sl_order = await self.exchange.create_stop_loss_order(
                    symbol=signal["symbol"],
                    side="sell" if signal["type"] == "buy" else "buy",
                    quantity=position_size,
                    stop_price=signal["stop_loss"]
                )
                
                # Установка тейк-профита
                tp_order = await self.exchange.create_take_profit_order(
                    symbol=signal["symbol"],
                    side="sell" if signal["type"] == "buy" else "buy",
                    quantity=position_size,
                    stop_price=signal["take_profit"]
                )
                
                # Сохранение информации о позиции
                self.open_positions[order_result["orderId"]] = {
                    "symbol": signal["symbol"],
                    "type": signal["type"],
                    "entry_price": signal["price"],
                    "stop_loss": signal["stop_loss"],
                    "take_profit": signal["take_profit"],
                    "quantity": position_size,
                    "sl_order_id": sl_order["orderId"],
                    "tp_order_id": tp_order["orderId"],
                    "scenario": signal["scenario"],
                    "entry_time": datetime.datetime.now()
                }
                
                self.logger.info(f"Position opened: {signal['type']} {position_size} {signal['symbol']} at {signal['price']}")
                
                return {
                    "success": True,
                    "position_id": order_result["orderId"],
                    "message": f"Position opened: {signal['type']} {position_size} {signal['symbol']} at {signal['price']}"
                }
            else:
                self.logger.warning(f"Failed to open position: {order_result}")
                return {
                    "success": False,
                    "message": f"Failed to open position: {order_result}"
                }
                
        except Exception as e:
            self.logger.error(f"Error executing entry signal: {str(e)}")
            return {
                "success": False,
                "message": f"Error executing entry signal: {str(e)}"
            }
    
    async def check_positions(self) -> List[Dict]:
        """
        Проверка открытых позиций.
        
        Returns:
            List[Dict]: Список обновленных позиций
        """
        if not self.open_positions:
            return []
        
        updated_positions = []
        
        try:
            # Получение открытых позиций с биржи
            exchange_positions = await self.exchange.get_open_positions()
            
            # Обновление статуса позиций
            for position_id, position in list(self.open_positions.items()):
                # Проверяем, есть ли позиция еще на бирже
                exchange_position = next((p for p in exchange_positions if p["symbol"] == position["symbol"]), None)
                
                if not exchange_position:
                    # Позиция закрыта
                    self.logger.info(f"Position {position_id} for {position['symbol']} is closed")
                    
                    # Получаем историю ордеров, чтобы узнать, как была закрыта позиция
                    # (по стоп-лоссу или тейк-профиту)
                    # Это упрощенная версия, в реальности нужно проверять историю ордеров
                    
                    # Удаляем позицию из списка открытых
                    closed_position = self.open_positions.pop(position_id)
                    
                    # Добавляем информацию о закрытии
                    closed_position["status"] = "closed"
                    closed_position["close_time"] = datetime.datetime.now()
                    
                    updated_positions.append(closed_position)
                else:
                    # Позиция все еще открыта
                    # Обновляем информацию о текущей цене и P&L
                    current_price = await self.exchange.get_current_price(position["symbol"])
                    
                    pnl = 0
                    if position["type"] == "buy":
                        pnl = (current_price - position["entry_price"]) * position["quantity"]
                    else:
                        pnl = (position["entry_price"] - current_price) * position["quantity"]
                    
                    updated_position = {**position, "current_price": current_price, "pnl": pnl}
                    updated_positions.append(updated_position)
            
            return updated_positions
            
        except Exception as e:
            self.logger.error(f"Error checking positions: {str(e)}")
            return []
    
    async def close_position(self, position_id: str) -> Dict:
        """
        Закрытие позиции.
        
        Args:
            position_id: ID позиции
            
        Returns:
            Dict: Результат закрытия
        """
        if position_id not in self.open_positions:
            return {
                "success": False,
                "message": f"Position {position_id} not found"
            }
        
        position = self.open_positions[position_id]
        
        try:
            # Отмена стоп-лосса и тейк-профита
            await self.exchange.cancel_order(position["sl_order_id"], position["symbol"])
            await self.exchange.cancel_order(position["tp_order_id"], position["symbol"])
            
            # Закрытие позиции
            close_order = await self.exchange.create_order(
                symbol=position["symbol"],
                side="sell" if position["type"] == "buy" else "buy",
                quantity=position["quantity"],
                order_type="market"
            )
            
            # Удаление позиции из списка открытых
            closed_position = self.open_positions.pop(position_id)
            
            self.logger.info(f"Position {position_id} for {position['symbol']} manually closed")
            
            return {
                "success": True,
                "message": f"Position {position_id} for {position['symbol']} manually closed"
            }
            
        except Exception as e:
            self.logger.error(f"Error closing position {position_id}: {str(e)}")
            return {
                "success": False,
                "message": f"Error closing position {position_id}: {str(e)}"
            }
    
    def _calculate_position_size(self, entry_price: float, stop_loss: float, account_balance: float) -> float:
        """
        Расчет размера позиции на основе риска.
        
        Args:
            entry_price: Цена входа
            stop_loss: Цена стоп-лосса
            account_balance: Баланс аккаунта
            
        Returns:
            float: Размер позиции
        """
        # Расчет суммы риска
        risk_amount = account_balance * self.risk_per_trade
        
        # Расчет расстояния до стоп-лосса
        price_distance = abs(entry_price - stop_loss)
        
        # Расчет размера позиции
        position_size = risk_amount / price_distance
        
        # Округление до допустимого размера лота
        return self._round_position_size(position_size)
    
    def _round_position_size(self, size: float) -> float:
        """
        Округление размера позиции в соответствии с правилами биржи.
        
        Args:
            size: Исходный размер позиции
            
        Returns:
            float: Округленный размер позиции
        """
        # Округление до 5 знаков после запятой (для большинства криптовалют)
        return round(size, 5)
