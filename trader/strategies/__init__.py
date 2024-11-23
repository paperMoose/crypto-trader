from .base import BaseStrategy
from .range_strategy import RangeStrategy
from .breakout_strategy import BreakoutStrategy
from .take_profit_strategy import TakeProfitStrategy
from trader.models import StrategyType

# Strategy mapping
STRATEGY_MAP = {
    StrategyType.RANGE: RangeStrategy,
    StrategyType.BREAKOUT: BreakoutStrategy,
    StrategyType.TAKE_PROFIT: TakeProfitStrategy
}

__all__ = [
    'BaseStrategy',
    'RangeStrategy',
    'BreakoutStrategy',
    'TakeProfitStrategy',
    'STRATEGY_MAP'
] 