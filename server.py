import threading, json, websocket, csv, os, time
from collections import deque
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

# --- CONFIG ---
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
        self.div_markers = deque(maxlen=MAX_HISTORY)
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
                        c = {"symbol": self.symbol, "start_time": int(row[0]), "open": float(row[1]), "high": float(row[2]), "low": float(row[3]), "close": float(row[4]), "volume": float(row[5])}
                        temp_candles.append(c)
                        temp_closes.append(c['close'])
                    except: continue
                
                rsi_values = self._calculate_rsi_wilder_full(temp_closes)
                ema_50 = self._calculate_ema(temp_closes, 50)
                ema_200 = self._calculate_ema(temp_closes, 200)
                
                for i, c in enumerate(temp_candles):
                    c['rsi'] = rsi_values[i]
                    c['ema50'] = ema_50[i]
                    c['ema200'] = ema_200[i]
                    self.history_candles.append(c)
                    self.history_closes.append(c['close'])
                
                # RECALCULATE SMC & DIV FULL
                self.smc_markers.extend(self._calculate_smc_advanced(list(self.history_candles)))
                self.div_markers.extend(self._calculate_divergence_bulk(list(self.history_candles)))

                print(f"[{self.symbol} {self.interval}s] Loaded {len(self.history_candles)} candles.")
        except Exception as e: print(f"Error loading {self.filename}: {e}")

    def save_to_disk(self, candle):
        try:
            with open(self.filename, 'a', newline='') as f:
                csv.writer(f).writerow([candle['start_time'], candle['open'], candle['high'], candle['low'], candle['close'], candle['volume']])
        except: pass

    # --- INDICATORS ---
    def _calculate_ema(self, closes, period):
        if len(closes) < period: return [None] * len(closes)
        ema = [None] * (period - 1); ema.append(sum(closes[:period]) / period)
        k = 2 / (period + 1)
        for i in range(period, len(closes)): ema.append((closes[i] - ema[-1]) * k + ema[-1])
        return ema

    def _calculate_rsi_wilder_full(self, closes, period=14):
        if not closes: return []
        rsi = []; pg = 0; pl = 0
        for i in range(len(closes)):
            if i==0: rsi.append(50); continue
            chg = closes[i] - closes[i-1]
            g = chg if chg > 0 else 0; l = abs(chg) if chg < 0 else 0
            if i < period: pg = (pg*(i-1)+g)/i; pl = (pl*(i-1)+l)/i
            else: pg = (pg*(period-1)+g)/period; pl = (pl*(period-1)+l)/period
            rsi.append(100 if pl==0 else 100-(100/(1+(pg/pl))))
        return rsi

    # --- ADVANCED SMC LOGIC (FIXED) ---
    def _calculate_smc_advanced(self, candles):
        markers = []
        if len(candles) < 10: return markers
        
        trend = 0 
        last_high = None 
        last_low = None  
        
        def is_pivot_high(i):
            return candles[i]['high'] > candles[i-1]['high'] and candles[i]['high'] > candles[i-2]['high'] and \
                   candles[i]['high'] > candles[i+1]['high'] and candles[i]['high'] > candles[i+2]['high']
        def is_pivot_low(i):
            return candles[i]['low'] < candles[i-1]['low'] and candles[i]['low'] < candles[i-2]['low'] and \
                   candles[i]['low'] < candles[i+1]['low'] and candles[i]['low'] < candles[i+2]['low']

        for i in range(2, len(candles) - 2):
            curr = candles[i]
            
            # 1. Update Swing Points
            if is_pivot_high(i):
                label = "H"; color = "#ef5350"
                # Logic sederhana: Jika Breakout High sebelumnya -> Strong High candidates
                markers.append({'time': curr['start_time'], 'position': 'aboveBar', 'color': color, 'shape': 'arrowDown', 'text': label})
                last_high = {'price': curr['high'], 'time': curr['start_time'], 'index': i}

            if is_pivot_low(i):
                label = "L"; color = "#26a69a"
                markers.append({'time': curr['start_time'], 'position': 'belowBar', 'color': color, 'shape': 'arrowUp', 'text': label})
                last_low = {'price': curr['low'], 'time': curr['start_time'], 'index': i}

            # 2. Break of Structure (BOS) & CHoCH
            # Bullish Break
            if last_high and curr['close'] > last_high['price']:
                txt = 'BOS' if trend == 1 else 'CHoCH'
                trend = 1
                markers.append({'time': curr['start_time'], 'position': 'aboveBar', 'color': '#00e676', 'shape': 'circle', 'text': txt})
                self._find_order_block(candles, i, 'bull', markers)
                last_high = {'price': curr['high'] * 1.0001, 'time': curr['start_time'], 'index': i} # Reset High

            # Bearish Break
            if last_low and curr['close'] < last_low['price']:
                txt = 'BOS' if trend == -1 else 'CHoCH'
                trend = -1
                markers.append({'time': curr['start_time'], 'position': 'belowBar', 'color': '#ff1744', 'shape': 'circle', 'text': txt})
                self._find_order_block(candles, i, 'bear', markers)
                last_low = {'price': curr['low'] * 0.9999, 'time': curr['start_time'], 'index': i} # Reset Low

        return markers

    def _find_order_block(self, candles, current_idx, direction, markers):
        lookback = 30 # Cari OB dalam 30 candle ke belakang
        start = max(0, current_idx - lookback)
        
        if direction == 'bull':
            # Bullish OB: Candle Merah terakhir sebelum rally
            for j in range(current_idx, start, -1):
                c = candles[j]
                if c['close'] < c['open']: 
                    markers.append({'time': c['start_time'], 'position': 'belowBar', 'color': '#2962ff', 'shape': 'square', 'text': 'OB'})
                    return 
        elif direction == 'bear':
            # Bearish OB: Candle Hijau terakhir sebelum dump
            for j in range(current_idx, start, -1):
                c = candles[j]
                if c['close'] > c['open']: 
                    markers.append({'time': c['start_time'], 'position': 'aboveBar', 'color': '#2962ff', 'shape': 'square', 'text': 'OB'})
                    return

    def _calculate_divergence_bulk(self, candles):
        markers = []
        if len(candles) < 10: return markers
        pivots_high = []; pivots_low = []
        for i in range(2, len(candles)-2):
            c = candles[i]
            if c['rsi'] is None: continue
            if c['high']>candles[i-1]['high'] and c['high']>candles[i-2]['high'] and c['high']>candles[i+1]['high'] and c['high']>candles[i+2]['high']:
                pivots_high.append({'idx': i, 'time': c['start_time'], 'price': c['high'], 'rsi': c['rsi']})
                if len(pivots_high) >= 2:
                    curr = pivots_high[-1]; prev = pivots_high[-2]
                    if (curr['idx'] - prev['idx']) < 60:
                        if curr['price'] > prev['price'] and curr['rsi'] < prev['rsi']:
                            markers.append({'time': curr['time'], 'position': 'aboveBar', 'color': '#ff0000', 'shape': 'circle', 'text': 'rBear', 'sound': 'bear'})
                        elif curr['price'] < prev['price'] and curr['rsi'] > prev['rsi']:
                            markers.append({'time': curr['time'], 'position': 'aboveBar', 'color': '#800000', 'shape': 'circle', 'text': 'hBear', 'sound': 'bear'})
            if c['low']<candles[i-1]['low'] and c['low']<candles[i-2]['low'] and c['low']<candles[i+1]['low'] and c['low']<candles[i+2]['low']:
                pivots_low.append({'idx': i, 'time': c['start_time'], 'price': c['low'], 'rsi': c['rsi']})
                if len(pivots_low) >= 2:
                    curr = pivots_low[-1]; prev = pivots_low[-2]
                    if (curr['idx'] - prev['idx']) < 60:
                        if curr['price'] < prev['price'] and curr['rsi'] > prev['rsi']:
                            markers.append({'time': curr['time'], 'position': 'belowBar', 'color': '#00ff00', 'shape': 'circle', 'text': 'rBull', 'sound': 'bull'})
                        elif curr['price'] > prev['price'] and curr['rsi'] < prev['rsi']:
                            markers.append({'time': curr['time'], 'position': 'belowBar', 'color': '#008000', 'shape': 'circle', 'text': 'hBull', 'sound': 'bull'})
        return markers

    def update(self, price, qty, tick_second):
        if self.candle is None: self._new_candle(tick_second, price, qty); return
        if tick_second > self.candle['start_time'] and tick_second % self.interval == 0:
            if tick_second > self.last_finalized_time: self._close_candle(); self._new_candle(tick_second, price, qty)
        else:
            self.candle['high'] = max(self.candle['high'], price); self.candle['low'] = min(self.candle['low'], price)
            self.candle['close'] = price; self.candle['volume'] += qty
            
            hist_len = len(self.history_closes); start = max(0, hist_len-500)
            rec = [self.history_closes[i] for i in range(start, hist_len)] + [price]
            rsi = self._calculate_rsi_wilder_full(rec); self.candle['rsi'] = rsi[-1] if rsi else 50
            ema50 = self._calculate_ema(rec, 50); self.candle['ema50'] = ema50[-1] if ema50 else None
            ema200 = self._calculate_ema(rec, 200); self.candle['ema200'] = ema200[-1] if ema200 else None
            socketio.emit(f'update_{self.interval}s', self.candle)

    def _new_candle(self, start_time, price, qty):
        aligned = start_time - (start_time % self.interval)
        hist_len = len(self.history_closes); start = max(0, hist_len-500)
        rec = [self.history_closes[i] for i in range(start, hist_len)] + [price]
        rsi = self._calculate_rsi_wilder_full(rec)
        ema50 = self._calculate_ema(rec, 50); ema200 = self._calculate_ema(rec, 200)
        self.candle = {"symbol": self.symbol, "start_time": aligned, "open": price, "high": price, "low": price, "close": price, "volume": qty, "rsi": rsi[-1] if rsi else 50, "ema50": ema50[-1] if ema50 else None, "ema200": ema200[-1] if ema200 else None}

    def _close_candle(self):
        final = self.candle.copy()
        self.history_candles.append(final)
        self.history_closes.append(final['close'])
        self.save_to_disk(final)
        
        # --- PERBAIKAN LOGIKA EMIT MARKER ---
        # Ambil 100 candle terakhir untuk analisis
        last_chunk = list(self.history_candles)[-100:]
        new_smc = self._calculate_smc_advanced(last_chunk)
        new_div = self._calculate_divergence_bulk(last_chunk)

        # FIX: Cek Duplikat agar marker "masa lalu" (Fractal) tetap terkirim tapi tidak double
        # Kita ambil hash (waktu + teks) dari 50 marker terakhir di memori
        existing_sigs = set()
        for m in list(self.smc_markers)[-50:]: existing_sigs.add((m['time'], m['text']))
        
        if new_smc:
            for m in new_smc:
                sig = (m['time'], m['text'])
                if sig not in existing_sigs: # Jika marker ini belum pernah disimpan
                    self.smc_markers.append(m)
                    socketio.emit(f'smc_new_{self.interval}s', {'symbol': self.symbol, 'marker': m})
        
        # Logic Divergence juga sama (Cek duplikat)
        existing_div_sigs = set()
        for d in list(self.div_markers)[-50:]: existing_div_sigs.add((d['time'], d['text']))

        if new_div:
            for d in new_div:
                sig = (d['time'], d['text'])
                if sig not in existing_div_sigs:
                    self.div_markers.append(d)
                    socketio.emit(f'divergence_new_{self.interval}s', {'symbol': self.symbol, 'marker': d})

        socketio.emit(f'close_{self.interval}s', final)
        self.last_finalized_time = self.candle['start_time'] + self.interval

# Pastikan ini ada di server.py Anda
managers = {}
for s in SYMBOLS:
    u = s.upper()
    managers[u] = {
        1: CandleManager(u, 1), 
        5: CandleManager(u, 5), 
        15: CandleManager(u, 15), 
        30: CandleManager(u, 30), 
        45: CandleManager(u, 45), 
        60: CandleManager(u, 60) # 1 Menit
    }

@socketio.on('request_history')
def handle_history_request(data):
    tf = int(data['tf']); sym = data['symbol']
    if sym in managers and tf in managers[sym]:
        mgr = managers[sym][tf]
        emit('history_response', {'symbol': sym, 'tf': tf, 'data': list(mgr.history_candles), 'smc': list(mgr.smc_markers), 'div': list(mgr.div_markers)})

def on_message(ws, message):
    try:
        j = json.loads(message); d = j['data']; s = j['stream'].split('@')[0].upper()
        if 'p' in d and s in managers:
            p=float(d['p']); q=float(d['q']); t=int(d['T']/1000)
            for i in managers[s]: managers[s][i].update(p, q, t)
    except: pass

def run_stream():
    while True:
        try: websocket.WebSocketApp(SOCKET, on_message=on_message).run_forever()
        except: time.sleep(2)

@app.route('/')
def index(): return render_template('index.html')

if __name__ == '__main__':
    t = threading.Thread(target=run_stream); t.daemon = True; t.start()
    print("=== Server Pro: Advanced SMC (Fixed) ===")
    socketio.run(app, debug=True, use_reloader=False)