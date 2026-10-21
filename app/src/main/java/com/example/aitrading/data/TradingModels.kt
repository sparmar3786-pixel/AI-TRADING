package com.example.aitrading.data

data class MarketTick(
    val symbol: String,
    val ltp: Double,
    val change: Double,
    val percentChange: Double,
    val high: Double,
    val low: Double,
    val volume: Long,
    val oi: Long,
    val timestamp: Long = System.currentTimeMillis()
)

data class TradingSignal(
    val id: String,
    val symbol: String,
    val type: SignalType, // CALL_BUY, PUT_BUY, FUTURES_LONG, FUTURES_SHORT
    val strategyName: String,
    val entryPrice: Double,
    val target1: Double,
    val target2: Double,
    val target3: Double,
    val stopLoss: Double,
    val strikePrice: String,
    val expiry: String,
    val confidence: Int, // 0 - 100
    val confluenceScore: Double,
    val stabilityMinutes: Int, // 10 min gate requirement
    val isActionable: Boolean,
    val timestamp: Long = System.currentTimeMillis()
)

enum class SignalType {
    CALL_BUY, PUT_BUY, FUTURES_LONG, FUTURES_SHORT, WAIT
}

data class OptionChainRow(
    val strikePrice: Double,
    val callLtp: Double,
    val callChange: Double,
    val callOi: Long,
    val callOiChange: Long,
    val callIv: Double,
    val callDelta: Double,
    val putLtp: Double,
    val putChange: Double,
    val putOi: Long,
    val putOiChange: Long,
    val putIv: Double,
    val putDelta: Double
)

data class PaperOrder(
    val orderId: String,
    val symbol: String,
    val type: String, // BUY / SELL
    val quantity: Int,
    val entryPrice: Double,
    val currentPrice: Double,
    val pnl: Double,
    val status: String // OPEN, CLOSED
)

data class StrategyInfo(
    val id: String,
    val name: String,
    val category: String,
    val description: String,
    val winRate: Double,
    val avgReturn: Double,
    val isEnabled: Boolean
)
