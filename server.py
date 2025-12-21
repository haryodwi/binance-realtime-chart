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

# --- VARIABEL GLOBAL CANDLE ---
current_candle = {
    "start_time": None, "open": 0, "high": 0, "low": 0, "close": 0, "volume": 0
}

# --- FUNGSI WEBSOCKET BINANCE (BACKEND) ---
def on_message(ws, message):
    global current_candle
    
    data = json.loads(message)
    price = float(data['p'])
    qty = float(data['q'])
    event_time_ms = data['T']
    tick_second = int(event_time_ms / 1000)
    
    # 1. Inisialisasi Candle Pertama
    if current_candle["start_time"] is None:
        current_candle = {
            "start_time": tick_second, "open": price, "high": price, 
            "low": price, "close": price, "volume": qty
        }
        
    # 2. Update Candle di Detik yang Sama
    elif tick_second == current_candle["start_time"]:
        current_candle["high"] = max(current_candle["high"], price)
        current_candle["low"] = min(current_candle["low"], price)
        current_candle["close"] = price
        current_candle["volume"] += qty
        
        # PENTING: Kirim update "real-time" ke browser meskipun candle belum close
        # Ini supaya chart terlihat bergerak naik turun (ticking)
        socketio.emit('candle_update', current_candle)
        
    # 3. Candle Close (Ganti Detik)
    elif tick_second > current_candle["start_time"]:
        # Kirim sinyal bahwa candle sudah FINAL (Close)
        socketio.emit('candle_closed', current_candle)
        print(f"Candle Closed: {current_candle['close']}") # Log di terminal
        
        # Reset candle baru
        current_candle = {
            "start_time": tick_second, "open": price, "high": price, 
            "low": price, "close": price, "volume": qty
        }

def on_error(ws, error):
    print(f"Error WebSocket: {error}")

def on_close(ws, close_status_code, close_msg):
    print("=== Koneksi Binance Terputus ===")

def run_binance_stream():
    """Fungsi ini berjalan di thread terpisah agar tidak memblokir Web Server"""
    ws = websocket.WebSocketApp(
        SOCKET, on_open=lambda ws: print("=== Terhubung ke Binance ==="),
        on_message=on_message, on_error=on_error, on_close=on_close
    )
    ws.run_forever()

# --- ROUTE WEBSITE ---
@app.route('/')
def index():
    return render_template('index.html')

# --- MAIN PROGRAM ---
if __name__ == '__main__':
    # 1. Jalankan Penyedot Data Binance di Thread Belakang
    t = threading.Thread(target=run_binance_stream)
    t.daemon = True # Agar thread mati saat program dimatikan
    t.start()
    
    # 2. Jalankan Web Server
    print("=== Server Berjalan di http://127.0.0.1:5000 ===")
    socketio.run(app, debug=True, use_reloader=False) 
    # use_reloader=False penting agar thread tidak dijalankan 2 kali