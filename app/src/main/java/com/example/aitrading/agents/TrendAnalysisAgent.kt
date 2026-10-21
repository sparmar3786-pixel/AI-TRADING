package com.example.aitrading.agents

import com.example.aitrading.data.MarketTick

class TrendAnalysisAgent {
    fun analyzeTrend(ticks: List<MarketTick>): String {
        val nifty = ticks.find { it.symbol == "NIFTY" } ?: return "NEUTRAL"
        return if (nifty.change >= 0.0) "BULLISH_TREND" else "BEARISH_TREND"
    }

    fun getAgentName(): String = "Agent 1: Trend & Price Action Specialist"
}
