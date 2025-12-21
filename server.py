import threading
import json
import websocket
import csv
import os
import time
from collections import deque
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

# --- KONFIGURASI ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'rahasia_trading_pro'
socketio = SocketIO(app, cors_allowed_origins="*")

# DAFTAR ASET YANG INGIN DIPANTAU (Huruf kecil semua)
SYMBOLS = ["btcusdt", "1000pepeusdt"] 

# URL Combined Stream (Satu jalur untuk banyak koin)
# Format: /stream?streams=btcusdt@aggTrade/1000pepeusdt@aggTrade
stream_params = "/".join([f"{s}@aggTrade" for s in SYMBOLS])
SOCKET = f"wss://fstream.binance.com/stream?streams={stream_params}"

MAX_HISTORY = 5000  

class CandleManager:
    def __init__(self, symbol, interval):
        self.symbol = symbol.upper() # Simpan nama symbol (BTCUSDT)
        self.interval = interval
        # Nama file dibedakan per simbol: history_BTCUSDT_1s.csv, history_1000PEPEUSDT_1s.csv
        self.filename = f"history_{self.symbol}_{interval}s.csv"
        
        self.history_candles = deque(maxlen=MAX_HISTORY)
        self.history_closes = deque(maxlen=MAX_HISTORY)
        self.candle = None
        self.last_finalized_time = 0
        self.load_from_disk()

    def load_from_disk(self):
        if not os.path.exists(self.filename):
            print(f"[{self.symbol} {self.interval}s] CSV baru.")
            return

        try:
            with open(self.filename, 'r') as f:
                reader = csv.reader(f)
                temp_candles = []
                temp_closes = []
                for row in reader:
                    if not row or len(row) < 6: continue
                    try:
                        c = {
                            "symbol": self.symbol, # Tandai data ini milik siapa
                            "start_time": int(row[0]),
                            "open": float(row[1]), "high": float(row[2]),
                            "low": float(row[3]), "close": float(row[4]),
                            "volume": float(row[5])
                        }
                        temp_candles.append(c)
                        temp_closes.append(c['close'])
                    except ValueError: continue
                
                # Hitung RSI Wilder
                rsi_values = self._calculate_rsi_wilder_full(temp_closes)
                
                for i, c in enumerate(temp_candles):
                    c['rsi'] = rsi_values[i]
                    self.history_candles.append(c)
                    self.history_closes.append(c['close'])
                
                print(f"[{self.symbol} {self.interval}s] Loaded {len(self.history_candles)} candles.")
        except Exception as e:
            print(f"Error loading CSV {self.filename}: {e}")

    def save_to_disk(self, candle):
        try:
            with open(self.filename, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    candle['start_time'], candle['open'], candle['high'], 
                    candle['low'], candle['close'], candle['volume']
                ])
        except Exception: pass

    def _calculate_rsi_wilder_full(self, closes, period=14):
        if not closes: return []
        rsi_result = []
        prev_avg_gain = 0
        prev_avg_loss = 0
        
        for i in range(len(closes)):
            if i == 0:
                rsi_result.append(50)
                continue
            
            change = closes[i] - closes[i-1]
            gain = change if change > 0 else 0
            loss = abs(change) if change < 0 else 0
            
            if i < period:
                prev_avg_gain = (prev_avg_gain * (i-1) + gain) / i
                prev_avg_loss = (prev_avg_loss * (i-1) + loss) / i
            else:
                prev_avg_gain = (prev_avg_gain * (period - 1) + gain) / period
                prev_avg_loss = (prev_avg_loss * (period - 1) + loss) / period
            
            if prev_avg_loss == 0: rsi = 100
            else:
                rs = prev_avg_gain / prev_avg_loss
                rsi = 100 - (100 / (1 + rs))
            rsi_result.append(rsi)
        return rsi_result

    def update(self, price, qty, tick_second):
        if self.candle is None:
            self._new_candle(tick_second, price, qty)
            return

        if tick_second > self.candle['start_time'] and tick_second % self.interval == 0:
            if tick_second > self.last_finalized_time:
                self._close_candle()
                self._new_candle(tick_second, price, qty)
        else:
            self.candle['high'] = max(self.candle['high'], price)
            self.candle['low'] = min(self.candle['low'], price)
            self.candle['close'] = price
            self.candle['volume'] += qty
            
            temp_closes = list(self.history_closes)[-500:] + [price]
            live_rsis = self._calculate_rsi_wilder_full(temp_closes)
            if live_rsis: self.candle['rsi'] = live_rsis[-1]
            
            socketio.emit(f'update_{self.interval}s', self.candle)

    def _new_candle(self, start_time, price, qty):
        aligned_time = start_time - (start_time % self.interval)
        temp_closes = list(self.history_closes)[-500:] + [price]
        live_rsis = self._calculate_rsi_wilder_full(temp_closes)
        rsi = live_rsis[-1] if live_rsis else 50
        
        self.candle = {
            "symbol": self.symbol,
            "start_time": aligned_time, "open": price, "high": price, 
            "low": price, "close": price, "volume": qty, "rsi": rsi
        }

    def _close_candle(self):
        final_candle = self.candle.copy()
        self.history_candles.append(final_candle)
        self.history_closes.append(final_candle['close'])
        self.save_to_disk(final_candle)
        socketio.emit(f'close_{self.interval}s', final_candle)
        self.last_finalized_time = self.candle['start_time'] + self.interval

# --- INISIALISASI MANAGERS (NESTED DICTIONARY) ---
# Struktur: managers['BTCUSDT'][5] = CandleManager Object
managers = {}
for s in SYMBOLS:
    symbol_upper = s.upper()
    managers[symbol_upper] = {
        1: CandleManager(symbol_upper, 1),
        5: CandleManager(symbol_upper, 5),
        15: CandleManager(symbol_upper, 15),
        30: CandleManager(symbol_upper, 30)
    }

@socketio.on('request_history')
def handle_history_request(data):
    tf = int(data['tf'])
    sym = data['symbol'] # Frontend harus kirim simbol apa yang diminta
    
    if sym in managers and tf in managers[sym]:
        history = list(managers[sym][tf].history_candles)
        emit('history_response', {'symbol': sym, 'tf': tf, 'data': history})

def on_message(ws, message):
    try:
        # Format Combined Stream: {"stream": "btcusdt@aggTrade", "data": {...}}
        msg_json = json.loads(message)
        stream_name = msg_json['stream']
        data = msg_json['data']
        
        # Ekstrak simbol dari nama stream (misal: "btcusdt@aggTrade" -> "BTCUSDT")
        symbol_raw = stream_name.split('@')[0].upper()
        
        if 'p' in data:
            price = float(data['p'])
            qty = float(data['q'])
            tick_second = int(data['T'] / 1000)
            
            # Update manager yang sesuai dengan simbol tersebut
            if symbol_raw in managers:
                for interval in managers[symbol_raw]:
                    managers[symbol_raw][interval].update(price, qty, tick_second)
    except Exception as e: 
        print("Error parsing:", e)

def run_stream():
    while True:
        try:
            print(f"Connecting to Combined Stream: {SYMBOLS}")
            ws = websocket.WebSocketApp(SOCKET, on_message=on_message)
            ws.run_forever()
        except: time.sleep(2)

@app.route('/')
def index(): return render_template('index.html')

if __name__ == '__main__':
    t = threading.Thread(target=run_stream)
    t.daemon = True
    t.start()
    print("=== Server Multi-Asset Ready ===")
    socketio.run(app, debug=True, use_reloader=False)