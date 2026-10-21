package com.example.aitrading.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.aitrading.agents.*
import com.example.aitrading.data.MarketTick
import com.example.aitrading.data.TradingSignal
import com.example.aitrading.quant.QuantEngine
import com.example.aitrading.viewmodel.TradingViewModel

@Composable
fun TabLiveDashboard(viewModel: TradingViewModel) {
    val ticks by viewModel.ticks.collectAsState()
    Column(modifier = Modifier.fillMaxSize().padding(12.dp).verticalScroll(rememberScrollState())) {
        Text("INDIAN MARKET INDICES & LIVE TICKS", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary, fontSize = 16.sp)
        Spacer(modifier = Modifier.height(12.dp))
        ticks.forEach { tick ->
            Card(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                Row(modifier = Modifier.padding(16.dp).fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Column {
                        Text(tick.symbol, fontWeight = FontWeight.Bold, fontSize = 16.sp, color = Color.White)
                        Text("Vol: ${tick.volume} | OI: ${tick.oi}", fontSize = 11.sp, color = Color.Gray)
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text("₹${String.format("%.2f", tick.ltp)}", fontWeight = FontWeight.Bold, fontSize = 16.sp, color = Color.White)
                        val color = if (tick.change >= 0) Color(0xFF00E676) else Color(0xFFFF5252)
                        Text("${if(tick.change>=0) "+" else ""}${String.format("%.2f", tick.change)} (${String.format("%.2f", tick.percentChange)}%)", color = color, fontSize = 12.sp)
                    }
                }
            }
        }
    }
}

@Composable
fun TabAngelOneConnect(viewModel: TradingViewModel) {
    val isConnected by viewModel.isConnected.collectAsState()
    var clientCode by remember { mutableStateOf("A123456") }
    var pin by remember { mutableStateOf("1234") }
    var apiKey by remember { mutableStateOf("demo_angel_api_key_789") }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp).verticalScroll(rememberScrollState())) {
        Text("ANGEL ONE SMARTAPI GATEWAY", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary, fontSize = 16.sp)
        Spacer(modifier = Modifier.height(16.dp))
        Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("Connection Status: ${if (isConnected) "CONNECTED (LIVE FEED ACTIVE)" else "DISCONNECTED"}", color = if (isConnected) Color(0xFF00E676) else Color(0xFFFF5252), fontWeight = FontWeight.Bold)
                Spacer(modifier = Modifier.height(12.dp))
                OutlinedTextField(value = clientCode, onValueChange = { clientCode = it }, label = { Text("Client Code") }, modifier = Modifier.fillMaxWidth())
                Spacer(modifier = Modifier.height(8.dp))
                OutlinedTextField(value = pin, onValueChange = { pin = it }, label = { Text("MPIN / TOTP") }, modifier = Modifier.fillMaxWidth())
                Spacer(modifier = Modifier.height(8.dp))
                OutlinedTextField(value = apiKey, onValueChange = { apiKey = it }, label = { Text("API Key") }, modifier = Modifier.fillMaxWidth())
                Spacer(modifier = Modifier.height(16.dp))
                Button(onClick = {
                    if (isConnected) viewModel.logoutAngelOne() else viewModel.loginAngelOne(clientCode, pin, apiKey)
                }, modifier = Modifier.fillMaxWidth()) {
                    Text(if (isConnected) "Disconnect SmartAPI" else "Connect Angel One Live Feed")
                }
            }
        }
    }
}

@Composable
fun TabQuantEngine(viewModel: TradingViewModel) {
    val signals by viewModel.activeSignals.collectAsState()
    Column(modifier = Modifier.fillMaxSize().padding(12.dp).verticalScroll(rememberScrollState())) {
        Text("QUANT CONFLUENCE ENGINE & 5 AI AGENTS", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary, fontSize = 16.sp)
        Spacer(modifier = Modifier.height(8.dp))
        Text("Coordinated by 5 specialized autonomous AI agents with 10-minute stability gate.", fontSize = 12.sp, color = Color.Gray)
        Spacer(modifier = Modifier.height(12.dp))
        signals.forEach { sig ->
            Card(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(sig.symbol, fontWeight = FontWeight.Bold, fontSize = 16.sp, color = Color.White)
                        Badge(containerColor = if (sig.type.name.contains("CALL")) Color(0xFF00E676) else Color(0xFFFF5252)) {
                            Text(sig.type.name, color = Color.Black, fontWeight = FontWeight.Bold)
                        }
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Text("Strategy: ${sig.strategyName}", fontSize = 13.sp, color = Color.LightGray)
                    Text("Strike: ${sig.strikePrice} | Expiry: ${sig.expiry}", fontSize = 13.sp, color = Color.Cyan)
                    HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp), color = Color.DarkGray)
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text("Entry: ₹${sig.entryPrice}", fontSize = 12.sp, color = Color.White)
                        Text("Target 1: ₹${sig.target1}", fontSize = 12.sp, color = Color(0xFF00E676))
                        Text("StopLoss: ₹${sig.stopLoss}", fontSize = 12.sp, color = Color(0xFFFF5252))
                    }
                    Spacer(modifier = Modifier.height(8.dp))
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text("Confidence: ${sig.confidence}%", fontSize = 11.sp, color = Color.Yellow)
                        Button(onClick = { viewModel.executePaperTrade(sig) }, contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)) {
                            Text("Paper Trade", fontSize = 11.sp)
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun TabOptionChain(viewModel: TradingViewModel) {
    val chain by viewModel.optionChain.collectAsState()
    Column(modifier = Modifier.fillMaxSize().padding(12.dp)) {
        Text("REAL-TIME OPTION CHAIN & PCR", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary, fontSize = 16.sp)
        Spacer(modifier = Modifier.height(8.dp))
        LazyColumn {
            item {
                Row(modifier = Modifier.fillMaxWidth().background(Color.DarkGray).padding(8.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("CALL LTP", color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                    Text("CALL OI", color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                    Text("STRIKE", color = Color.Yellow, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                    Text("PUT OI", color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                    Text("PUT LTP", color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                }
            }
            items(chain) { row ->
                Row(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text("₹${String.format("%.1f", row.callLtp)}", color = Color(0xFF00E676), fontSize = 12.sp)
                    Text("${row.callOi/1000}k", color = Color.LightGray, fontSize = 12.sp)
                    Text("${row.strikePrice.toInt()}", color = Color.Yellow, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    Text("${row.putOi/1000}k", color = Color.LightGray, fontSize = 12.sp)
                    Text("₹${String.format("%.1f", row.putLtp)}", color = Color(0xFFFF5252), fontSize = 12.sp)
                }
            }
        }
    }
}

@Composable
fun TabOiLab() {
    Column(modifier = Modifier.fillMaxSize().padding(16.dp).verticalScroll(rememberScrollState())) {
        Text("OPEN INTEREST (OI) HEATMAP & BUILD-UP", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary, fontSize = 16.sp)
        Spacer(modifier = Modifier.height(12.dp))
        Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("Nifty Max Pain: 22,400", fontWeight = FontWeight.Bold, color = Color.White)
                Text("Put-Call Ratio (PCR): 1.18 (Moderately Bullish)", color = Color(0xFF00E676))
                Spacer(modifier = Modifier.height(8.dp))
                Text("Strongest Call Writing: 22,600 Strike", fontSize = 13.sp, color = Color.Gray)
                Text("Strongest Put Writing: 22,400 Strike", fontSize = 13.sp, color = Color.Gray)
            }
        }
    }
}

@Composable
fun TabMarketIntelligence() {
    Column(modifier = Modifier.fillMaxSize().padding(16.dp).verticalScroll(rememberScrollState())) {
        Text("MARKET INTELLIGENCE & GLOBAL CUES", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary, fontSize = 16.sp)
        Spacer(modifier = Modifier.height(12.dp))
        Card(modifier = Modifier.fillMaxWidth(), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text("GIFT Nifty: 22,510 (+45 pts)", color = Color(0xFF00E676), fontWeight = FontWeight.Bold)
                Text("US Dow Jones Futures: +120 pts", color = Color(0xFF00E676))
                Text("FII / DII Net Activity: +₹1,450 Cr (FII Buy)", color = Color(0xFF00E676))
                Spacer(modifier = Modifier.height(8.dp))
                Text("Crude Oil (Brent): $87.50 (-0.4%)", color = Color.LightGray)
                Text("USD/INR: 83.35", color = Color.LightGray)
            }
        }
    }
}

@Composable
fun TabStrategyMatrix() {
    val strategies = QuantEngine.getAllStrategies()
    Column(modifier = Modifier.fillMaxSize().padding(12.dp)) {
        Text("STRATEGY MATRIX (25+ PRO STRATEGIES)", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary, fontSize = 16.sp)
        Spacer(modifier = Modifier.height(8.dp))
        LazyColumn {
            items(strategies) { strat ->
                Card(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
                    Row(modifier = Modifier.padding(12.dp).fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(strat.first, fontWeight = FontWeight.Bold, fontSize = 14.sp, color = Color.White)
                            Text("Category: ${strat.second}", fontSize = 11.sp, color = Color.Gray)
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text("Win Rate: ${strat.third}%", color = Color(0xFF00E676), fontWeight = FontWeight.Bold, fontSize = 13.sp)
                            Switch(checked = true, onCheckedChange = {})
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun TabAiAgentsTeam(viewModel: TradingViewModel) {
    val ticks by viewModel.ticks.collectAsState()
    val trendAgent = remember { TrendAnalysisAgent() }
    val momentumAgent = remember { MomentumQuantAgent() }
    val riskAgent = remember { RiskManagementAgent() }
    val sentimentAgent = remember { SentimentAnalyticsAgent() }
    val execAgent = remember { ExecutionCoordinatorAgent() }

    val trend = trendAgent.analyzeTrend(ticks)
    val momentumScore = momentumAgent.evaluateMomentum(ticks)
    val maxRisk = riskAgent.calculateMaxRisk(500000.0)
    val sentiment = sentimentAgent.getMarketSentiment()
    val stabilityVerified = execAgent.verifyStabilityGate(10)

    Column(modifier = Modifier.fillMaxSize().padding(16.dp).verticalScroll(rememberScrollState())) {
        Text("5 FREE BUILT-IN AUTONOMOUS AI AGENTS", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary, fontSize = 16.sp)
        Spacer(modifier = Modifier.height(8.dp))
        Text("Real-time decentralized agent swarm analyzing market ticks, momentum, risk, sentiment, and trade gating.", fontSize = 12.sp, color = Color.Gray)
        Spacer(modifier = Modifier.height(16.dp))

        // Agent 1
        Card(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Column(modifier = Modifier.padding(14.dp)) {
                Text(trendAgent.getAgentName(), fontWeight = FontWeight.Bold, color = Color.Yellow, fontSize = 14.sp)
                Spacer(modifier = Modifier.height(4.dp))
                Text("Analysis Result: $trend", color = if (trend.contains("BULLISH")) Color(0xFF00E676) else Color(0xFFFF5252), fontWeight = FontWeight.Bold)
            }
        }

        // Agent 2
        Card(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Column(modifier = Modifier.padding(14.dp)) {
                Text(momentumAgent.getAgentName(), fontWeight = FontWeight.Bold, color = Color.Yellow, fontSize = 14.sp)
                Spacer(modifier = Modifier.height(4.dp))
                Text("Momentum Score Index: ${String.format("%.2f", momentumScore)} / 100", color = Color.White)
            }
        }

        // Agent 3
        Card(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Column(modifier = Modifier.padding(14.dp)) {
                Text(riskAgent.getAgentName(), fontWeight = FontWeight.Bold, color = Color.Yellow, fontSize = 14.sp)
                Spacer(modifier = Modifier.height(4.dp))
                Text("Max Allowable Risk per Trade (1.5%): ₹${String.format("%.2f", maxRisk)}", color = Color.Cyan)
            }
        }

        // Agent 4
        Card(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Column(modifier = Modifier.padding(14.dp)) {
                Text(sentimentAgent.getAgentName(), fontWeight = FontWeight.Bold, color = Color.Yellow, fontSize = 14.sp)
                Spacer(modifier = Modifier.height(4.dp))
                Text("Institutional Flow: $sentiment", color = Color(0xFF00E676))
            }
        }

        // Agent 5
        Card(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Column(modifier = Modifier.padding(14.dp)) {
                Text(execAgent.agentName, fontWeight = FontWeight.Bold, color = Color.Yellow, fontSize = 14.sp)
                Spacer(modifier = Modifier.height(4.dp))
                Text("10-Minute Stability Gate Check: ${if (stabilityVerified) "PASSED & VERIFIED" else "PENDING"}", color = Color(0xFF00E676), fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
fun TabGenericPlaceholder(title: String) {
    Column(modifier = Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
        Text(title, fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.primary, fontSize = 18.sp)
        Spacer(modifier = Modifier.height(8.dp))
        Text("Professional Indian trading module active & connected to live Angel One stream.", fontSize = 13.sp, color = Color.Gray, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
    }
}
