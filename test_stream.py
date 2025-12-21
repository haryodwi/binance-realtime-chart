import websocket
import json
import datetime

# Konfigurasi Target Pair
SYMBOL = "btcusdt"
# Menggunakan stream aggTrade untuk kecepatan real-time (bahan baku candle 1 detik)
SOCKET = f"wss://fstream.binance.com/ws/{SYMBOL}@aggTrade"

def on_open(ws):
    print("=== Koneksi ke Binance Futures Terbuka ===")
    print(f"Mengambil data real-time untuk: {SYMBOL.upper()}")
    print("Menunggu data transaksi...")

def on_close(ws, close_status_code, close_msg):
    print("=== Koneksi Terputus ===")

def on_error(ws, error):
    print(f"Error: {error}")

def on_message(ws, message):
    # Data diterima dalam format JSON text, kita ubah ke Dictionary Python
    data = json.loads(message)
    
    # Struktur data aggTrade:
    # 'p': Price (Harga), 'q': Quantity (Jumlah), 'm': IsBuyerMaker (True=Sell, False=Buy)
    
    price = float(data['p'])
    qty = float(data['q'])
    is_sell = data['m'] # Jika True, berarti yang pasang limit order adalah pembeli (Buyer Maker) -> Taker-nya Seller
    
    # Menentukan warna untuk terminal (Hijau untuk Buy, Merah untuk Sell)
    # Ini simulasi sederhana visualisasi
    side = "SELL 🔴" if is_sell else "BUY  🟢"
    
    # Waktu saat ini
    time_now = datetime.datetime.now().strftime("%H:%M:%S")
    
    print(f"[{time_now}] {side} | Harga: {price:.2f} | Jumlah: {qty:.3f}")

if __name__ == "__main__":
    # Menjalankan WebSocketApp
    ws = websocket.WebSocketApp(
        SOCKET,
        on_open=on_open,
        on_close=on_close,
        on_message=on_message,
        on_error=on_error
    )
    # Run forever loop agar koneksi tidak putus
    ws.run_forever()