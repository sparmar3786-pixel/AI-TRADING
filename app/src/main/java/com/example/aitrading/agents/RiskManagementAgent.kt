package com.example.aitrading.agents

class RiskManagementAgent {
    fun calculateMaxRisk(capital: Double): Double {
        // Enforce strict 1.5% max risk per trade rule
        return capital * 0.015
    }

    fun validateStopLoss(entry: Double, stopLoss: Double, isBuy: Boolean): Boolean {
        return if (isBuy) stopLoss < entry else stopLoss > entry
    }

    fun getAgentName(): String = "Agent 3: Risk Management & Capital Guardian"
}
