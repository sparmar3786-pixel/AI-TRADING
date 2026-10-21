package com.example.aitrading.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.aitrading.viewmodel.TradingViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainScreenWith25Tabs(viewModel: TradingViewModel) {
    val selectedIndex by viewModel.selectedTabIndex.collectAsState()

    val tabTitles = listOf(
        "1. Live Ticks",
        "2. Angel One",
        "3. Quant Engine",
        "4. Option Chain",
        "5. OI Lab",
        "6. Market Intel",
        "7. Strategies",
        "8. Signals",
        "9. Indicators",
        "10. Backtest",
        "11. Risk Manager",
        "12. Paper Trading",
        "13. Broker Settings",
        "14. Data Health",
        "15. Account",
        "16. Volatility",
        "17. Scalper",
        "18. Calendar",
        "19. FII/DII",
        "20. Sector Heat",
        "21. 5 AI Agents",
        "22. Voice Alerts",
        "23. Cloud Watch",
        "24. P&L Journal",
        "25. App Settings"
    )

    Scaffold(
        topBar = {
            Column {
                TopAppBar(
                    title = { Text("ANGELQUANT LIVE PRO (25 TABS)", fontSize = 16.sp, color = MaterialTheme.colorScheme.primary) },
                    colors = TopAppBarDefaults.topAppBarColors(containerColor = MaterialTheme.colorScheme.surface)
                )
                ScrollableTabRow(
                    selectedTabIndex = selectedIndex,
                    edgePadding = 8.dp,
                    containerColor = MaterialTheme.colorScheme.surface,
                    contentColor = MaterialTheme.colorScheme.primary
                ) {
                    tabTitles.forEachIndexed { index, title ->
                        Tab(
                            selected = selectedIndex == index,
                            onClick = { viewModel.selectTab(index) },
                            text = { Text(title, fontSize = 12.sp) }
                        )
                    }
                }
            }
        }
    ) { paddingVals ->
        Box(modifier = Modifier.fillMaxSize().padding(paddingVals).background(MaterialTheme.colorScheme.background)) {
            when (selectedIndex) {
                0 -> TabLiveDashboard(viewModel)
                1 -> TabAngelOneConnect(viewModel)
                2 -> TabQuantEngine(viewModel)
                3 -> TabOptionChain(viewModel)
                4 -> TabOiLab()
                5 -> TabMarketIntelligence()
                6 -> TabStrategyMatrix()
                7 -> TabQuantEngine(viewModel) // Signals
                8 -> TabGenericPlaceholder("Advanced Technical Indicators (RSI, MACD, ATR, ADX)")
                9 -> TabGenericPlaceholder("Backtesting Simulation Lab & Historical Win-Rate")
                10 -> TabGenericPlaceholder("Risk & Position Sizing Calculator (Kelly Criterion)")
                11 -> TabGenericPlaceholder("Paper Trading & Live Virtual Execution Terminal")
                12 -> TabGenericPlaceholder("Multi-Broker API Settings (Angel One, Zerodha, Upstox)")
                13 -> TabGenericPlaceholder("Data Health & WebSocket Latency Monitor")
                14 -> TabGenericPlaceholder("Broker Account Dashboard & Available Margin")
                15 -> TabGenericPlaceholder("Volatility & IV Skew Percentile Analyzer")
                16 -> TabGenericPlaceholder("Scalper Quick Order Execution Terminal")
                17 -> TabGenericPlaceholder("Earnings, RBI Policy & Economic Calendar")
                18 -> TabGenericPlaceholder("FII / DII Institutional Derivatives Activity Tracker")
                19 -> TabGenericPlaceholder("Sector Performance Heatmap (Bank, IT, Auto, Pharma)")
                20 -> TabAiAgentsTeam(viewModel) // 5 Free Autonomous AI Agents
                21 -> TabGenericPlaceholder("Voice Alerts & Text-to-Speech Market Summaries")
                22 -> TabGenericPlaceholder("Firebase Cloud Synced Watchlists & Custom Alerts")
                23 -> TabGenericPlaceholder("Performance Analytics & P&L Trading Journal")
                24 -> TabGenericPlaceholder("App Settings, Dark/Neon Theme & Risk Warnings")
                else -> TabLiveDashboard(viewModel)
            }
        }
    }
}
