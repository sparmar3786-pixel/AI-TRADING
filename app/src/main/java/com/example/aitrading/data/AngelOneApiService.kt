package com.example.aitrading.data

import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlin.math.abs
import kotlin.random.Random

class AngelOneApiService {
    var isConnected: Boolean = false
    var clientCode: String = ""
    var apiKey: String = ""

    suspend fun login(client: String, pin: String, key: String): Boolean {
        delay(1000)
        clientCode = client
        apiKey = key
        isConnected = true
        return true
    }

    fun logout() {
        isConnected = false
        clientCode = ""
        apiKey = ""
    }

    fun getLiveTicksStream(): Flow<List<MarketTick>> = flow {
        val symbols = listOf("NIFTY", "BANKNIFTY", "FINNIFTY", "SENSEX", "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK")
        val basePrices = mutableMapOf(
            "NIFTY" to 22450.0,
            "BANKNIFTY" to 47800.0,
            "FINNIFTY" to 21100.0,
            "SENSEX" to 73800.0,
            "RELIANCE" to 2950.0,
            "TCS" to 4100.0,
            "INFY" to 1550.0,
            "HDFCBANK" to 1480.0,
            "ICICIBANK" to 1080.0
        )

        while (true) {
            val ticks = symbols.map { sym ->
                val current = basePrices[sym] ?: 1000.0
                val delta = (Random.nextDouble() - 0.49) * (current * 0.001)
                val newPrice = current + delta
                basePrices[sym] = newPrice
                val change = newPrice - (current - delta)
                val pct = (change / current) * 100
                MarketTick(
                    symbol = sym,
                    ltp = newPrice,
                    change = change,
                    percentChange = pct,
                    high = newPrice * 1.005,
                    low = newPrice * 0.995,
                    volume = Random.nextLong(100000, 5000000),
                    oi = Random.nextLong(500000, 20000000)
                )
            }
            emit(ticks)
            delay(2000)
        }
    }

    fun getOptionChain(indexSymbol: String): List<OptionChainRow> {
        val spot = if (indexSymbol == "NIFTY") 22450.0 else 47800.0
        val strikeStep = if (indexSymbol == "NIFTY") 50.0 else 100.0
        val baseStrike = (spot / strikeStep).toInt() * strikeStep

        val rows = mutableListOf<OptionChainRow>()
        for (i in -10..10) {
            val strike = baseStrike + (i * strikeStep)
            val dist = abs(strike - spot)
            val callLtp = kotlin.math.max(5.0, (spot - strike) + (200.0 - dist * 0.1))
            val putLtp = kotlin.math.max(5.0, (strike - spot) + (200.0 - dist * 0.1))
            rows.add(
                OptionChainRow(
                    strikePrice = strike,
                    callLtp = callLtp,
                    callChange = callLtp * 0.05 * (if (i % 2 == 0) 1 else -1),
                    callOi = 1500000L + (abs(i) * 100000L),
                    callOiChange = 50000L * (if (i > 0) 1 else -1),
                    callIv = 14.5 + abs(i) * 0.2,
                    callDelta = 0.5 - (i * 0.04),
                    putLtp = putLtp,
                    putChange = putLtp * 0.05 * (if (i % 2 == 0) -1 else 1),
                    putOi = 1800000L + (abs(i) * 90000L),
                    putOiChange = 40000L * (if (i < 0) 1 else -1),
                    putIv = 15.0 + abs(i) * 0.2,
                    putDelta = -0.5 - (i * 0.04)
                )
            )
        }
        return rows
    }
}
