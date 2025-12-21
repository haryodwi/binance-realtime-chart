import websocket
import json
import datetime

# --- KONFIGURASI ---
SYMBOL = "btcusdt"
SOCKET = f"wss://fstream.binance.com/ws/{SYMBOL}@aggTrade"

# --- VARIABEL GLOBAL (Untuk menyimpan data candle sementara) ---
current_candle = {
    "start_time": None,
    "open": 0,
    "high": 0,
    "low": 0,
    "close": 0,
    "volume": 0,
    "is_closed": False
}

def on_message(ws, message):
    global current_candle
    
    # 1. Parsing Data Mentah dari Binance
    data = json.loads(message)
    price = float(data['p'])
    qty = float(data['q'])
    event_time_ms = data['T'] # Waktu dalam milidetik
    
    # Konversi waktu transaksi ke detik (hilangkan milidetik)
    tick_second = int(event_time_ms / 1000)
    
    # --- LOGIKA AGREGASI CANDLE ---
    
    # A. Jika ini adalah data pertama kali program jalan
    if current_candle["start_time"] is None:
        current_candle["start_time"] = tick_second
        current_candle["open"] = price
        current_candle["high"] = price
        current_candle["low"] = price
        current_candle["close"] = price
        current_candle["volume"] = qty
        
    # B. Jika transaksi masih berada di DETIK YANG SAMA
    elif tick_second == current_candle["start_time"]:
        # Update High dan Low jika perlu
        current_candle["high"] = max(current_candle["high"], price)
        current_candle["low"] = min(current_candle["low"], price)
        # Update Close (selalu harga terakhir)
        current_candle["close"] = price
        # Tambah Volume
        current_candle["volume"] += qty
        
    # C. Jika waktu sudah pindah ke DETIK BARU (Candle Close!)
    elif tick_second > current_candle["start_time"]:
        # 1. Finalisasi Candle Sebelumnya
        print_candle(current_candle) # Cetak ke layar
        
        # 2. Reset untuk Candle Baru (Detik ini)
        current_candle["start_time"] = tick_second
        current_candle["open"] = price
        current_candle["high"] = price
        current_candle["low"] = price
        current_candle["close"] = price
        current_candle["volume"] = qty

def print_candle(candle):
    # Format waktu agar mudah dibaca manusia
    human_time = datetime.datetime.fromtimestamp(candle["start_time"]).strftime('%H:%M:%S')
    
    # Tentukan warna teks berdasarkan naik/turun (Hanya kosmetik terminal)
    # Hijau jika Close > Open, Merah jika Close < Open
    color_icon = "🟢" if candle["close"] >= candle["open"] else "🔴"
    
    print(f"[{human_time}] {color_icon} O:{candle['open']:.2f} | H:{candle['high']:.2f} | L:{candle['low']:.2f} | C:{candle['close']:.2f} | Vol:{candle['volume']:.3f}")

def on_error(ws, error):
    print(f"Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print("=== Koneksi Terputus ===")

def on_open(ws):
    print("=== Mengubah Tick menjadi Candle 1 Detik ===")
    print("Menunggu detik berganti...")

if __name__ == "__main__":
    # Jalankan WebSocket
    ws = websocket.WebSocketApp(
        SOCKET,
        on_open=on_open,
        on_close=on_close,
        on_message=on_message,
        on_error=on_error
    )
    ws.run_forever()