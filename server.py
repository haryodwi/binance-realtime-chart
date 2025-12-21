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

SYMBOL = "btcusdt"
SOCKET = f"wss://fstream.binance.com/ws/{SYMBOL}@aggTrade"
MAX_HISTORY = 5000  

class CandleManager:
    def __init__(self, interval):
        self.interval = interval
        self.filename = f"history_{interval}s.csv"
        self.history_candles = deque(maxlen=MAX_HISTORY)
        self.history_closes = deque(maxlen=MAX_HISTORY)
        self.candle = None
        self.last_finalized_time = 0
        self.load_from_disk()

    def load_from_disk(self):
        if not os.path.exists(self.filename):
            print(f"[{self.interval}s] CSV baru. Menunggu data...")
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
                            "start_time": int(row[0]),
                            "open": float(row[1]), "high": float(row[2]),
                            "low": float(row[3]), "close": float(row[4]),
                            "volume": float(row[5])
                        }
                        temp_candles.append(c)
                        temp_closes.append(c['close'])
                    except ValueError: continue
                
                # --- PROSES RSI WILDER (FULL RECALCULATION) ---
                # Kita hitung ulang semua RSI dari awal agar akurat
                rsi_values = self._calculate_rsi_wilder_full(temp_closes)
                
                # Masukkan ke Memori dengan RSI yang sudah jadi
                for i, c in enumerate(temp_candles):
                    c['rsi'] = rsi_values[i]
                    self.history_candles.append(c)
                    self.history_closes.append(c['close'])
                
                print(f"[{self.interval}s] Loaded {len(self.history_candles)} candles. RSI synced.")
        except Exception as e:
            print(f"Error loading CSV: {e}")

    def save_to_disk(self, candle):
        try:
            with open(self.filename, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    candle['start_time'], candle['open'], candle['high'], 
                    candle['low'], candle['close'], candle['volume']
                ])
        except Exception: pass

    # --- RUMUS RSI WILDER (MIRIP TRADINGVIEW) ---
    def _calculate_rsi_wilder_full(self, closes, period=14):
        """Menghitung RSI untuk seluruh list harga dengan metode Wilder"""
        if not closes: return []
        
        rsi_result = []
        # Variabel untuk menyimpan state rata-rata gain/loss sebelumnya
        prev_avg_gain = 0
        prev_avg_loss = 0
        
        for i in range(len(closes)):
            # A. FASE AWAL (0 sampai 14 candle pertama)
            # Kita gunakan trik: hitung RSI dengan data yang ada saja (Backfill)
            if i == 0:
                rsi_result.append(50) # Candle pertama netral
                continue
            
            change = closes[i] - closes[i-1]
            gain = change if change > 0 else 0
            loss = abs(change) if change < 0 else 0
            
            if i < period:
                # Untuk 14 candle pertama, kita pakai SMA (Simple Moving Average)
                # Ini hanya untuk inisialisasi agar grafik tidak kosong
                # State disimpan akumulatif
                prev_avg_gain = (prev_avg_gain * (i-1) + gain) / i
                prev_avg_loss = (prev_avg_loss * (i-1) + loss) / i
            else:
                # B. FASE LANJUTAN (Wilder's Smoothing)
                # Formula: (Prev * 13 + Current) / 14
                prev_avg_gain = (prev_avg_gain * (period - 1) + gain) / period
                prev_avg_loss = (prev_avg_loss * (period - 1) + loss) / period
            
            # Hitung RSI
            if prev_avg_loss == 0:
                rsi = 100
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
            # Update Live Candle
            self.candle['high'] = max(self.candle['high'], price)
            self.candle['low'] = min(self.candle['low'], price)
            self.candle['close'] = price
            self.candle['volume'] += qty
            
            # Hitung RSI Live (Recalculate small window agar efisien)
            # Kita ambil 500 data terakhir cukup untuk akurasi Wilder
            temp_closes = list(self.history_closes)[-500:] + [price]
            live_rsis = self._calculate_rsi_wilder_full(temp_closes)
            if live_rsis:
                self.candle['rsi'] = live_rsis[-1]
            
            socketio.emit(f'update_{self.interval}s', self.candle)

    def _new_candle(self, start_time, price, qty):
        aligned_time = start_time - (start_time % self.interval)
        
        # Hitung RSI awal untuk candle baru
        temp_closes = list(self.history_closes)[-500:] + [price]
        live_rsis = self._calculate_rsi_wilder_full(temp_closes)
        rsi = live_rsis[-1] if live_rsis else 50
        
        self.candle = {
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

managers = {
    1: CandleManager(1),
    5: CandleManager(5),
    15: CandleManager(15),
    30: CandleManager(30)
}

@socketio.on('request_history')
def handle_history_request(data):
    tf = int(data['tf'])
    if tf in managers:
        history = list(managers[tf].history_candles)
        emit('history_response', {'tf': tf, 'data': history})

def on_message(ws, message):
    try:
        data = json.loads(message)
        if 'p' in data:
            price = float(data['p'])
            qty = float(data['q'])
            tick_second = int(data['T'] / 1000)
            for interval in managers: managers[interval].update(price, qty, tick_second)
    except: pass

def run_stream():
    while True:
        try:
            ws = websocket.WebSocketApp(SOCKET, on_message=on_message)
            ws.run_forever()
        except: time.sleep(2)

@app.route('/')
def index(): return render_template('index.html')

if __name__ == '__main__':
    t = threading.Thread(target=run_stream)
    t.daemon = True
    t.start()
    print("=== Server Wilder RSI Ready ===")
    socketio.run(app, debug=True, use_reloader=False)