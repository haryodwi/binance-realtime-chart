# 🚀 Binance Real-Time Pro Chart & Alarm Manager

A high-performance, self-hosted trading dashboard engineered for **scalpers** and **algorithmic traders**.

Unlike standard charting platforms, this tool captures raw tick data from Binance Futures to generate custom **1-second to 1-minute candlesticks**. It features a persistent flat-file database and a suite of "Institutional Grade" indicators usually reserved for premium subscriptions, including **Smart Money Concepts (SMC)**, **Real-Time Divergence Detection**, and **Dynamic EMAs**.

It is designed for scalpers and algo-traders who need granular data (1s, 5s) and custom alerts that standard platforms often charge for.

![Dashboard Screenshot](https://i.ibb.co.com/XrfZxH65/image.png)

## ✨ Key Features

### 🧠 Advanced Technical Indicators
* **⚡ Smart Money Concepts (SMC):**
    * **Market Structure:** Auto-detects **BOS** (Break of Structure) and **CHoCH** (Change of Character).
    * **Swing Points:** Identifies Fractal Highs (`H`) and Lows (`L`).
    * **Order Blocks:** Visualizes potential supply/demand zones (hidden automatically when switching timeframes for a clean UI).
* **🔀 Divergence Detector (RSI-based):**
    * **Regular Bullish (`rBull`)**: Trend Reversal (Buy).
    * **Hidden Bullish (`hBull`)**: Trend Continuation (Buy).
    * **Regular Bearish (`rBear`)**: Trend Reversal (Sell).
    * **Hidden Bearish (`hBear`)**: Trend Continuation (Sell).
* **📈 Dynamic EMA:** Exponential Moving Averages (EMA 50 & EMA 200) adjusted for low-cap asset precision.

### 🔔 Advanced Alert System
* **🔊 Divergence Config Panel (New!):** Toggle audio alerts for specific timeframes (e.g., mute 1s/5s, unmute 1m).
* **Custom RSI Alarms:** Set specific triggers (e.g., `RSI < 25`) that monitor the background.
* **Audio Cues:** Distinct sounds for standard alarms ("Beep/Bell") vs. Divergence detection ("Magic Chime").
* **Toast Notifications:** Non-intrusive visual pop-ups for every alert.

### 📊 Professional Charting Engine
* **Granular Timeframes:** 1s, 5s, 15s, 30s, **45s**, and **1m**.
* **Clean UI Architecture:** Smart caching ensures markers from one timeframe do not clutter another.
* **Multi-Asset Support:** Seamless switching (e.g., `BTCUSDT`, `1000PEPEUSDT`).
* **Timezone Awareness:** One-click switch between **New York** and **Jakarta** time.
* **Precision Handling:** Auto-adjusts decimals (e.g., 7 decimals for PEPE) for accurate indicator calculation.

## 🛠️ Tech Stack

* **Backend:** Python 3.x, Flask, Flask-SocketIO, Websocket-client.
* **Frontend:** HTML5, CSS3, JavaScript (Socket.IO Client).
* **Charting Library:** [TradingView Lightweight Charts](https://github.com/tradingview/lightweight-charts).
* **Data Storage:** CSV Flat-file database (Stored in `data/` folder).

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

**Indicator Legend**

| Syntax | Description |
| ----------- | ----------- |
| Marker | 	Color |	Meaning |
| BOS	 | 🟢/🔴 | 	Break of Structure: Trend continuation signal. |
| CHoCH	 | 🟢/🔴 | 	Change of Character: Potential trend reversal signal. |
| H / L	 | 🔻/🔺 | 	Swing High / Low: Market fractals. |
| rBull	 | 🟢 Bright | 	Regular Bullish Div: Price Lower Low, RSI Higher Low. |
| hBull	 | 🟢 Dark	 | Hidden Bullish Div: Price Higher Low, RSI Lower Low. |
| rBear	 | 🔴 Bright | 	Regular Bearish Div: Price Higher High, RSI Lower High. |
| hBear	 | 🔴 Dark	 | Hidden Bearish Div: Price Lower High, RSI Higher High. |
| EMA 50 | 	🟡 Yellow | 	Medium-term trend baseline. |
| EMA 200 | 	🟣 Purple | 	Long-term trend baseline. |

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