package com.example.aitrading.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.example.aitrading.data.AngelOneApiService
import com.example.aitrading.data.MarketTick
import com.example.aitrading.data.OptionChainRow
import com.example.aitrading.data.PaperOrder
import com.example.aitrading.data.TradingRepository
import com.example.aitrading.data.TradingSignal
import com.example.aitrading.quant.QuantEngine
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

class TradingViewModel(application: Application) : AndroidViewModel(application) {
    private val apiService = AngelOneApiService()
    private val repository = TradingRepository(application)

    private val _isConnected = MutableStateFlow(false)
    val isConnected: StateFlow<Boolean> = _isConnected.asStateFlow()

    private val _ticks = MutableStateFlow<List<MarketTick>>(emptyList())
    val ticks: StateFlow<List<MarketTick>> = _ticks.asStateFlow()

    private val _activeSignals = MutableStateFlow<List<TradingSignal>>(emptyList())
    val activeSignals: StateFlow<List<TradingSignal>> = _activeSignals.asStateFlow()

    private val _selectedTabIndex = MutableStateFlow(0)
    val selectedTabIndex: StateFlow<Int> = _selectedTabIndex.asStateFlow()

    private val _optionChain = MutableStateFlow<List<OptionChainRow>>(emptyList())
    val optionChain: StateFlow<List<OptionChainRow>> = _optionChain.asStateFlow()

    private val _paperOrders = MutableStateFlow<List<PaperOrder>>(emptyList())
    val paperOrders: StateFlow<List<PaperOrder>> = _paperOrders.asStateFlow()

    init {
        startLiveFeeds()
        generateInitialSignals()
    }

    fun selectTab(index: Int) {
        _selectedTabIndex.value = index
    }

    fun loginAngelOne(clientCode: String, pin: String, apiKey: String) {
        viewModelScope.launch {
            val success = apiService.login(clientCode, pin, apiKey)
            _isConnected.value = success
        }
    }

    fun logoutAngelOne() {
        apiService.logout()
        _isConnected.value = false
    }

    private fun startLiveFeeds() {
        viewModelScope.launch {
            apiService.getLiveTicksStream().collect { tickList ->
                _ticks.value = tickList
                // update option chain for nifty
                val niftyTick = tickList.find { it.symbol == "NIFTY" }
                if (niftyTick != null) {
                    _optionChain.value = apiService.getOptionChain("NIFTY")
                }
            }
        }
    }

    private fun generateInitialSignals() {
        val symbols = listOf("NIFTY", "BANKNIFTY", "FINNIFTY", "RELIANCE", "TCS", "INFY", "HDFCBANK")
        val initial = symbols.map { sym ->
            QuantEngine.generateSignal(sym, if (sym == "NIFTY") 22450.0 else 47800.0)
        }
        _activeSignals.value = initial
    }

    fun refreshSignals() {
        generateInitialSignals()
    }

    fun executePaperTrade(signal: TradingSignal) {
        val order = PaperOrder(
            orderId = "ORD-${System.currentTimeMillis()}",
            symbol = signal.symbol,
            type = signal.type.name,
            quantity = 50,
            entryPrice = signal.entryPrice,
            currentPrice = signal.entryPrice,
            pnl = 0.0,
            status = "OPEN"
        )
        _paperOrders.update { listOf(order) + it }
    }
}
