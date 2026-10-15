# AI Trading Signals — Android Terminal

A high-performance algorithmic trading terminal for NSE/BSE equity indices (`NIFTY`, `BANKNIFTY`, `FINNIFTY`, `MIDCPNIFTY`, `SENSEX`, `BANKEX`).

## Core Architecture & Features

The primary Android APK excludes the dedicated SMC chart, MCX/commodities screens, and Order Flow/Footprint chart. Those chart modules are reserved for a separate APK.

### 1. 10-Minute Signal Stability Gate
- Algorithmic BUY candidates (`CALL BUY` or `PUT BUY`) must pass comprehensive 5-layer quant validation and maintain the exact same option side and strike for **10 continuous minutes (600 seconds)** before becoming actionable.
- Any change in candidate strike/side, validation failure, or gap longer than 60 seconds between refreshes automatically resets the confirmation timer.
- If live data disconnects or backend falls back to cache, signals are immediately reverted to display-only `WAIT` state with zero live broker risk.

### 2. 5-Layer Quant Confluence Engine
- **Layer 1: Trend Alignment** — EMA 8/13/21 stack and Supertrend buy/sell state.
- **Layer 2: Momentum & Volatility** — RSI (14), ATR (14), and Bollinger Band expansion.
- **Layer 3: Smart Money Concepts (SMC)** — Bullish/Bearish Order Blocks (OB), Fair Value Gaps (FVG), Change of Character (CHoCH), and Liquidity Sweeps.
- **Layer 4: Options Open Interest & PCR Flow** — Put-Call Ratio dynamics and institutional strike clustering.
- **Layer 5: Execution Safeguard & Spread Guard** — Bid-Ask spread tolerance and slippage filters.

### 3. Integrated Modules & Tools
- **Live Option Chain & Greeks**: Real-time strike ladder with ATM tagging, CE/PE LTP, OI change, and Max Pain strike.
- **Paper Broker**: Virtual margin account (₹10,00,000) for real-time order simulation and live mark-to-market P&L tracking.
- **AI Market Intelligence**: Conversational market analyst for quick queries, signal review, and order book synthesis.
- **Telemetry & Diagnostics**: Real-time worker cycle tracking, Angel One broker session health, and scoped Android device identification (`X-Device-Id`).

## Development & Build

```bash
# Run local dev server (port 3000)
npm run dev

# Build production bundle
npm run build
```
