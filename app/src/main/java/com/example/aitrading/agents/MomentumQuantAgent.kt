package com.example.aitrading.agents

import com.example.aitrading.data.MarketTick
import kotlin.random.Random

class MomentumQuantAgent {
    fun evaluateMomentum(ticks: List<MarketTick>): Double {
        val bankNifty = ticks.find { it.symbol == "BANKNIFTY" } ?: return 50.0
        return 50.0 + (bankNifty.percentChange * 15.0) + Random.nextDouble(-5.0, 5.0)
    }

    fun getAgentName(): String = "Agent 2: Momentum & Oscillator Quant"
}
