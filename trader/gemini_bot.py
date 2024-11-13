import logging
from trader.client import GeminiClient, Symbol, OrderSide, OrderType
from trader.database import (
    get_open_buy_orders,
    save_order,
    update_order,
    init_db
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

client = GeminiClient()

def place_order(symbol, amount, price, side, order_type, stop_price=None):
    return client.place_order(
        symbol=symbol,
        amount=amount,
        price=price,
        side=side,
        order_type=order_type,
        stop_price=stop_price
    )

def check_order_status(order_id):
    return client.check_order_status(order_id)

def main():
    # Update this line to use the new init_db function
    init_db()
    
    logging.info("Monitoring orders...")
    
    # Get all open buy orders that don't have sell orders placed
    open_orders = get_open_buy_orders()
    
    for order in open_orders:
        status = check_order_status(order.order_id)
        
        if not status.get("is_live"):
            logging.info(f"Buy order {order.order_id} filled at {order.price}.")
            
            # Update the buy order status
            update_order(
                order.order_id,
                status="filled",
                sell_orders_placed=True
            )
            
            doge_amount = float(order.amount)
            half_position = doge_amount / 2
            
            # Place stop loss order
            stop_loss = place_order(
                symbol=Symbol.DOGEUSD,
                amount=doge_amount,
                price="0.24",
                side=OrderSide.SELL,
                order_type=OrderType.EXCHANGE_STOP_LIMIT,
                stop_price="0.25"
            )
            
            # Place take profit orders
            take_profit_1 = place_order(
                symbol=Symbol.DOGEUSD,
                amount=half_position,
                price="0.50",
                side=OrderSide.SELL,
                order_type=OrderType.EXCHANGE_LIMIT
            )
            
            take_profit_2 = place_order(
                symbol=Symbol.DOGEUSD,
                amount=half_position,
                price="0.60",
                side=OrderSide.SELL,
                order_type=OrderType.EXCHANGE_LIMIT
            )
            
            # Save the new orders
            if stop_loss:
                save_order({
                    "order_id": stop_loss["order_id"],
                    "type": "stop-loss",
                    "status": "open",
                    "price": "0.24",
                    "amount": str(doge_amount),
                    "side": OrderSide.SELL.value,
                    "parent_order_id": order.order_id,
                    "symbol": Symbol.DOGEUSD.value,
                    "order_type": OrderType.EXCHANGE_STOP_LIMIT.value,
                    "stop_price": "0.25"
                })
            
            if take_profit_1:
                save_order({
                    "order_id": take_profit_1["order_id"],
                    "type": "take-profit-1",
                    "status": "open",
                    "price": "0.50",
                    "amount": str(half_position),
                    "side": OrderSide.SELL.value,
                    "parent_order_id": order.order_id,
                    "symbol": Symbol.DOGEUSD.value,
                    "order_type": OrderType.EXCHANGE_LIMIT.value
                })
                
            if take_profit_2:
                save_order({
                    "order_id": take_profit_2["order_id"],
                    "type": "take-profit-2",
                    "status": "open",
                    "price": "0.60",
                    "amount": str(half_position),
                    "side": OrderSide.SELL.value,
                    "parent_order_id": order.order_id,
                    "symbol": Symbol.DOGEUSD.value,
                    "order_type": OrderType.EXCHANGE_LIMIT.value
                })
            
            logging.info(f"Sell orders placed for buy order {order.order_id}")

if __name__ == "__main__":
    main()
