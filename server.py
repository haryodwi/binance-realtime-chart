import threading
import json
import websocket
import csv
import os
from collections import deque
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

# --- KONFIGURASI SERVER ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'rahasia_trading_pro'
socketio = SocketIO(app, cors_allowed_origins="*")

SYMBOL = "btcusdt"
SOCKET = f"wss://fstream.binance.com/ws/{SYMBOL}@aggTrade"
MAX_HISTORY = 2000  # Sesuai permintaan Anda

# --- CLASS PENGELOLA CANDLE DENGAN PENYIMPANAN FILE ---
class CandleManager:
    def __init__(self, interval):
        self.interval = interval
        self.filename = f"history_{interval}s.csv"
        
        # Buffer Memori (Deque otomatis membuang data lama jika > 2000)
        self.history_candles = deque(maxlen=MAX_HISTORY)
        self.history_closes = deque(maxlen=MAX_HISTORY) # Untuk hitungan RSI
        
        self.candle = None
        self.last_finalized_time = 0
        
        # 1. LOAD DATA DARI FILE SAAT STARTUP
        self.load_from_disk()

    def load_from_disk(self):
        """Membaca file CSV agar data tidak hilang saat restart"""
        if not os.path.exists(self.filename):
            return # File belum ada, skip

        try:
            with open(self.filename, 'r') as f:
                reader = csv.reader(f)
                loaded_data = []
                for row in reader:
                    if not row: continue
                    # Format CSV: time, open, high, low, close, volume
                    try:
                        c = {
                            "start_time": int(row[0]),
                            "open": float(row[1]), "high": float(row[2]),
                            "low": float(row[3]), "close": float(row[4]),
                            "volume": float(row[5])
                        }
                        loaded_data.append(c)
                    except ValueError: continue
                
                # Masukkan ke Memori (Ambil 2000 terakhir saja)
                recent_data = loaded_data[-MAX_HISTORY:]
                for c in recent_data:
                    self.history_candles.append(c)
                    self.history_closes.append(c['close'])
                
                # Hitung ulang RSI untuk data terakhir agar grafik RSI mulus
                self.recalculate_rsi_history()
                
                print(f"[{self.interval}s] Berhasil memuat {len(self.history_candles)} candle dari disk.")
        except Exception as e:
            print(f"Error loading {self.filename}: {e}")

    def save_to_disk(self, candle):
        """Menyimpan 1 baris candle baru ke file CSV (Append Mode)"""
        try:
            with open(self.filename, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    candle['start_time'], candle['open'], candle['high'], 
                    candle['low'], candle['close'], candle['volume']
                ])
        except Exception as e:
            print(f"Gagal menyimpan ke disk: {e}")

    def recalculate_rsi_history(self):
        """Hitung ulang RSI untuk semua history yang dimuat"""
        # Kita butuh loop ulang karena RSI bergantung data sebelumnya
        temp_closes = []
        for i, candle in enumerate(self.history_candles):
            temp_closes.append(candle['close'])
            # Hitung RSI parsial
            rsi_val = self._calculate_rsi_from_list(temp_closes)
            # Update nilai RSI di dalam deque
            self.history_candles[i]['rsi'] = rsi_val

    def update(self, price, qty, tick_second):
        if self.candle is None:
            self._new_candle(tick_second, price, qty)
            return

        # Cek Closing Candle
        if tick_second > self.candle['start_time'] and tick_second % self.interval == 0:
            if tick_second > self.last_finalized_time:
                self._close_candle()
                self._new_candle(tick_second, price, qty)
        else:
            # Update Candle Berjalan
            self.candle['high'] = max(self.candle['high'], price)
            self.candle['low'] = min(self.candle['low'], price)
            self.candle['close'] = price
            self.candle['volume'] += qty
            # Hitung RSI live
            current_closes = list(self.history_closes) + [price]
            self.candle['rsi'] = self._calculate_rsi_from_list(current_closes)
            
            socketio.emit(f'update_{self.interval}s', self.candle)

    def _new_candle(self, start_time, price, qty):
        aligned_time = start_time - (start_time % self.interval)
        current_closes = list(self.history_closes) + [price]
        rsi = self._calculate_rsi_from_list(current_closes)
        
        self.candle = {
            "start_time": aligned_time,
            "open": price, "high": price, "low": price, "close": price,
            "volume": qty, "rsi": rsi
        }

    def _close_candle(self):
        final_candle = self.candle.copy()
        
        # 1. Simpan ke Memori RAM
        self.history_candles.append(final_candle)
        self.history_closes.append(final_candle['close'])
        
        # 2. Simpan ke HARD DISK (CSV)
        self.save_to_disk(final_candle)
        
        socketio.emit(f'close_{self.interval}s', final_candle)
        self.last_finalized_time = self.candle['start_time'] + self.interval

    def _calculate_rsi_from_list(self, closes_list, period=14):
        if len(closes_list) < period + 1: return None
        
        # Ambil data secukupnya untuk efisiensi
        recent = closes_list[-(period+1):]
        gains, losses = [], []
        
        for i in range(1, len(recent)):
            diff = recent[i] - recent[i-1]
            if diff > 0: gains.append(diff); losses.append(0)
            else: gains.append(0); losses.append(abs(diff))
            
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0: return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

# --- INIT MANAGERS ---
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
        # Konversi deque ke list agar bisa dikirim via JSON
        history = list(managers[tf].history_candles)
        emit('history_response', {'tf': tf, 'data': history})

# --- WEBSOCKET BINANCE ---
def on_message(ws, message):
    try:
        data = json.loads(message)
        if 'p' in data:
            price = float(data['p'])
            qty = float(data['q'])
            tick_second = int(data['T'] / 1000)
            
            # Update SEMUA Timeframe di background
            for interval in managers:
                managers[interval].update(price, qty, tick_second)
    except Exception as e:
        print(f"Error processing data: {e}")

def run_stream():
    ws = websocket.WebSocketApp(SOCKET, on_message=on_message)
    ws.run_forever()

@app.route('/')
def index(): return render_template('index.html')

if __name__ == '__main__':
    t = threading.Thread(target=run_stream)
    t.daemon = True
    t.start()
    print("=== Server Persistent (2000 Data) Ready ===")
    socketio.run(app, debug=True, use_reloader=False)