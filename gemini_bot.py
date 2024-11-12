import requests
import json
import time
import hmac
import hashlib
import base64
import logging
from config import API_KEY, API_SECRET, BASE_URL

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

ORDER_FILE = "orders.json"

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

def generate_signature(payload):
    b64 = base64.b64encode(json.dumps(payload).encode())
    signature = hmac.new(API_SECRET, b64, hashlib.sha384).hexdigest()
    return signature

def place_order(symbol, amount, price, side, order_type):
    url = BASE_URL + "/v1/order/new"
    nonce = str(int(time.time()))
    payload = {"request": "/v1/order/new", "nonce": nonce, "symbol": symbol, "amount": str(amount), "price": str(price), "side": side, "type": order_type}
    signature = generate_signature(payload)
    headers = {"Content-Type": "text/plain", "X-GEMINI-APIKEY": API_KEY, "X-GEMINI-PAYLOAD": base64.b64encode(json.dumps(payload).encode()), "X-GEMINI-SIGNATURE": signature}
    response = requests.post(url, headers=headers)
    return response.json()

def check_order_status(order_id):
    url = BASE_URL + "/v1/order/status"
    payload = {"request": "/v1/order/status", "nonce": str(int(time.time() * 1000)), "order_id": order_id}
    signature = generate_signature(payload)
    headers = {"Content-Type": "text/plain", "X-GEMINI-APIKEY": API_KEY, "X-GEMINI-PAYLOAD": base64.b64encode(json.dumps(payload).encode()), "X-GEMINI-SIGNATURE": signature}
    response = requests.post(url, headers=headers)
    return response.json()

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
