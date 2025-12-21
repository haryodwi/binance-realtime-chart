import threading
import json
import time
import websocket
from flask import Flask, render_template
from flask_socketio import SocketIO

# --- KONFIGURASI SERVER ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'rahasia_dong'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- KONFIGURASI BINANCE ---
SYMBOL = "btcusdt"
SOCKET = f"wss://fstream.binance.com/ws/{SYMBOL}@aggTrade"

# --- VARIABEL GLOBAL ---
current_candle = {
    "start_time": None, "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0
}
closing_prices = [] # Menyimpan riwayat harga close untuk hitung RSI

# --- FUNGSI HITUNG RSI (MANUAL) ---
def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50 # Nilai default jika data belum cukup
    
    # Ambil data secukupnya
    recent_prices = prices[-(period+1):]
    
    gains = []
    losses = []
    
    for i in range(1, len(recent_prices)):
        diff = recent_prices[i] - recent_prices[i-1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# --- FUNGSI WEBSOCKET BINANCE ---
def on_message(ws, message):
    global current_candle, closing_prices
    
    data = json.loads(message)
    price = float(data['p'])
    qty = float(data['q'])
    event_time_ms = data['T']
    tick_second = int(event_time_ms / 1000)
    
    # --- LOGIKA RSI ---
    # Kita buat list sementara yang berisi history + harga sekarang
    # agar RSI bergerak real-time (ticking)
    temp_history = closing_prices + [price]
    rsi_value = calculate_rsi(temp_history)

    # 1. Inisialisasi Candle Pertama
    if current_candle["start_time"] is None:
        current_candle = {
            "start_time": tick_second, "open": price, "high": price, 
            "low": price, "close": price, "volume": qty, "rsi": rsi_value
        }
        
    # 2. Update Candle di Detik yang Sama
    elif tick_second == current_candle["start_time"]:
        current_candle["high"] = max(current_candle["high"], price)
        current_candle["low"] = min(current_candle["low"], price)
        current_candle["close"] = price
        current_candle["volume"] += qty
        current_candle["rsi"] = rsi_value # Update RSI live
        
        socketio.emit('candle_update', current_candle)
        
    # 3. Candle Close (Ganti Detik)
    elif tick_second > current_candle["start_time"]:
        # Simpan harga close ke history permanen untuk perhitungan RSI selanjutnya
        closing_prices.append(current_candle["close"])
        
        # Batasi history agar RAM tidak meledak (simpan 1000 data terakhir saja)
        if len(closing_prices) > 1000:
            closing_prices.pop(0)

        socketio.emit('candle_closed', current_candle)
        # print(f"Close: {current_candle['close']} | RSI: {current_candle['rsi']:.2f}") 
        
        # Reset candle baru
        current_candle = {
            "start_time": tick_second, "open": price, "high": price, 
            "low": price, "close": price, "volume": qty, "rsi": rsi_value
        }

def on_error(ws, error):
    print(f"Error WebSocket: {error}")

def on_close(ws, close_status_code, close_msg):
    print("=== Koneksi Binance Terputus ===")

def run_binance_stream():
    ws = websocket.WebSocketApp(
        SOCKET, on_open=lambda ws: print("=== Terhubung ke Binance ==="),
        on_message=on_message, on_error=on_error, on_close=on_close
    )
    ws.run_forever()

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    t = threading.Thread(target=run_binance_stream)
    t.daemon = True
    t.start()
    
    print("=== Server Berjalan di http://127.0.0.1:5000 ===")
    socketio.run(app, debug=True, use_reloader=False)