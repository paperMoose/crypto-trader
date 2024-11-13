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
        if details["status"] == "open":
            status = check_order_status(order_id)
            if not status.get("is_live"):
                logging.info(f"Order {order_id} filled.")
                order_data[order_id]["status"] = "filled"
                save_orders(order_data)

if __name__ == "__main__":
    main()
