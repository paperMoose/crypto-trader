import json
import logging
from client import GeminiClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

ORDER_FILE = "orders.json"
client = GeminiClient()

def load_orders():
    try:
        with open(ORDER_FILE, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

def save_orders(data):
    with open(ORDER_FILE, "w") as file:
        json.dump(data, file, indent=4)

order_data = load_orders()

def place_order(symbol, amount, price, side, order_type):
    return client.place_order(symbol, amount, price, side, order_type)

def check_order_status(order_id):
    return client.check_order_status(order_id)

def main():
    logging.info("Monitoring orders...")
    
    for order_id, details in order_data.items():
        # Only check buy orders that are open and don't have sell orders placed yet
        if (details["side"] == "buy" and 
            details["status"] == "open" and 
            not details.get("sell_orders_placed")):
            
            status = check_order_status(order_id)
            
            if not status.get("is_live"):
                logging.info(f"Buy order {order_id} filled at {details['price']}.")
                order_data[order_id]["status"] = "filled"
                doge_amount = float(details["amount"])
                half_position = doge_amount / 2
                
                # Place stop loss order
                stop_loss = place_order(
                    symbol="dogeusdt",
                    amount=doge_amount,
                    price=0.24,
                    side="sell",
                    order_type="stop-limit",
                    stop_price=0.25
                )
                
                # Place take profit orders
                take_profit_1 = place_order(
                    symbol="dogeusdt",
                    amount=half_position,
                    price=0.50,
                    side="sell",
                    order_type="limit"
                )
                
                take_profit_2 = place_order(
                    symbol="dogeusdt",
                    amount=half_position,
                    price=0.60,
                    side="sell",
                    order_type="limit"
                )
                
                # Save the new orders
                if stop_loss:
                    order_data[stop_loss["order_id"]] = {
                        "type": "stop-loss",
                        "status": "open",
                        "price": 0.24,
                        "amount": doge_amount,
                        "side": "sell",
                        "parent_order": order_id
                    }
                
                if take_profit_1:
                    order_data[take_profit_1["order_id"]] = {
                        "type": "take-profit-1",
                        "status": "open",
                        "price": 0.50,
                        "amount": half_position,
                        "side": "sell",
                        "parent_order": order_id
                    }
                    
                if take_profit_2:
                    order_data[take_profit_2["order_id"]] = {
                        "type": "take-profit-2",
                        "status": "open",
                        "price": 0.60,
                        "amount": half_position,
                        "side": "sell",
                        "parent_order": order_id
                    }
                
                # Mark that we've placed sell orders for this buy
                order_data[order_id]["sell_orders_placed"] = True
                logging.info(f"Sell orders placed for buy order {order_id}")
                save_orders(order_data)

if __name__ == "__main__":
    main()
