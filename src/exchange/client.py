"""
Модуль для работы с API криптовалютных бирж.
"""
import asyncio
import logging
from typing import Dict, List, Optional, Union

import ccxt.async_support as ccxt

class ExchangeClient:
    """
    Клиент для работы с API криптовалютных бирж.
    Поддерживает основные операции для торговли.
    """
    
    def __init__(self, api_key: str = "", api_secret: str = "", testnet: bool = True):
        """
        Инициализация клиента биржи.
        
        Args:
            api_key: API ключ для доступа к бирже
            api_secret: Секретный ключ для доступа к бирже
            testnet: Использовать тестовую сеть (True) или реальную (False)
        """
        self.logger = logging.getLogger(__name__)
        
        # Настройка клиента Binance (можно добавить поддержку других бирж)
        options = {
            'defaultType': 'future',  # Используем фьючерсы по умолчанию
            'adjustForTimeDifference': True,
        }
        
        if testnet:
            options['test'] = True
        
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'options': options,
            'enableRateLimit': True
        })
        
        self.logger.info(f"Exchange client initialized. Testnet: {testnet}")
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def close(self):
        """Закрытие соединения с биржей."""
        await self.exchange.close()
        self.logger.info("Exchange connection closed")
    
    async def get_candles(self, symbol: str, timeframe: str = '1m', limit: int = 100) -> List[Dict]:
        """
        Получение исторических свечей.
        
        Args:
            symbol: Торговая пара (например, 'BTCUSDT')
            timeframe: Таймфрейм ('1m', '5m', '15m', '1h', '4h', '1d')
            limit: Количество свечей
            
        Returns:
            Список свечей в формате [{'timestamp': int, 'open': float, 'high': float, 
                                     'low': float, 'close': float, 'volume': float}, ...]
        """
        try:
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            # Преобразование в более удобный формат
            candles = []
            for candle in ohlcv:
                candles.append({
                    'timestamp': candle[0],
                    'open': candle[1],
                    'high': candle[2],
                    'low': candle[3],
                    'close': candle[4],
                    'volume': candle[5]
                })
            
            self.logger.debug(f"Got {len(candles)} candles for {symbol} on {timeframe} timeframe")
            return candles
            
        except Exception as e:
            self.logger.error(f"Error getting candles: {str(e)}")
            raise
    
    async def get_current_price(self, symbol: str) -> float:
        """
        Получение текущей цены.
        
        Args:
            symbol: Торговая пара (например, 'BTCUSDT')
            
        Returns:
            Текущая цена
        """
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            price = ticker['last']
            self.logger.debug(f"Current price for {symbol}: {price}")
            return price
        except Exception as e:
            self.logger.error(f"Error getting current price: {str(e)}")
            raise
    
    async def get_account_balance(self) -> float:
        """
        Получение баланса аккаунта.
        
        Returns:
            Общий баланс в USDT
        """
        try:
            balance = await self.exchange.fetch_balance()
            total_balance = balance['total']['USDT'] if 'USDT' in balance['total'] else 0
            self.logger.debug(f"Account balance: {total_balance} USDT")
            return total_balance
        except Exception as e:
            self.logger.error(f"Error getting account balance: {str(e)}")
            raise
    
    async def create_order(self, symbol: str, side: str, quantity: float, 
                          price: Optional[float] = None, order_type: str = 'market') -> Dict:
        """
        Создание ордера.
        
        Args:
            symbol: Торговая пара (например, 'BTCUSDT')
            side: Сторона ('buy' или 'sell')
            quantity: Количество
            price: Цена (для лимитных ордеров)
            order_type: Тип ордера ('market' или 'limit')
            
        Returns:
            Информация о созданном ордере
        """
        try:
            params = {}
            
            if order_type == 'market':
                order = await self.exchange.create_market_order(symbol, side, quantity, params=params)
            else:
                order = await self.exchange.create_limit_order(symbol, side, quantity, price, params=params)
            
            self.logger.info(f"Created {order_type} {side} order for {quantity} {symbol} at {price if price else 'market price'}")
            return order
        except Exception as e:
            self.logger.error(f"Error creating order: {str(e)}")
            raise
    
    async def create_stop_loss_order(self, symbol: str, side: str, quantity: float, 
                                   stop_price: float) -> Dict:
        """
        Создание стоп-лосс ордера.
        
        Args:
            symbol: Торговая пара (например, 'BTCUSDT')
            side: Сторона ('buy' или 'sell')
            quantity: Количество
            stop_price: Стоп-цена
            
        Returns:
            Информация о созданном ордере
        """
        try:
            params = {
                'stopPrice': stop_price,
            }
            
            order = await self.exchange.create_order(
                symbol=symbol,
                type='stop_market',
                side=side,
                amount=quantity,
                params=params
            )
            
            self.logger.info(f"Created stop-loss {side} order for {quantity} {symbol} at {stop_price}")
            return order
        except Exception as e:
            self.logger.error(f"Error creating stop-loss order: {str(e)}")
            raise
    
    async def create_take_profit_order(self, symbol: str, side: str, quantity: float, 
                                     stop_price: float) -> Dict:
        """
        Создание тейк-профит ордера.
        
        Args:
            symbol: Торговая пара (например, 'BTCUSDT')
            side: Сторона ('buy' или 'sell')
            quantity: Количество
            stop_price: Цена тейк-профита
            
        Returns:
            Информация о созданном ордере
        """
        try:
            params = {
                'stopPrice': stop_price,
                'reduceOnly': True
            }
            
            order = await self.exchange.create_order(
                symbol=symbol,
                type='take_profit_market',
                side=side,
                amount=quantity,
                params=params
            )
            
            self.logger.info(f"Created take-profit {side} order for {quantity} {symbol} at {stop_price}")
            return order
        except Exception as e:
            self.logger.error(f"Error creating take-profit order: {str(e)}")
            raise
    
    async def cancel_order(self, order_id: str, symbol: str) -> Dict:
        """
        Отмена ордера.
        
        Args:
            order_id: ID ордера
            symbol: Торговая пара
            
        Returns:
            Информация об отмененном ордере
        """
        try:
            result = await self.exchange.cancel_order(order_id, symbol)
            self.logger.info(f"Cancelled order {order_id} for {symbol}")
            return result
        except Exception as e:
            self.logger.error(f"Error cancelling order: {str(e)}")
            raise
    
    async def get_open_positions(self) -> List[Dict]:
        """
        Получение открытых позиций.
        
        Returns:
            Список открытых позиций
        """
        try:
            positions = await self.exchange.fetch_positions()
            open_positions = [p for p in positions if float(p['contracts']) > 0]
            
            self.logger.debug(f"Got {len(open_positions)} open positions")
            return open_positions
        except Exception as e:
            self.logger.error(f"Error getting open positions: {str(e)}")
            raise
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Получение открытых ордеров.
        
        Args:
            symbol: Торговая пара (опционально)
            
        Returns:
            Список открытых ордеров
        """
        try:
            orders = await self.exchange.fetch_open_orders(symbol=symbol)
            self.logger.debug(f"Got {len(orders)} open orders{f' for {symbol}' if symbol else ''}")
            return orders
        except Exception as e:
            self.logger.error(f"Error getting open orders: {str(e)}")
            raise
