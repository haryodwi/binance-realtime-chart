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

SYMBOLS = ["btcusdt", "1000pepeusdt"] 
DATA_DIR = "data"
if not os.path.exists(DATA_DIR): os.makedirs(DATA_DIR)

stream_params = "/".join([f"{s}@aggTrade" for s in SYMBOLS])
SOCKET = f"wss://fstream.binance.com/stream?streams={stream_params}"
MAX_HISTORY = 50000 

class CandleManager:
    def __init__(self, symbol, interval):
        self.symbol = symbol.upper()
        self.interval = interval
        self.filename = os.path.join(DATA_DIR, f"history_{self.symbol}_{interval}s.csv")
        
        self.history_candles = deque(maxlen=MAX_HISTORY)
        self.history_closes = deque(maxlen=MAX_HISTORY)
        self.smc_markers = deque(maxlen=MAX_HISTORY)
        
        self.candle = None
        self.last_finalized_time = 0
        self.load_from_disk()

    def load_from_disk(self):
        if not os.path.exists(self.filename): return
        try:
            with open(self.filename, 'r') as f:
                reader = csv.reader(f)
                temp_candles = []
                temp_closes = []
                for row in reader:
                    if not row or len(row) < 6: continue
                    try:
                        c = {
                            "symbol": self.symbol, "start_time": int(row[0]),
                            "open": float(row[1]), "high": float(row[2]),
                            "low": float(row[3]), "close": float(row[4]),
                            "volume": float(row[5])
                        }
                        temp_candles.append(c)
                        temp_closes.append(c['close'])
                    except ValueError: continue
                
                # Hitung Indikator (RSI & EMA)
                rsi_values = self._calculate_rsi_wilder_full(temp_closes)
                ema_50 = self._calculate_ema(temp_closes, 50)
                ema_200 = self._calculate_ema(temp_closes, 200)
                
                # Hitung SMC
                markers = self._calculate_smc_bulk(temp_candles)

                for i, c in enumerate(temp_candles):
                    c['rsi'] = rsi_values[i]
                    c['ema50'] = ema_50[i]
                    c['ema200'] = ema_200[i]
                    self.history_candles.append(c)
                    self.history_closes.append(c['close'])
                
                for m in markers: self.smc_markers.append(m)
                    
                print(f"[{self.symbol} {self.interval}s] Loaded {len(self.history_candles)} candles.")
        except Exception as e:
            print(f"Error loading {self.filename}: {e}")

    def save_to_disk(self, candle):
        try:
            with open(self.filename, 'a', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([candle['start_time'], candle['open'], candle['high'], candle['low'], candle['close'], candle['volume']])
        except: pass

    # --- HITUNG EMA (EXPONENTIAL MOVING AVERAGE) ---
    def _calculate_ema(self, closes, period):
        if len(closes) < period: return [None] * len(closes)
        
        ema_values = [None] * (period - 1)
        # SMA awal sebagai titik start
        sma = sum(closes[:period]) / period
        ema_values.append(sma)
        
        multiplier = 2 / (period + 1)
        
        for i in range(period, len(closes)):
            # EMA Hari ini = (Harga - EMA Kemarin) * Multiplier + EMA Kemarin
            val = (closes[i] - ema_values[-1]) * multiplier + ema_values[-1]
            ema_values.append(val)
            
        return ema_values

    def _calculate_smc_bulk(self, candles):
        markers = []
        if len(candles) < 5: return markers
        for i in range(2, len(candles) - 2):
            curr = candles[i]
            prev1, prev2 = candles[i-1], candles[i-2]
            next1, next2 = candles[i+1], candles[i+2]
            
            if curr['high'] > prev1['high'] and curr['high'] > prev2['high'] and curr['high'] > next1['high'] and curr['high'] > next2['high']:
                markers.append({'time': curr['start_time'], 'position': 'aboveBar', 'color': '#ef5350', 'shape': 'arrowDown', 'text': 'H'})
            if curr['low'] < prev1['low'] and curr['low'] < prev2['low'] and curr['low'] < next1['low'] and curr['low'] < next2['low']:
                markers.append({'time': curr['start_time'], 'position': 'belowBar', 'color': '#26a69a', 'shape': 'arrowUp', 'text': 'L'})
        return markers

    def _calculate_rsi_wilder_full(self, closes, period=14):
        if not closes: return []
        rsi_result = []
        prev_avg_gain = 0; prev_avg_loss = 0
        for i in range(len(closes)):
            if i == 0: rsi_result.append(50); continue
            change = closes[i] - closes[i-1]
            gain = change if change > 0 else 0; loss = abs(change) if change < 0 else 0
            if i < period:
                prev_avg_gain = (prev_avg_gain * (i-1) + gain) / i
                prev_avg_loss = (prev_avg_loss * (i-1) + loss) / i
            else:
                prev_avg_gain = (prev_avg_gain * (period - 1) + gain) / period
                prev_avg_loss = (prev_avg_loss * (period - 1) + loss) / period
            if prev_avg_loss == 0: rsi = 100
            else: rs = prev_avg_gain / prev_avg_loss; rsi = 100 - (100 / (1 + rs))
            rsi_result.append(rsi)
        return rsi_result

    def update(self, price, qty, tick_second):
        if self.candle is None: self._new_candle(tick_second, price, qty); return
        
        if tick_second > self.candle['start_time'] and tick_second % self.interval == 0:
            if tick_second > self.last_finalized_time: self._close_candle(); self._new_candle(tick_second, price, qty)
        else:
            self.candle['high'] = max(self.candle['high'], price)
            self.candle['low'] = min(self.candle['low'], price)
            self.candle['close'] = price
            self.candle['volume'] += qty
            
            # Optimasi Perhitungan Live (Ambil 500 data terakhir)
            history_len = len(self.history_closes)
            start_index = max(0, history_len - 500)
            recent_closes = [self.history_closes[i] for i in range(start_index, history_len)]
            recent_closes.append(price)
            
            # Hitung Indikator Live
            live_rsis = self._calculate_rsi_wilder_full(recent_closes)
            if live_rsis: self.candle['rsi'] = live_rsis[-1]
            
            # Hitung EMA Live
            live_ema50 = self._calculate_ema(recent_closes, 50)
            live_ema200 = self._calculate_ema(recent_closes, 200)
            if live_ema50: self.candle['ema50'] = live_ema50[-1]
            if live_ema200: self.candle['ema200'] = live_ema200[-1]
            
            socketio.emit(f'update_{self.interval}s', self.candle)

    def _new_candle(self, start_time, price, qty):
        aligned_time = start_time - (start_time % self.interval)
        
        # Init Indikator Awal
        history_len = len(self.history_closes)
        start_index = max(0, history_len - 500)
        recent_closes = [self.history_closes[i] for i in range(start_index, history_len)]
        recent_closes.append(price)
        
        live_rsis = self._calculate_rsi_wilder_full(recent_closes)
        rsi = live_rsis[-1] if live_rsis else 50
        
        live_ema50 = self._calculate_ema(recent_closes, 50)
        ema50 = live_ema50[-1] if live_ema50 else None
        
        live_ema200 = self._calculate_ema(recent_closes, 200)
        ema200 = live_ema200[-1] if live_ema200 else None

        self.candle = {
            "symbol": self.symbol, "start_time": aligned_time, 
            "open": price, "high": price, "low": price, "close": price, 
            "volume": qty, "rsi": rsi, "ema50": ema50, "ema200": ema200
        }

    def _close_candle(self):
        final_candle = self.candle.copy()
        self.history_candles.append(final_candle)
        self.history_closes.append(final_candle['close'])
        self.save_to_disk(final_candle)
        
        # SMC Check (Sama seperti sebelumnya)
        if len(self.history_candles) >= 5:
            last_5 = list(self.history_candles)[-5:]
            curr, prev1, prev2, next1, next2 = last_5[2], last_5[1], last_5[0], last_5[3], last_5[4]
            new_marker = None
            if curr['high'] > prev1['high'] and curr['high'] > prev2['high'] and curr['high'] > next1['high'] and curr['high'] > next2['high']:
                new_marker = {'time': curr['start_time'], 'position': 'aboveBar', 'color': '#ef5350', 'shape': 'arrowDown', 'text': 'H'}
            elif curr['low'] < prev1['low'] and curr['low'] < prev2['low'] and curr['low'] < next1['low'] and curr['low'] < next2['low']:
                new_marker = {'time': curr['start_time'], 'position': 'belowBar', 'color': '#26a69a', 'shape': 'arrowUp', 'text': 'L'}
            if new_marker:
                self.smc_markers.append(new_marker)
                socketio.emit(f'smc_new_{self.interval}s', {'symbol': self.symbol, 'marker': new_marker})

        socketio.emit(f'close_{self.interval}s', final_candle)
        self.last_finalized_time = self.candle['start_time'] + self.interval

managers = {}
for s in SYMBOLS:
    symbol_upper = s.upper()
    managers[symbol_upper] = {1: CandleManager(symbol_upper, 1), 5: CandleManager(symbol_upper, 5), 15: CandleManager(symbol_upper, 15), 30: CandleManager(symbol_upper, 30)}

@socketio.on('request_history')
def handle_history_request(data):
    tf = int(data['tf']); sym = data['symbol']
    if sym in managers and tf in managers[sym]:
        history = list(managers[sym][tf].history_candles)
        markers = list(managers[sym][tf].smc_markers)
        emit('history_response', {'symbol': sym, 'tf': tf, 'data': history, 'smc': markers})

def on_message(ws, message):
    try:
        msg_json = json.loads(message); stream_name = msg_json['stream']; data = msg_json['data']
        symbol_raw = stream_name.split('@')[0].upper()
        if 'p' in data:
            price = float(data['p']); qty = float(data['q']); tick_second = int(data['T'] / 1000)
            if symbol_raw in managers:
                for interval in managers[symbol_raw]: managers[symbol_raw][interval].update(price, qty, tick_second)
    except: pass

def run_stream():
    while True:
        try: ws = websocket.WebSocketApp(SOCKET, on_message=on_message); ws.run_forever()
        except: time.sleep(2)

@app.route('/')
def index(): return render_template('index.html')

if __name__ == '__main__':
    t = threading.Thread(target=run_stream); t.daemon = True; t.start()
    print("=== Server Pro (EMA + SMC) Ready ===")
    socketio.run(app, debug=True, use_reloader=False)