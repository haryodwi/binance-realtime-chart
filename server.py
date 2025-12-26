import threading, json, websocket, csv, os, time, uuid
from collections import deque
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

# --- CONFIG ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'rahasia_trading_pro'
socketio = SocketIO(app, cors_allowed_origins="*")

SYMBOLS = ["btcusdt", "1000pepeusdt", "solusdt", "ethusdt", "cfxusdt", "fartcoinusdt"] 
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
        
        # STATE:
        self.active_levels = [] # Dynamic SMC Lines
        self.div_markers = deque(maxlen=MAX_HISTORY) # Divergence Markers
        
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
                    c['rsi'] = rsi_values[i]; c['ema50'] = ema_50[i]; c['ema200'] = ema_200[i]
                    self.history_candles.append(c)
                    self.history_closes.append(c['close'])
                
                # RECALCULATE DIV ONLY (SMC Dynamic starts fresh)
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

    # --- DIVERGENCE LOGIC (RESTORED) ---
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
                            markers.append({'time': curr['time'], 'position': 'aboveBar', 'color': '#ff0000', 'shape': 'circle', 'text': 'rBear'})
                        elif curr['price'] < prev['price'] and curr['rsi'] > prev['rsi']:
                            markers.append({'time': curr['time'], 'position': 'aboveBar', 'color': '#800000', 'shape': 'circle', 'text': 'hBear'})
            if c['low']<candles[i-1]['low'] and c['low']<candles[i-2]['low'] and c['low']<candles[i+1]['low'] and c['low']<candles[i+2]['low']:
                pivots_low.append({'idx': i, 'time': c['start_time'], 'price': c['low'], 'rsi': c['rsi']})
                if len(pivots_low) >= 2:
                    curr = pivots_low[-1]; prev = pivots_low[-2]
                    if (curr['idx'] - prev['idx']) < 60:
                        if curr['price'] < prev['price'] and curr['rsi'] > prev['rsi']:
                            markers.append({'time': curr['time'], 'position': 'belowBar', 'color': '#00ff00', 'shape': 'circle', 'text': 'rBull'})
                        elif curr['price'] > prev['price'] and curr['rsi'] < prev['rsi']:
                            markers.append({'time': curr['time'], 'position': 'belowBar', 'color': '#008000', 'shape': 'circle', 'text': 'hBull'})
        return markers

    # --- DYNAMIC SMC ENGINE ---
    def _analyze_structure(self, candles):
        if len(candles) < 6: return []
        curr = candles[-3]; prev1, prev2 = candles[-4], candles[-5]; next1, next2 = candles[-2], candles[-1]
        new_levels = []

        # SWING HIGH
        if curr['high'] > prev1['high'] and curr['high'] > prev2['high'] and curr['high'] > next1['high'] and curr['high'] > next2['high']:
            lvl_id = str(uuid.uuid4())
            new_levels.append({'id': lvl_id, 'type': 'SWING_HIGH', 'price': curr['high'], 'text': 'High', 'color': '#ef5350', 'style': 2})
            self.active_levels.append(new_levels[-1])

        # SWING LOW
        if curr['low'] < prev1['low'] and curr['low'] < prev2['low'] and curr['low'] < next1['low'] and curr['low'] < next2['low']:
            lvl_id = str(uuid.uuid4())
            new_levels.append({'id': lvl_id, 'type': 'SWING_LOW', 'price': curr['low'], 'text': 'Low', 'color': '#26a69a', 'style': 2})
            self.active_levels.append(new_levels[-1])
            
        # ORDER BLOCKS
        body_size = abs(next2['close'] - next2['open'])
        prev_body_avg = sum([abs(candles[i]['close'] - candles[i]['open']) for i in range(-6, -2)]) / 4
        if body_size > 2 * prev_body_avg:
            if next2['close'] > next2['open']: # Bullish Impulsive
                ob_candle = next1 if next1['close'] < next1['open'] else prev1
                if ob_candle['close'] < ob_candle['open']:
                    ob_id = str(uuid.uuid4())
                    lvl = {'id': ob_id, 'type': 'OB_BULL', 'price': ob_candle['high'], 'bottom': ob_candle['low'], 'text': 'Bull OB +', 'color': '#2962ff', 'style': 1}
                    new_levels.append(lvl); self.active_levels.append(lvl)
            elif next2['close'] < next2['open']: # Bearish Impulsive
                ob_candle = next1 if next1['close'] > next1['open'] else prev1
                if ob_candle['close'] > ob_candle['open']:
                    ob_id = str(uuid.uuid4())
                    lvl = {'id': ob_id, 'type': 'OB_BEAR', 'price': ob_candle['low'], 'top': ob_candle['high'], 'text': 'Bear OB +', 'color': '#f50057', 'style': 1}
                    new_levels.append(lvl); self.active_levels.append(lvl)
        return new_levels

    def _check_mitigation(self, current_price):
        removed_ids = []; active_copy = []
        for lvl in self.active_levels:
            is_broken = False
            if lvl['type'] == 'SWING_HIGH' and current_price > lvl['price']: is_broken = True
            elif lvl['type'] == 'SWING_LOW' and current_price < lvl['price']: is_broken = True
            elif lvl['type'] == 'OB_BULL' and current_price < lvl.get('bottom', 0): is_broken = True
            elif lvl['type'] == 'OB_BEAR' and current_price > lvl.get('top', 999999): is_broken = True
            
            if is_broken: removed_ids.append(lvl['id'])
            else: active_copy.append(lvl)
        self.active_levels = active_copy
        return removed_ids

    def update(self, price, qty, tick_second):
        if self.candle is None: self._new_candle(tick_second, price, qty); return
        
        # Realtime Mitigation
        removed = self._check_mitigation(price)
        if removed: socketio.emit(f'smc_remove_{self.interval}s', {'symbol': self.symbol, 'ids': removed})

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
        
        # 1. Update SMC Dynamic
        if len(self.history_candles) >= 6:
            new_levels = self._analyze_structure(list(self.history_candles))
            if new_levels: socketio.emit(f'smc_add_{self.interval}s', {'symbol': self.symbol, 'levels': new_levels})

        # 2. Update Divergence
        last_chunk = list(self.history_candles)[-100:]
        new_div = self._calculate_divergence_bulk(last_chunk)
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

managers = {}
for s in SYMBOLS:
    u = s.upper()
    managers[u] = {1: CandleManager(u, 1), 5: CandleManager(u, 5), 15: CandleManager(u, 15), 30: CandleManager(u, 30), 45: CandleManager(u, 45), 60: CandleManager(u, 60)}

@socketio.on('request_history')
def handle_history_request(data):
    tf = int(data['tf']); sym = data['symbol']
    if sym in managers and tf in managers[sym]:
        mgr = managers[sym][tf]
        # Kirim SEMUA: Candle, SMC Lines Aktif, dan Div Markers
        emit('history_response', {'symbol': sym, 'tf': tf, 'data': list(mgr.history_candles), 'active_levels': mgr.active_levels, 'div': list(mgr.div_markers)})

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
    print("=== Server Pro: ALL FEATURES RESTORED ===")
    socketio.run(app, debug=True, use_reloader=False)