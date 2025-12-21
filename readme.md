# 📈 Binance Real-Time 1s Chart & Recorder

A high-performance, real-time financial charting tool built with Python and JavaScript. This application captures aggressive trade streams from Binance Futures to generate custom **1-second timeframe candlesticks**, which are not typically available on standard free charting platforms.

It features a persistent backend (CSV storage), multi-asset support, technical indicators (RSI & Volume), and interactive drawing tools.

![Screenshot](https://i.ibb.co.com/rRG2QrdT/image.png)

## ✨ Key Features

* **Extreme Low Timeframes:** Generates **1s, 5s, 15s, and 30s** candles from raw tick data.
* **Real-Time WebSocket:** Uses Binance AggTrade streams for zero-latency updates.
* **Multi-Asset Support:** Seamlessly switch between assets (e.g., `BTCUSDT`, `1000PEPEUSDT`).
* **Persistent Data Storage:** Automatically saves history to CSV files in the `data/` folder. No data loss on restart.
* **Technical Indicators:**
    * **RSI (Relative Strength Index):** Implements Wilder's Smoothing method (accurate to TradingView).
    * **Volume:** Real-time volume histogram with color-coding (Up/Down).
* **Interactive Tools:**
    * **Measurement Tool:** Measure price changes (%) and value difference with a ruler tool.
    * **Synchronized Charts:** Crosshair and time scale synchronization between Price and RSI charts.
    * **Dynamic Precision:** Automatically adjusts decimal precision for low-value assets (e.g., PEPE).

## 🛠️ Tech Stack

* **Backend:** Python 3.x, Flask, Flask-SocketIO, Websocket-client.
* **Frontend:** HTML5, CSS3, Socket.IO Client.
* **Charting Library:** [TradingView Lightweight Charts](https://github.com/tradingview/lightweight-charts).
* **Data Source:** Binance Futures WebSocket API.

## 🚀 Installation & Setup

### 1. Clone the Repository

```bash
git clone [https://github.com/username/repo-name.git](https://github.com/username/repo-name.git)
cd repo-name
```

### 2. Install Dependencies

It is recommended to use a virtual environment.

```bash

pip install flask flask-socketio websocket-client
```

### 3. Run the Server

```bash

python server.py
Note: The first time you run this, the data/ folder will be created automatically.
```

### 4. Access the Chart

Open your web browser and navigate to:

`[http://127.0.0.1:5000](http://127.0.0.1:5000)`

## ⚙️ Configuration
To add more assets, open server.py and modify the SYMBOLS list:

```Python

# server.py

# Add symbols in lowercase
SYMBOLS = ["btcusdt", "1000pepeusdt", "ethusdt", "solusdt"] 
```

To change the frontend precision (decimal places), open templates/index.html and update symbolSettings:

```JavaScript

// index.html

const symbolSettings = {
    "BTCUSDT": { precision: 2, minMove: 0.01 },
    "1000PEPEUSDT": { precision: 7, minMove: 0.0000001 },
    "ETHUSDT": { precision: 2, minMove: 0.01 } // Add new config
};
```

## ⚠️ Important Notes
Data Accumulation: Since Binance does not provide historical 1-second data via API, this tool acts as a recorder. When you first start it, the chart will be empty. Leave it running to build up your own historical database (CSV).

Connection Issues (Indonesia Users): If you encounter [WinError 10060], your ISP is likely blocking Binance. Please use Cloudflare WARP (1.1.1.1) or a VPN to bypass the restriction.

## 🤝 Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## 📝 License
MIT