import threading
import json
import websocket
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

# --- KONFIGURASI ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'rahasia'
socketio = SocketIO(app, cors_allowed_origins="*")

SYMBOL = "btcusdt"
SOCKET = f"wss://fstream.binance.com/ws/{SYMBOL}@aggTrade"

# --- CLASS PENGELOLA CANDLE & MEMORI ---
class CandleManager:
    def __init__(self, interval):
        self.interval = interval
        self.candle = None
        self.history_closes = []  # Untuk hitung rumus RSI
        self.history_candles = [] # MEMORI: Menyimpan candle utuh untuk dikirim ke browser
        self.last_finalized_time = 0

    def update(self, price, qty, tick_second):
        # 1. Inisialisasi Candle Baru
        if self.candle is None:
            self._new_candle(tick_second, price, qty)
            return

        # 2. Cek Closing Candle
        if tick_second > self.candle['start_time'] and tick_second % self.interval == 0:
            if tick_second > self.last_finalized_time:
                self._close_candle()
                self._new_candle(tick_second, price, qty)
        else:
            # 3. Update Candle Berjalan
            self.candle['high'] = max(self.candle['high'], price)
            self.candle['low'] = min(self.candle['low'], price)
            self.candle['close'] = price
            self.candle['volume'] += qty
            self.candle['rsi'] = self._calculate_rsi(price)
            
            # Kirim update "Ticking" (hanya ke user yang sedang lihat TF ini)
            socketio.emit(f'update_{self.interval}s', self.candle)

    def _new_candle(self, start_time, price, qty):
        aligned_time = start_time - (start_time % self.interval)
        rsi = self._calculate_rsi(price)
        self.candle = {
            "start_time": aligned_time,
            "open": price, "high": price, "low": price, "close": price,
            "volume": qty, "rsi": rsi
        }

    def _close_candle(self):
        # A. Update History Harga untuk Rumus RSI
        self.history_closes.append(self.candle['close'])
        if len(self.history_closes) > 1000: self.history_closes.pop(0)
        
        # B. SIMPAN KE MEMORI (Agar saat switch TF, grafik langsung penuh)
        # Kita copy dictionary agar tidak tertimpa referensinya
        final_candle = self.candle.copy()
        self.history_candles.append(final_candle)
        
        # Batasi memori server (misal simpan 500 candle terakhir per timeframe)
        if len(self.history_candles) > 500: self.history_candles.pop(0)
        
        # Kirim sinyal candle FINAL
        socketio.emit(f'close_{self.interval}s', final_candle)
        self.last_finalized_time = self.candle['start_time'] + self.interval

    def _calculate_rsi(self, current_price, period=14):
        temp_prices = self.history_closes + [current_price]
        if len(temp_prices) < period + 1: return 50
        
        gains, losses = [], []
        recent = temp_prices[-(period+1):]
        
        for i in range(1, len(recent)):
            diff = recent[i] - recent[i-1]
            if diff > 0: gains.append(diff); losses.append(0)
            else: gains.append(0); losses.append(abs(diff))
            
        avg_gain = sum(gains) / period
        avg_loss = sum(losses) / period
        
        if avg_loss == 0: return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

# --- INISIALISASI ---
managers = {
    1: CandleManager(1),
    5: CandleManager(5),
    15: CandleManager(15),
    30: CandleManager(30)
}

# --- EVENT HANDLER KHUSUS REQUEST HISTORY ---
@socketio.on('request_history')
def handle_history_request(data):
    # Saat browser minta data lama, kita ambil dari memori RAM Python
    tf = int(data['tf'])
    if tf in managers:
        history = managers[tf].history_candles
        # Kirim balik ke pengirim saja (emit)
        emit('history_response', {'tf': tf, 'data': history})

# --- WEBSOCKET BINANCE ---
def on_message(ws, message):
    data = json.loads(message)
    price = float(data['p'])
    qty = float(data['q'])
    tick_second = int(data['T'] / 1000)

    for interval in managers:
        managers[interval].update(price, qty, tick_second)

def run_stream():
    ws = websocket.WebSocketApp(SOCKET, on_message=on_message)
    ws.run_forever()

@app.route('/')
def index(): return render_template('index.html')

if __name__ == '__main__':
    t = threading.Thread(target=run_stream)
    t.daemon = True
    t.start()
    print("=== Server dengan Memory Ready di http://127.0.0.1:5000 ===")
    socketio.run(app, debug=True, use_reloader=False)