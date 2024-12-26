import sys
import time
import logging
import ccxt
import json
from decimal import Decimal
from typing import Union, Dict, List
from chalicelib import utils, trade_processing

logger = logging.getLogger("app")

class BybitClient:
    """
    Bybit spot exchange

    Important notes:
    - This is an initial implementation, use at your own risk.
    """

    def __init__(self, base_currency: str):
        """
        Initialization with the base currency.

        Args:
            base_currency: Currency used for trading and for the calculation of available funds, e.g., USD or USDT.
        """

        self.client = None

        if not base_currency:
            raise ValueError("base currency not set")
        self.base_currency = base_currency

    def connect(self, secret_name: str, sandbox: bool=False, max_retries: int=3) -> bool:
        """
        Establishes connection to Bybit exchange.

        Args:
            secret_name: The name of the secret in AWS Secrets Manager.
            sandbox (optional): Determines whether to connect to exchange's sandbox env.
            max_retries (optional): Maximum number of retries. Defaults to 3.

        Returns:
            bool: True if connection is successful, False otherwise.
        """
        retries = 0
        while retries < max_retries:
            try:
                api_key_manager = utils.APIKeyManager(secret_name)
                api_key = api_key_manager.get_api_key()
                api_secret = api_key_manager.get_api_secret()

                logger.debug(f"Connecting to bybit with key {api_key}")

                exchange = ccxt.bybit({
                    "apiKey": api_key,
                    "secret": api_secret,
                    # TODO: proxy testing
                    #"proxies": {
                    #    "socksProxy": proxy,
                    #    "wsSocksProxy": proxy,
                    #},
                    "timeout": 6_000
                })

                # TODO: proxy testing
                #if proxy:
                #    exchange.socksProxy = proxy
                #    exchange.wsSocksProxy = proxy

                if sandbox:
                    exchange.set_sandbox_mode(True)

                self.markets = exchange.load_markets()
                #logger.debug(json.dumps(self.markets))

                self.client = exchange
                return True

            except ccxt.NetworkError as e:
                logger.error(f"Connection failed due to Network error: {str(e)}. Retrying the call.")
                time.sleep(3)
                retries +=1
            except ccxt.ExchangeError as e:
                logger.error(f"Exchange error while connecting: {e}")
                return False
            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}")
                raise e

        logger.error(f"Failed to connect to exchange after {max_retries} retries.")
        return False

    def create_limit_order(self, symbol: str, side: str, amount: float, order_price: float, max_retries: int=3):
        """
        Places a limit buy order on the bybit exchange.

        Args:
            symbol: The symbol representing the trading pair.
            side: 'buy' or 'sell'.
            amount: Amount of currency to buy
            order_price: Price to place sell order at.
            max_retries: Maximum number of retry attempts. Defaults to 3.

        Returns:
            dict or None: The order object if the order was successfully placed,
            or None if an error occurred.
        """
        retries = 0
        while retries < max_retries:
            try:
                order = self.client.create_limit_order(symbol, side, amount, order_price)
                logger.debug(f"Created limit order: {symbol} {side} {amount} {order_price}")
                return order

            except ccxt.NetworkError as e:
                if e == ccxt.RequestTimeout:
                    # Check if the order was placed
                    orders = self.client.fetch_open_orders(symbol)
                    if orders:
                        logger.info(f"RequestTimeout occurred: Confirmed buy order placed by fetching open orders.")
                        return orders[0]

                # Increment retry count
                logger.warning(f"Place sell failed due to network error: {str(e)}. Retrying the call.")
                time.sleep(3)  # Adding a delay before retrying
                retries += 1

            except ccxt.ExchangeError as e:
                logger.error(f"Exchange error occurred: {e}")
                return None

            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}")
                raise e

        logger.error(f"Failed to place sell order after {max_retries} retries.")
        return None

    def get_total_currency(self, currency: str, max_retries: int=3) -> Union[Decimal, None]:
        """
        Get the total amount of a given currency owned by the account.

        Args:
            exchange: The exchange object from ccxt.
            currency: The currency symbol to retrieve from the account balance.
            max_retries (optional): Maximum number of retries. Defaults to 3.

        Returns:
            Total number of the given currency owned by the account, or None if not found.
        """
        retries = 0
        while retries < max_retries:
            try:
                # Fetch account balance
                balance = self.client.fetch_balance()

                # Check if the currency exists in the balance
                if currency in balance:
                    total_currency = balance[currency].get("total", 0)
                    logger.debug(f"Retrieved total currency {currency}: {total_currency}")
                    return Decimal(str(total_currency))
                else:
                    # Currency not found in the balance
                    logger.warning(f"Currency '{currency}' not found in the account balance.")
                    return None

            except ccxt.NetworkError as e:
                logger.error(f"{self.client.id} fetch_balance failed due to a network error: {str(e)}")
                time.sleep(3)
                retries += 1

            except ccxt.ExchangeError as e:
                logger.error(f"{self.client.id} fetch_balance failed due to user error: {str(e)}")
                return None

            except Exception as e:
                logger.exception(f"{self.client.id} fetch_balance failed with: {str(e)}")
                raise e

        # If retry limit is reached
        logger.error(f"Failed to fetch account balance after {max_retries} retries.")
        return None

    def get_bid_ask(self, symbol: str, max_retries: int=3) -> tuple:
        """
        Get bid ask spread of symbol on exchange.

        Args:
            exchange: The exchange object from ccxt.
            symbol: Uppercase string literal name of a pair of traded currencies
            with a slash in between.
            max_retries (optional): Maximum number of retries. Defaults to 3.

        Returns:
            Tuple containing current bid and ask price of symbol on exchange.
            If fetching the ticker fails, returns None for both bid and ask.
        """
        retries = 0
        while retries < max_retries:
            try:
                # Validate inputs
                if not isinstance(self.client, ccxt.Exchange):
                    raise ValueError("exchange must be a valid ccxt.Exchange object")
                if not isinstance(symbol, str):
                    raise ValueError("symbol must be a string")

                # Fetch ticker
                ticker = self.client.fetch_ticker(symbol)

                bid = Decimal(str(ticker.get("bid"))) if ticker.get("bid") is not None else None
                ask = Decimal(str(ticker.get("ask"))) if ticker.get("ask") is not None else None

                logger.debug(f"Retrieved bid and ask for {symbol}: {bid} {ask}")

                return bid, ask

            except ccxt.NetworkError as e:
                logger.error(f"Network error while fetching ticker: {e}")
                time.sleep(3)
                retries += 1

            except ccxt.ExchangeError as e:
                logger.error(f"Exchange error while fetching ticker: {e}")
                return None, None

            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}")
                raise e

        # If retry limit is reached
        logger.error(f"Failed to fetch ticker after {max_retries} retries.")
        return None, None

    def get_last_price(self, symbol: str, max_retries: int=3) -> Decimal:
        """
        Get last price of symbol on exchange.

        Args:
            symbol: Uppercase string literal name of a pair of traded currencies
            with a slash in between.
            max_retries (optional): Maximum number of retries. Defaults to 3.

        Returns:
            Last price of symbol on exchange as Decimal object.
            If fetching the ticker fails, returns None.
        """
        retries = 0
        while retries < max_retries:
            try:
                # Validate inputs
                if not isinstance(self.client, ccxt.Exchange):
                    raise ValueError("exchange must be a valid ccxt.Exchange object")
                if not isinstance(symbol, str):
                    raise ValueError("symbol must be a string")

                # Fetch ticker
                ticker = self.client.fetch_ticker(symbol)

                last = Decimal(str(ticker.get("last"))) if ticker.get("last") is not None else None

                logger.debug(f"Retrieved last price for {symbol}: {last}")

                return last

            except ccxt.NetworkError as e:
                logger.error(f"Network error while fetching ticker: {e}")
                time.sleep(3)
                retries += 1

            except ccxt.ExchangeError as e:
                logger.error(f"Exchange error while fetching ticker: {e}")
                return None

            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}")
                raise e

        # If retry limit is reached
        logger.error(f"Failed to fetch ticker after {max_retries} retries.")
        return None

    def get_account_allocation(self, max_retries: int=3) -> Dict:
        """
        Gets the cost in usd at time of purchase for each active strategy in the account.

        Args:
            max_retries (optional): Maximum number of retries. Defaults to 3.

        Returns:
            Dict: A dictionary containing the allocation of the account.
        """
        retries = 0
        while retries < max_retries:
            try:
                balance = self.client.fetch_balance()
                available_funds_usd = balance.get("free").get(self.base_currency)
                logger.debug(f"Available funds in {self.base_currency}: {available_funds_usd}")
                active_configs = trade_processing.get_active_strategy_configs()
                logger.debug(f"Active strategy: {active_configs}")
                allocation_dict = dict()
                allocation_dict["USD"] = available_funds_usd
                for config in active_configs:
                    symbol = config.get("symbol")
                    currency = config.get("currency")
                    trades = self.get_most_recent_trade(symbol)
                    if trades:
                        trade_value_usd = self.get_trade_value_usd(trades)
                        logger.debug(f"Found most recent trade for {symbol}. The value still owned will be considered in the allocation: {trade_value_usd}.")
                        allocation_dict[currency] = trade_value_usd
                    else:
                        logger.debug(f"Found no trades for {symbol}. It will not be considered in the allocation.")
                        allocation_dict[currency] = 0
                logger.debug(f"Allocations: {allocation_dict}")
                return allocation_dict

            except ccxt.NetworkError as e:
                logger.error(f"Network error while fetching ticker: {e}")
                time.sleep(3)
                retries += 1

            except ccxt.ExchangeError as e:
                logger.error(f"Exchange error while fetching ticker: {e}")
                return None

            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}")
                raise e

    def get_total_usd(self) -> float:
        """
        Get total USD value of account before any unrealized trades.

        This function allows us to correctly allocate funds to a given strategy.

        Returns:
            Total funds of account in USD.
        """
        allocation_dict = self.get_account_allocation()
        sum = Decimal(str(sum(allocation_dict.values())))
        logger.debug(f"Calculated total USD: {sum}")

    def get_most_recent_trade(self, symbol: str, max_retries: int=3) -> List[Dict]:
        """
        Get the most recent open or closed trade of given symbol.

        A trade starts with a buy and ends with a sell that sets balance to 0.

        Args:
            symbol: Uppercase string literal name of a pair of traded currencies
            max_retries (optional): Maximum number of retries. Defaults to 3.

        Returns:
            List[Dict]: A list of dictionaries containing the order fills related to the last trade.
        """
        retries = 0
        while retries < max_retries:
            try:
                trades = self.client.fetch_my_trades(symbol)
                if trades:
                    prev_trade_side = None
                    for i, trade in enumerate(reversed(trades)):
                        side = trade.get("side")
                        if (prev_trade_side == "buy") & (side == "sell"):
                            most_recent_trade = trades[-i:]
                            logger.debug(f"Retrieved most recent trade with open and close transactions: {most_recent_trade}")
                            return most_recent_trade
                        elif side == "buy":
                            prev_trade_side = "buy"
                        elif side == "sell":
                            prev_trade_side = "sell"
                    else:
                        return trades
                else:
                    return []

            except ccxt.NetworkError as e:
                logger.error(f"Network error while fetching ticker: {e}")
                time.sleep(3)
                retries += 1

            except ccxt.ExchangeError as e:
                logger.error(f"Exchange error while fetching ticker: {e}")
                raise e

            except Exception as e:
                logger.error(f"An unexpected error occurred: {e}")
                raise e

    def get_trade_value_usd(self, trades: List[Dict]) -> float:
        """
        Calculate proportion of original purchase value of trade in USD that is still owned.

        Args:
            trades: A list of order fills for a trade.

        Returns:
            float: Original purchase price of trade in USD that is still owned.
        """
        trade_value_usd = 0
        amount_owned = 0
        amount_bought = 0

        for trade in trades:
            amount = trade.get("amount", 0)
            if trade.get("side") == "buy":
                amount_owned += amount
                amount_bought += amount
                trade_value_usd += trade.get("cost", 0)
            elif trade.get("side") == "sell":
                amount_owned -= amount

        if amount_bought == 0:
            return 0

        proportion_owned = round(amount_owned / amount_bought, 2)
        trade_value_usd_owned = trade_value_usd * proportion_owned

        logger.debug(f"Calculated total USD trade value, proportion still owned, value still owned: {trade_value_usd} {proportion_owned} {trade_value_usd_owned}")

        return trade_value_usd_owned

