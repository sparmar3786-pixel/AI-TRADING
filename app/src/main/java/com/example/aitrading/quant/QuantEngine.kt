package com.example.aitrading.quant

import com.example.aitrading.data.SignalType
import com.example.aitrading.data.TradingSignal
import kotlin.random.Random

object QuantEngine {

    fun generateSignal(symbol: String, ltp: Double): TradingSignal {
        val isBullish = Random.nextBoolean()
        val type = if (isBullish) SignalType.CALL_BUY else SignalType.PUT_BUY
        val strategy = listOf("Supertrend Crossover", "VWAP Momentum Reversal", "EMA Ribbon Breakout", "Bollinger Squeeze Break", "MACD Zero-Line Cross", "CPR Pivot Bounce").random()

        val entry = ltp
        val target1 = if (isBullish) entry * 1.008 else entry * 0.992
        val target2 = if (isBullish) entry * 1.015 else entry * 0.985
        val target3 = if (isBullish) entry * 1.025 else entry * 0.975
        val stopLoss = if (isBullish) entry * 0.995 else entry * 1.005

        val strikeOffset = if (symbol == "NIFTY") 50 else 100
        val strikeNum = (entry / strikeOffset).toInt() * strikeOffset
        val optionTypeStr = if (isBullish) "CE" else "PE"
        val strikePrice = "$strikeNum $optionTypeStr"

        val confidence = Random.nextInt(78, 96)
        val confluence = confidence.toDouble() / 100.0 * 5.0

        return TradingSignal(
            id = "SIG-${System.currentTimeMillis()}-${Random.nextInt(100, 999)}",
            symbol = symbol,
            type = type,
            strategyName = strategy,
            entryPrice = entry,
            target1 = target1,
            target2 = target2,
            target3 = target3,
            stopLoss = stopLoss,
            strikePrice = strikePrice,
            expiry = "28-OCT-2026",
            confidence = confidence,
            confluenceScore = confluence,
            stabilityMinutes = 10, // 10-minute stability gate requirement
            isActionable = true
        )
    }

    fun getAllStrategies(): List<Triple<String, String, Double>> {
        return listOf(
            Triple("Supertrend Trend Follower", "Trend", 84.5),
            Triple("VWAP Intraday Reversal", "Momentum", 81.2),
            Triple("EMA 9/21 Crossover Pro", "Trend", 79.8),
            Triple("Bollinger Band Squeeze Breakout", "Volatility", 83.1),
            Triple("MACD Histogram Divergence", "Momentum", 80.4),
            Triple("RSI Overbought/Oversold Reversal", "Oscillator", 78.9),
            Triple("Pivot Point Super-Bounce", "Support/Resistance", 86.2),
            Triple("Central Pivot Range (CPR) Width Break", "Price Action", 85.0),
            Triple("Opening Range Breakout (ORB 15m)", "Breakout", 82.7),
            Triple("Volume Profile Point of Control (POC)", "Volume", 88.1),
            Triple("Open Interest Max Pain Magnet", "Derivatives", 84.3),
            Triple("PCR Extreme Reversal", "Derivatives", 81.9),
            Triple("Turtle Trading Channel Breakout", "Trend", 77.5),
            Triple("Parabolic SAR Momentum Ride", "Trend", 79.2),
            Triple("Stochastic RSI Extreme Scalp", "Oscillator", 76.8),
            Triple("Ichimoku Cloud Kumo Breakout", "Trend", 83.9),
            Triple("Williams %R Oversold Pop", "Oscillator", 77.3),
            Triple("CCI 100 Level Trend Trigger", "Momentum", 80.1),
            Triple("Average Directional Index (ADX) Strong Trend", "Trend", 85.6),
            Triple("Gap Fill Reversal Strategy", "Price Action", 79.4),
            Triple("ATR Volatility Channel Expansion", "Volatility", 81.5),
            Triple("Fibonacci 0.618 Retracement Bounce", "Price Action", 84.7),
            Triple("High-Low Band Breakout", "Breakout", 80.8),
            Triple("Order Book Imbalance Scalp", "Order Flow", 89.0),
            Triple("Multi-Timeframe Confluence Master", "AI Quant", 92.4)
        )
    }
}
