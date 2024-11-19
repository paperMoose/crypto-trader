from enum import Enum

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(str, Enum):
    EXCHANGE_LIMIT = "exchange limit"
    EXCHANGE_STOP_LIMIT = "exchange stop limit"

class Symbol(str, Enum):
    DOGEUSD = "dogeusd"
    BTCUSD = "btcusd"
    # Add other symbols as needed

class OrderOption(str, Enum):
    MAKER_OR_CANCEL = "maker-or-cancel"
    IMMEDIATE_OR_CANCEL = "immediate-or-cancel"
    FILL_OR_KILL = "fill-or-kill"
    AUCTION_ONLY = "auction-only"
    INDICATION_OF_INTEREST = "indication-of-interest" 