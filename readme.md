# 🚀 Binance Real-Time Pro Chart & Alarm Manager

A powerful, self-hosted technical analysis dashboard built with Python and JavaScript. Unlike standard exchange charts, this tool captures raw tick data to generate **1-second timeframe candlesticks**, complete with a persistent database, professional indicators, and a customizable **Smart Alarm System**.

It is designed for scalpers and algo-traders who need granular data (1s, 5s) and custom alerts that standard platforms often charge for.

![Dashboard Screenshot](https://i.ibb.co.com/ccC58cW8/image.png)

## ✨ Key Features

### 🔔 Smart Alarm Manager (New!)
* **Custom Triggers:** Set alarms based on RSI conditions (e.g., `RSI < 30` on `15s` timeframe).
* **Background Monitoring:** Monitors **all configured assets** simultaneously in the background, even if you are viewing a different chart.
* **Audio & Visual Alerts:** Plays distinctive sounds (Beep/Bell) and shows Toast Notifications when triggered.
* **Persistent Config:** Alarms are saved in local storage, so they remain active after refreshing the browser.
* **Anti-Spam:** Intelligent cooldown system to prevent constant ringing.

### 📊 Professional Charting
* **Extreme Low Timeframes:** Real-time generation of **1s, 5s, 15s, and 30s** candles.
* **Multi-Asset Support:** Seamlessly switch between assets (e.g., `BTCUSDT`, `1000PEPEUSDT`).
* **Technical Indicators:**
    * **RSI (Wilder's Smoothing):** Mathematically identical to TradingView.
    * **Volume Histogram:** Color-coded (Up/Down) volume bars overlay.
* **Interactive Tools:**
    * **Measure Tool:** Ruler to calculate percentage (%) and price difference between two points.
    * **Sync:** Crosshair and time scale synchronization across Price and RSI charts.

### 💾 Backend & Architecture
* **Zero Latency:** Uses Binance Futures WebSocket (AggTrade) for millisecond-precision updates.
* **Data Persistence:** Automatically records history to CSV files in the `data/` folder.
* **Dynamic Precision:** Automatically adjusts price decimals for low-value assets (e.g., 7 decimals for PEPE).

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
```
Note: The first time you run this, the data/ folder will be created automatically.


### 4. Access the Dashboard

Open your web browser and navigate to:

`http://127.0.0.1:5000`

## 🎮 Usage Guide

**Setting an Alarm**
1. Click the 🔔 Alarms button in the top bar.
2. Select the Symbol (e.g., 1000PEPEUSDT) and Timeframe (e.g., 15s).
3. Set the condition (e.g., RSI < 28) and choose a sound.
4. Click + Add. The system will now monitor this condition in the background.

**Using the Measure Tool**
1. Click the 📐 Measure button.
2. Click once on the chart to set the Start Point.
3. Click again to set the End Point.
4. A tooltip will appear showing the % Change and Price Difference.

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
**Data Accumulation**: Since Binance does not provide historical 1-second data via API, this tool acts as a recorder. When you first start it, the chart will be empty. Leave it running to build up your own historical database (CSV).

**Browser Audio:** You might need to interact with the page (click anywhere) once after loading to allow the browser to play alarm sounds.

**Connection Issues (Indonesia Users)**: If you encounter [WinError 10060], your ISP is likely blocking Binance. Please use Cloudflare WARP (1.1.1.1) or a VPN to bypass the restriction.

## 🤝 Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## 📝 License
MIT