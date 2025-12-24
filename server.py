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
                
                # HITUNG SMC ADVANCED
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

    # --- ADVANCED SMC LOGIC (BOS, CHoCH, OB, Strong/Weak) ---
    def _calculate_smc_advanced(self, candles):
        markers = []
        if len(candles) < 10: return markers
        
        # State
        trend = 0 # 1 Bullish, -1 Bearish
        last_high = None # {price, time, index}
        last_low = None  # {price, time, index}
        
        # Helper: Deteksi Fractal (Pivot)
        def is_pivot_high(i):
            return candles[i]['high'] > candles[i-1]['high'] and candles[i]['high'] > candles[i-2]['high'] and \
                   candles[i]['high'] > candles[i+1]['high'] and candles[i]['high'] > candles[i+2]['high']
        def is_pivot_low(i):
            return candles[i]['low'] < candles[i-1]['low'] and candles[i]['low'] < candles[i-2]['low'] and \
                   candles[i]['low'] < candles[i+1]['low'] and candles[i]['low'] < candles[i+2]['low']

        # Loop Analisis Struktur
        for i in range(2, len(candles) - 2):
            curr = candles[i]
            
            # 1. Update Swing Points
            if is_pivot_high(i):
                # Validasi Swing High Baru
                if last_high is None or curr['high'] > last_high['price']:
                    # Jika sebelumnya Bullish, ini mungkin Higher High (Strong)
                    # Jika Bearish, ini mungkin Lower High (Weak High target liquidity)
                    label = "H" # Default
                    color = "#ef5350"
                    
                    # Logika Breakout (Hanya cek jika trend bullish)
                    if trend == 1 and last_high and curr['high'] > last_high['price']:
                         # Ini penerusan trend (BOS sebenarnya terjadi saat close menembus, tapi kita mark pivotnya)
                         pass
                    
                    markers.append({'time': curr['start_time'], 'position': 'aboveBar', 'color': color, 'shape': 'arrowDown', 'text': label})
                    last_high = {'price': curr['high'], 'time': curr['start_time'], 'index': i}

            if is_pivot_low(i):
                if last_low is None or curr['low'] < last_low['price']:
                    label = "L"
                    color = "#26a69a"
                    markers.append({'time': curr['start_time'], 'position': 'belowBar', 'color': color, 'shape': 'arrowUp', 'text': label})
                    last_low = {'price': curr['low'], 'time': curr['start_time'], 'index': i}

            # 2. Deteksi Break of Structure (BOS) & CHoCH (Berdasarkan Candle CLOSE)
            # Bullish Break
            if last_high and curr['close'] > last_high['price']:
                if trend == 1: # Continuation
                    markers.append({'time': curr['start_time'], 'position': 'aboveBar', 'color': '#00e676', 'shape': 'circle', 'text': 'BOS'})
                    # Tandai Order Block Bullish (Candle merah terakhir sebelum move ini)
                    self._find_order_block(candles, i, 'bull', markers)
                    last_high['price'] = curr['high'] # Update structure
                elif trend <= 0: # Reversal (Bear to Bull)
                    markers.append({'time': curr['start_time'], 'position': 'aboveBar', 'color': '#00e676', 'shape': 'circle', 'text': 'CHoCH'})
                    self._find_order_block(candles, i, 'bull', markers)
                    trend = 1
                
                # Reset High agar tidak spamming BOS di setiap candle yg naik
                last_high = {'price': curr['high'] * 1.0001, 'time': curr['start_time'], 'index': i} # Fake update biar gak trigger lg

            # Bearish Break
            if last_low and curr['close'] < last_low['price']:
                if trend == -1: # Continuation
                    markers.append({'time': curr['start_time'], 'position': 'belowBar', 'color': '#ff1744', 'shape': 'circle', 'text': 'BOS'})
                    self._find_order_block(candles, i, 'bear', markers)
                    last_low['price'] = curr['low']
                elif trend >= 0: # Reversal (Bull to Bear)
                    markers.append({'time': curr['start_time'], 'position': 'belowBar', 'color': '#ff1744', 'shape': 'circle', 'text': 'CHoCH'})
                    self._find_order_block(candles, i, 'bear', markers)
                    trend = -1
                
                last_low = {'price': curr['low'] * 0.9999, 'time': curr['start_time'], 'index': i}

        return markers

    def _find_order_block(self, candles, current_idx, direction, markers):
        # Cari mundur maksimal 50 candle
        lookback = 50
        start = max(0, current_idx - lookback)
        
        if direction == 'bull':
            # Cari candle MERAH (Bearish) terakhir sebelum impulsive move
            # Kita cari candle dengan Close < Open
            for j in range(current_idx, start, -1):
                c = candles[j]
                if c['close'] < c['open']: # Candle Merah ketemu
                    markers.append({'time': c['start_time'], 'position': 'belowBar', 'color': '#2962ff', 'shape': 'square', 'text': 'OB'})
                    return # Ketemu satu, stop
        
        elif direction == 'bear':
            # Cari candle HIJAU (Bullish) terakhir sebelum impulsive move
            for j in range(current_idx, start, -1):
                c = candles[j]
                if c['close'] > c['open']: # Candle Hijau ketemu
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
            
            # Live Indicators
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
        
        # Trigger SMC update setiap candle close (kita recalculate bulk kecil untuk efisiensi)
        # Ambil 100 candle terakhir saja untuk update marker terbaru
        last_chunk = list(self.history_candles)[-100:]
        new_smc = self._calculate_smc_advanced(last_chunk)
        new_div = self._calculate_divergence_bulk(last_chunk)

        # Filter marker yang HANYA terjadi di candle terakhir ini
        if new_smc:
            latest = [m for m in new_smc if m['time'] == final['start_time']]
            for m in latest:
                self.smc_markers.append(m)
                socketio.emit(f'smc_new_{self.interval}s', {'symbol': self.symbol, 'marker': m})
        
        if new_div:
            latest = [d for d in new_div if d['time'] == final['start_time']]
            for d in latest:
                self.div_markers.append(d)
                socketio.emit(f'divergence_new_{self.interval}s', {'symbol': self.symbol, 'marker': d})

        socketio.emit(f'close_{self.interval}s', final)
        self.last_finalized_time = self.candle['start_time'] + self.interval

managers = {}
for s in SYMBOLS:
    u = s.upper()
    managers[u] = {1: CandleManager(u, 1), 5: CandleManager(u, 5), 15: CandleManager(u, 15), 30: CandleManager(u, 30), 45: CandleManager(u, 45), 60: CandleManager(u, 60)}

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
    print("=== Server Pro: Advanced SMC Ready ===")
    socketio.run(app, debug=True, use_reloader=False)