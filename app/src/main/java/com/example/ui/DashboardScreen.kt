package com.example.ui

import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.model.GoldCandle
import com.example.data.Trade
import com.example.ui.components.GoldChartCanvas
import com.example.ui.theme.BullishTeal
import com.example.ui.theme.BearishCrimson
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun DashboardScreen(
    viewModel: AureusViewModel,
    modifier: Modifier = Modifier
) {
    val currentScreen by viewModel.currentScreen.collectAsState()
    val timeframe by viewModel.timeframe.collectAsState()
    val candles by viewModel.candles.collectAsState()
    val selectedCandle by viewModel.selectedCandle.collectAsState()
    
    val allTrades by viewModel.allTrades.collectAsState(initial = emptyList())
    val isAnalyzing by viewModel.isAnalyzing.collectAsState()
    val aiAnalysisText by viewModel.aiAnalysisText.collectAsState()
    
    val chatMessages by viewModel.chatMessages.collectAsState()
    val isChatWaiting by viewModel.isChatWaiting.collectAsState()

    Scaffold(
        modifier = modifier.fillMaxSize(),
        bottomBar = {
            AureusBottomNavigation(
                currentScreen = currentScreen,
                onNavigate = { viewModel.navigateTo(it) }
            )
        },
        contentWindowInsets = WindowInsets.safeDrawing
    ) { innerPadding ->
        Box(
            modifier = Modifier
                .padding(innerPadding)
                .fillMaxSize()
                .background(MaterialTheme.colorScheme.background)
        ) {
            AnimatedContent(
                targetState = currentScreen,
                transitionSpec = {
                    fadeIn(animationSpec = tween(220)) togetherWith fadeOut(animationSpec = tween(220))
                },
                label = "ScreenTransition"
            ) { screen ->
                when (screen) {
                    AureusScreen.MARKET -> {
                        MarketScreenBody(
                            timeframe = timeframe,
                            candles = candles,
                            selectedCandle = selectedCandle,
                            onTimeframeSelected = { viewModel.loadMarketData(it) },
                            onCandleSelected = { viewModel.selectCandle(it) }
                        )
                    }
                    AureusScreen.AI_SIGNALS -> {
                        SignalsScreenBody(
                            isAnalyzing = isAnalyzing,
                            aiAnalysisText = aiAnalysisText,
                            onTriggerAnalysis = { viewModel.queryAiSignal() }
                        )
                    }
                    AureusScreen.JOURNAL -> {
                        JournalScreenBody(
                            trades = allTrades,
                            onAddTrade = { type, entry, exit, lot, note ->
                                viewModel.addTrade(type, entry, exit, lot, note)
                            },
                            onDeleteTrade = { viewModel.deleteTrade(it) }
                        )
                    }
                    AureusScreen.ASSISTANT -> {
                        AssistantScreenBody(
                            chatMessages = chatMessages,
                            isWaiting = isChatWaiting,
                            onSendMessage = { viewModel.sendChatMessage(it) }
                        )
                    }
                }
            }
        }
    }
}

// --- Dynamic Navigation Bar ---
@Composable
fun AureusBottomNavigation(
    currentScreen: AureusScreen,
    onNavigate: (AureusScreen) -> Unit
) {
    // Custom Gold gradient highlights to represent top luxury trading experience
    NavigationBar(
        containerColor = MaterialTheme.colorScheme.surface,
        tonalElevation = 8.dp,
        modifier = Modifier.windowInsetsPadding(WindowInsets.navigationBars)
    ) {
        NavigationBarItem(
            selected = currentScreen == AureusScreen.MARKET,
            onClick = { onNavigate(AureusScreen.MARKET) },
            icon = { Icon(Icons.Filled.ShowChart, contentDescription = "Bozor") },
            label = { Text("Bozor", fontSize = 11.sp, fontWeight = FontWeight.SemiBold) },
            colors = NavigationBarItemDefaults.colors(
                selectedIconColor = MaterialTheme.colorScheme.primary,
                selectedTextColor = MaterialTheme.colorScheme.primary,
                indicatorColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.12f),
                unselectedIconColor = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.6f),
                unselectedTextColor = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.6f)
            ),
            modifier = Modifier.testTag("nav_market")
        )
        NavigationBarItem(
            selected = currentScreen == AureusScreen.AI_SIGNALS,
            onClick = { onNavigate(AureusScreen.AI_SIGNALS) },
            icon = { Icon(Icons.Filled.AutoAwesome, contentDescription = "AI Signallar") },
            label = { Text("AI Signal", fontSize = 11.sp, fontWeight = FontWeight.SemiBold) },
            colors = NavigationBarItemDefaults.colors(
                selectedIconColor = MaterialTheme.colorScheme.primary,
                selectedTextColor = MaterialTheme.colorScheme.primary,
                indicatorColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.12f),
                unselectedIconColor = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.6f),
                unselectedTextColor = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.6f)
            ),
            modifier = Modifier.testTag("nav_signals")
        )
        NavigationBarItem(
            selected = currentScreen == AureusScreen.JOURNAL,
            onClick = { onNavigate(AureusScreen.JOURNAL) },
            icon = { Icon(Icons.Filled.Book, contentDescription = "Savdo Jurnali") },
            label = { Text("Jurnal", fontSize = 11.sp, fontWeight = FontWeight.SemiBold) },
            colors = NavigationBarItemDefaults.colors(
                selectedIconColor = MaterialTheme.colorScheme.primary,
                selectedTextColor = MaterialTheme.colorScheme.primary,
                indicatorColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.12f),
                unselectedIconColor = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.6f),
                unselectedTextColor = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.6f)
            ),
            modifier = Modifier.testTag("nav_journal")
        )
        NavigationBarItem(
            selected = currentScreen == AureusScreen.ASSISTANT,
            onClick = { onNavigate(AureusScreen.ASSISTANT) },
            icon = { Icon(Icons.Filled.Forum, contentDescription = "Chat Assistant") },
            label = { Text("AI Chat", fontSize = 11.sp, fontWeight = FontWeight.SemiBold) },
            colors = NavigationBarItemDefaults.colors(
                selectedIconColor = MaterialTheme.colorScheme.primary,
                selectedTextColor = MaterialTheme.colorScheme.primary,
                indicatorColor = MaterialTheme.colorScheme.primary.copy(alpha = 0.12f),
                unselectedIconColor = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.6f),
                unselectedTextColor = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.6f)
            ),
            modifier = Modifier.testTag("nav_assistant")
        )
    }
}

// --- 1. MARKET SCREEN ---
@Composable
fun MarketScreenBody(
    timeframe: String,
    candles: List<GoldCandle>,
    selectedCandle: GoldCandle?,
    onTimeframeSelected: (String) -> Unit,
    onCandleSelected: (GoldCandle) -> Unit
) {
    val formatter = remember { SimpleDateFormat("yyyy/MM/dd HH:mm", Locale.US) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 12.dp, vertical = 8.dp)
    ) {
        // App Header and Brand
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 10.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text(
                    text = "AUREUS PROTOCOL",
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary.copy(alpha = 0.8f),
                    letterSpacing = 1.8.sp
                )
                Text(
                    text = "XAUUSD Analyzer",
                    fontSize = 20.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = Color.White,
                    letterSpacing = 0.5.sp
                )
            }
            Spacer(modifier = Modifier.weight(1f))
            
            // Timeframe Selector Buttons matching Sophisticated Dark capsule UI
            Row(
                modifier = Modifier
                    .clip(RoundedCornerShape(20.dp))
                    .background(MaterialTheme.colorScheme.surface)
                    .border(1.dp, Color.White.copy(alpha = 0.05f), RoundedCornerShape(20.dp))
                    .padding(2.dp)
            ) {
                listOf("1H", "4H", "1D").forEach { tf ->
                    val isActive = timeframe == tf
                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(18.dp))
                            .background(if (isActive) MaterialTheme.colorScheme.primary else Color.Transparent)
                            .clickable { onTimeframeSelected(tf) }
                            .padding(horizontal = 14.dp, vertical = 6.dp)
                    ) {
                        Text(
                            text = tf,
                            color = if (isActive) Color.Black else MaterialTheme.colorScheme.onBackground,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.ExtraBold
                        )
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(10.dp))

        // Main Financial Candlestick Canvas Chart Component with Sophisticated rounding and border
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
                .clip(RoundedCornerShape(24.dp))
                .border(1.dp, Color.White.copy(alpha = 0.05f), RoundedCornerShape(24.dp))
        ) {
            GoldChartCanvas(
                candles = candles,
                selectedCandle = selectedCandle,
                onCandleSelected = onCandleSelected,
                modifier = Modifier.fillMaxSize()
            )
        }

        Spacer(modifier = Modifier.height(10.dp))

        // Legend details row
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 4.dp, vertical = 2.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(modifier = Modifier.size(8.dp).clip(CircleShape).background(Color(0xFFF39C12)))
                Spacer(modifier = Modifier.width(4.dp))
                Text("SMA 20", fontSize = 10.sp, color = MaterialTheme.colorScheme.onBackground)
                
                Spacer(modifier = Modifier.width(12.dp))
                Box(modifier = Modifier.size(8.dp).clip(CircleShape).background(Color(0xFF29B6F6)))
                Spacer(modifier = Modifier.width(4.dp))
                Text("SMA 50", fontSize = 10.sp, color = MaterialTheme.colorScheme.onBackground)

                Spacer(modifier = Modifier.width(12.dp))
                Box(modifier = Modifier.size(8.dp).clip(CircleShape).background(Color(0xFF9C27B0)))
                Spacer(modifier = Modifier.width(4.dp))
                Text("RSI (14)", fontSize = 10.sp, color = MaterialTheme.colorScheme.onBackground)
            }
            Text(
                "Tahlil qilish uchun grafikni bosing",
                fontSize = 10.sp,
                color = MaterialTheme.colorScheme.primary.copy(alpha = 0.6f),
                fontWeight = FontWeight.Medium
            )
        }

        Spacer(modifier = Modifier.height(8.dp))

        // Selected Candlestick Metrics Display Card
        selectedCandle?.let { c ->
            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                shape = RoundedCornerShape(24.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, Color.White.copy(alpha = 0.05f), RoundedCornerShape(24.dp))
            ) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Text(
                            text = formatter.format(Date(c.timestamp)),
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.primary
                        )
                        Text(
                            text = "Hajm: ${String.format("%.0f", c.volume)}",
                            fontSize = 11.sp,
                            color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.7f)
                        )
                    }
                    HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp), color = Color(0xFF1F2A3F))
                    
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Column {
                            MetricTextItem(label = "Ochilish", value = "$${String.format("%.2f", c.open)}")
                            MetricTextItem(label = "Yopilish", value = "$${String.format("%.2f", c.close)}")
                        }
                        Column {
                            MetricTextItem(label = "Eng yuqori", value = "$${String.format("%.2f", c.high)}", color = BullishTeal)
                            MetricTextItem(label = "Eng past", value = "$${String.format("%.2f", c.low)}", color = BearishCrimson)
                        }
                        Column {
                            val rsiVal = c.rsi ?: 50.0
                            val rsiColor = if (rsiVal > 70.0) BearishCrimson else if (rsiVal < 30.0) BullishTeal else MaterialTheme.colorScheme.onSurface
                            MetricTextItem(label = "RSI (14)", value = String.format("%.2f", rsiVal), color = rsiColor)
                            
                            val sma20Val = c.sma20 ?: c.close
                            MetricTextItem(label = "SMA 20", value = "$${String.format("%.1f", sma20Val)}")
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun MetricTextItem(label: String, value: String, color: Color = MaterialTheme.colorScheme.onSurface) {
    Row {
        Text(text = "$label: ", fontSize = 11.sp, color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.7f))
        Text(text = value, fontSize = 11.sp, fontWeight = FontWeight.Bold, color = color)
    }
}


// --- 2. AI SIGNALS SCREEN ---
@Composable
fun SignalsScreenBody(
    isAnalyzing: Boolean,
    aiAnalysisText: String?,
    onTriggerAnalysis: () -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(14.dp)
    ) {
        // App Header and Brand
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 10.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text(
                    text = "AUREUS PROTOCOL",
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary.copy(alpha = 0.8f),
                    letterSpacing = 1.8.sp
                )
                Text(
                    text = "AI Core Signals",
                    fontSize = 20.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = Color.White,
                    letterSpacing = 0.5.sp
                )
            }
        }

        Spacer(modifier = Modifier.height(10.dp))

        // Premium AI Core Engine Highlight Banner matching Sophisticated Dark CSS
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .clip(RoundedCornerShape(24.dp))
                .background(
                    Brush.linearGradient(
                        colors = listOf(
                            Color(0x2A9A3412), // Rich amber brown transparent tone
                            Color(0x4DCA8A04)  // Golden amber transparent tone
                        )
                    )
                )
                .border(1.dp, Color(0x66FFD700), RoundedCornerShape(24.dp))
                .padding(16.dp)
        ) {
            Column {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                ) {
                    Box(
                        modifier = Modifier
                            .size(6.dp)
                            .clip(CircleShape)
                            .background(Color(0xFFFFD700))
                    )
                    Text(
                        text = "AI CORE ENGINE",
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Black,
                        color = Color(0xFFFFD700),
                        letterSpacing = 2.sp
                    )
                }
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "STRONG BUY",
                    fontSize = 22.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color.White
                )
                Spacer(modifier = Modifier.height(2.dp))
                Text(
                    text = "Ehtimollik: 89.4% • Targets: $2,352.00 / $2,365.50",
                    fontSize = 11.sp,
                    color = Color(0xFFE2E8F0).copy(alpha = 0.8f),
                    fontWeight = FontWeight.Medium
                )
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        // Large Premium Dashboard Query Button
        Button(
            onClick = onTriggerAnalysis,
            enabled = !isAnalyzing,
            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary),
            shape = RoundedCornerShape(20.dp),
            modifier = Modifier
                .fillMaxWidth()
                .height(50.dp)
                .testTag("analyze_market_button")
        ) {
            Icon(
                Icons.Filled.AutoAwesome,
                contentDescription = null,
                tint = Color.Black,
                modifier = Modifier.size(16.dp)
            )
            Spacer(modifier = Modifier.width(8.dp))
            Text(
                "XAUUSD TAHLILINI YANGILASH",
                color = Color.Black,
                fontWeight = FontWeight.Bold,
                fontSize = 11.sp,
                letterSpacing = 0.5.sp
            )
        }

        Spacer(modifier = Modifier.height(12.dp))

        // Main Signal Report display body with Sophisticated 24.dp rounded corners + 5% white border
        Card(
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            shape = RoundedCornerShape(24.dp),
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
                .border(1.dp, Color.White.copy(alpha = 0.05f), RoundedCornerShape(24.dp))
        ) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(12.dp)
            ) {
                if (isAnalyzing) {
                    Column(
                        modifier = Modifier.fillMaxSize(),
                        verticalArrangement = Arrangement.Center,
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
                        Spacer(modifier = Modifier.height(16.dp))
                        Text(
                            text = "Aureus AI serverlari bozor krossoverlarini, RSI ko'rsatkichini va so'nggi bugungi oltin munosabatlarini baholamoqda...",
                            color = MaterialTheme.colorScheme.primary,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Medium,
                            textAlign = TextAlign.Center,
                            modifier = Modifier.padding(horizontal = 24.dp)
                        )
                    }
                } else if (!aiAnalysisText.isNullOrBlank()) {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        item {
                            MarkdownText(text = aiAnalysisText)
                        }
                    }
                } else {
                    // Empty state instruction manual
                    Column(
                        modifier = Modifier.fillMaxSize(),
                        verticalArrangement = Arrangement.Center,
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Icon(
                            Icons.Outlined.AutoAwesome,
                            contentDescription = null,
                            tint = MaterialTheme.colorScheme.primary.copy(alpha = 0.2f),
                            modifier = Modifier.size(80.dp)
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        Text(
                            text = "Hozircha tahlil yo'q",
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onSurface
                        )
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "Yuqoridagi buyruq orqali Oltin tahlilini yuklang. Gemini modeli trend quvvatini avtomatik ravishda baholaydi.",
                            fontSize = 12.sp,
                            color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.6f),
                            textAlign = TextAlign.Center,
                            modifier = Modifier.padding(horizontal = 32.dp)
                        )
                    }
                }
            }
        }
    }
}

// Render formatted text supporting bold headings cleanly
@Composable
fun MarkdownText(text: String, modifier: Modifier = Modifier) {
    val parts = text.split("**")
    Text(
        text = buildAnnotatedString {
            parts.forEachIndexed { index, part ->
                if (index % 2 == 1) {
                    pushStyle(SpanStyle(fontWeight = FontWeight.ExtraBold, color = MaterialTheme.colorScheme.primary))
                    append(part)
                    pop()
                } else {
                    append(part)
                }
            }
        },
        color = MaterialTheme.colorScheme.onSurface,
        fontSize = 13.sp,
        lineHeight = 22.sp,
        fontFamily = FontFamily.SansSerif,
        modifier = modifier
    )
}


// --- 3. JOURNAL SCREEN ---
@Composable
fun JournalScreenBody(
    trades: List<Trade>,
    onAddTrade: (String, Double, Double, Double, String) -> Unit,
    onDeleteTrade: (Trade) -> Unit
) {
    var showAddForm by remember { mutableStateOf(false) }
    
    // Form fields
    var tradeType by remember { mutableStateOf("BUY") }
    var entryPriceText by remember { mutableStateOf("") }
    var exitPriceText by remember { mutableStateOf("") }
    var lotSizeText by remember { mutableStateOf("") }
    var noteText by remember { mutableStateOf("") }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    val focusManager = LocalFocusManager.current

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(14.dp)
    ) {
        // App Header and Brand
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 10.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text(
                    text = "AUREUS PROTOCOL",
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary.copy(alpha = 0.8f),
                    letterSpacing = 1.8.sp
                )
                Text(
                    text = "Trading Journal",
                    fontSize = 20.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = Color.White,
                    letterSpacing = 0.5.sp
                )
            }
        }

        Spacer(modifier = Modifier.height(10.dp))

        // Stats Header Card Row
        val totalProfit = trades.sumOf { it.profit }
        val wins = trades.count { it.profit > 0 }
        val winRate = if (trades.isNotEmpty()) (wins.toFloat() / trades.size * 100).toInt() else 100

        Card(
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            shape = RoundedCornerShape(24.dp),
            modifier = Modifier
                .fillMaxWidth()
                .border(1.dp, Color.White.copy(alpha = 0.05f), RoundedCornerShape(24.dp))
                .padding(bottom = 12.dp)
        ) {
            Column(modifier = Modifier.padding(14.dp)) {
                Text(
                    text = "📊 PREMIUM HAMYON & STATISTIKA",
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary,
                    letterSpacing = 1.1.sp
                )
                Spacer(modifier = Modifier.height(10.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column {
                        Text("Umumiy Foyda/Zarar", fontSize = 11.sp, color = MaterialTheme.colorScheme.onBackground)
                        Text(
                            text = if (totalProfit >= 0) "+$${String.format("%.2f", totalProfit)}" else "-$${String.format("%.2f", kotlin.math.abs(totalProfit))}",
                            fontSize = 22.sp,
                            fontWeight = FontWeight.ExtraBold,
                            color = if (totalProfit >= 0) BullishTeal else BearishCrimson
                        )
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text("Win Rate %", fontSize = 11.sp, color = MaterialTheme.colorScheme.onBackground)
                        Text(
                            text = "$winRate%",
                            fontSize = 22.sp,
                            fontWeight = FontWeight.ExtraBold,
                            color = if (winRate >= 60) BullishTeal else MaterialTheme.colorScheme.onSurface
                        )
                    }
                    Column(horizontalAlignment = Alignment.End) {
                        Text("Savdolar soni", fontSize = 11.sp, color = MaterialTheme.colorScheme.onBackground)
                        Text(
                            text = "${trades.size}",
                            fontSize = 22.sp,
                            fontWeight = FontWeight.ExtraBold,
                            color = MaterialTheme.colorScheme.primary
                        )
                    }
                }
            }
        }

        // Toggle New Trade Form Button
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(
                "Yozilgan savdolar ro'yxati",
                fontWeight = FontWeight.Bold,
                fontSize = 15.sp,
                color = MaterialTheme.colorScheme.onSurface
            )
            Button(
                onClick = {
                    showAddForm = !showAddForm
                    errorMessage = null
                },
                shape = RoundedCornerShape(8.dp),
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (showAddForm) Color.Gray else MaterialTheme.colorScheme.primary
                ),
                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp),
                modifier = Modifier.testTag("toggle_add_trade_form")
            ) {
                Icon(
                    imageVector = if (showAddForm) Icons.Filled.Close else Icons.Filled.Add,
                    contentDescription = null,
                    tint = Color.Black,
                    modifier = Modifier.size(16.dp)
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text(
                    if (showAddForm) "Yopish" else "+ Savdo",
                    color = Color.Black,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold
                )
            }
        }

        // Expandable Add Form
        AnimatedVisibility(
            visible = showAddForm,
            enter = expandVertically() + fadeIn(),
            exit = shrinkVertically() + fadeOut()
        ) {
            Card(
                colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                shape = RoundedCornerShape(24.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 12.dp)
                    .border(1.dp, Color.White.copy(alpha = 0.05f), RoundedCornerShape(24.dp))
            ) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Text(
                        "Yangi savdo logini kiritish",
                        fontSize = 13.sp,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    // Direction Selector Tab
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(8.dp))
                            .background(Color(0xFF0F1424))
                            .padding(2.dp)
                    ) {
                        listOf("BUY", "SELL").forEach { type ->
                            val active = tradeType == type
                            val activeBg = if (type == "BUY") BullishTeal else BearishCrimson
                            Box(
                                modifier = Modifier
                                    .weight(1f)
                                    .clip(RoundedCornerShape(6.dp))
                                    .background(if (active) activeBg else Color.Transparent)
                                    .clickable { tradeType = type }
                                    .padding(vertical = 8.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(
                                    type,
                                    fontSize = 12.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = if (active) Color.White else MaterialTheme.colorScheme.onBackground
                                )
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    // Input Fields Row
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        OutlinedTextField(
                            value = entryPriceText,
                            onValueChange = { entryPriceText = it },
                            label = { Text("Kirish narxi", fontSize = 11.sp) },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedBorderColor = MaterialTheme.colorScheme.primary,
                                unfocusedBorderColor = Color(0xFF1F2A3F)
                            ),
                            singleLine = true,
                            modifier = Modifier
                                .weight(1f)
                                .testTag("input_entry")
                        )
                        OutlinedTextField(
                            value = exitPriceText,
                            onValueChange = { exitPriceText = it },
                            label = { Text("Chiqish narxi", fontSize = 11.sp) },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedBorderColor = MaterialTheme.colorScheme.primary,
                                unfocusedBorderColor = Color(0xFF1F2A3F)
                            ),
                            singleLine = true,
                            modifier = Modifier
                                .weight(1f)
                                .testTag("input_exit")
                        )
                        OutlinedTextField(
                            value = lotSizeText,
                            onValueChange = { lotSizeText = it },
                            label = { Text("Lot (Hajmi)", fontSize = 11.sp) },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedBorderColor = MaterialTheme.colorScheme.primary,
                                unfocusedBorderColor = Color(0xFF1F2A3F)
                            ),
                            singleLine = true,
                            modifier = Modifier
                                .weight(1f)
                                .testTag("input_lot")
                        )
                    }

                    Spacer(modifier = Modifier.height(6.dp))

                    OutlinedTextField(
                        value = noteText,
                        onValueChange = { noteText = it },
                        label = { Text("Tavsif (izoh)", fontSize = 11.sp) },
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = MaterialTheme.colorScheme.primary,
                            unfocusedBorderColor = Color(0xFF1F2A3F)
                        ),
                        singleLine = true,
                        modifier = Modifier
                            .fillMaxWidth()
                            .testTag("input_note")
                    )

                    errorMessage?.let { err ->
                        Spacer(modifier = Modifier.height(6.dp))
                        Text(err, color = BearishCrimson, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                    }

                    Spacer(modifier = Modifier.height(8.dp))

                    Button(
                        onClick = {
                            val entry = entryPriceText.toDoubleOrNull()
                            val exit = exitPriceText.toDoubleOrNull()
                            val lot = lotSizeText.toDoubleOrNull()
                            
                            if (entry == null || entry <= 0 || exit == null || exit <= 0 || lot == null || lot <= 0) {
                                errorMessage = "Iltimos hamma narx va lot raqamlarini to'g'ri kiriting!"
                            } else {
                                onAddTrade(tradeType, entry, exit, lot, noteText)
                                // Reset
                                entryPriceText = ""
                                exitPriceText = ""
                                lotSizeText = ""
                                noteText = ""
                                errorMessage = null
                                showAddForm = false
                                focusManager.clearFocus()
                            }
                        },
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.primary),
                        shape = RoundedCornerShape(8.dp),
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(44.dp)
                            .testTag("add_trade_confirm_button")
                    ) {
                        Text("SAVDOni MUVAFFAQIYATLI SAQLASH", color = Color.Black, fontWeight = FontWeight.ExtraBold, fontSize = 11.sp)
                    }
                }
            }
        }

        // Lazy lists of trades journals
        if (trades.isEmpty()) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f),
                contentAlignment = Alignment.Center
            ) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(
                        Icons.Outlined.Book,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary.copy(alpha = 0.2f),
                        modifier = Modifier.size(60.dp)
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text("Savdo jurnali bo'sh", color = MaterialTheme.colorScheme.onBackground, fontSize = 13.sp)
                    Text("Log kiritish uchun '+ Savdo' tugmasini bosing", color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.6f), fontSize = 11.sp)
                }
            }
        } else {
            LazyColumn(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                items(trades) { item ->
                    TradeJournalCard(trade = item, onDelete = onDeleteTrade)
                }
            }
        }
    }
}

@Composable
fun TradeJournalCard(trade: Trade, onDelete: (Trade) -> Unit) {
    val dateString = remember(trade.date) {
        val formatter = SimpleDateFormat("dd-MMM HH:mm", Locale.US)
        formatter.format(Date(trade.date))
    }

    Card(
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        shape = RoundedCornerShape(16.dp),
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, Color.White.copy(alpha = 0.05f), RoundedCornerShape(16.dp))
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(11.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Direction Column
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier
                    .clip(RoundedCornerShape(6.dp))
                    .background(if (trade.type == "BUY") BullishTeal.copy(alpha = 0.15f) else BearishCrimson.copy(alpha = 0.15f))
                    .padding(horizontal = 10.dp, vertical = 6.dp)
            ) {
                Text(
                    text = trade.type,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.Bold,
                    color = if (trade.type == "BUY") BullishTeal else BearishCrimson
                )
                Text(
                    text = "${trade.lotSize} L",
                    fontSize = 10.sp,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.8f),
                    fontWeight = FontWeight.Medium
                )
            }

            Spacer(modifier = Modifier.width(12.dp))

            // Details Column
            Column(modifier = Modifier.weight(1f)) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("$${String.format("%.2f", trade.entryPrice)}", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.onSurface)
                    Icon(Icons.Filled.ArrowForward, contentDescription = null, modifier = Modifier.size(10.dp), tint = MaterialTheme.colorScheme.onBackground)
                    Text("$${String.format("%.2f", trade.exitPrice)}", fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = MaterialTheme.colorScheme.onSurface)
                }
                Spacer(modifier = Modifier.height(2.dp))
                if (trade.note.isNotBlank()) {
                    Text(
                        text = trade.note,
                        fontSize = 10.sp,
                        color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.8f),
                        maxLines = 1
                    )
                }
                Text(
                    text = dateString,
                    fontSize = 8.sp,
                    color = Color.Gray
                )
            }

            // Profit indicator & Trash icon
            val prof = trade.profit
            Column(horizontalAlignment = Alignment.End) {
                Text(
                    text = if (prof >= 0) "+$${String.format("%.2f", prof)}" else "-$${String.format("%.2f", kotlin.math.abs(prof))}",
                    fontSize = 14.sp,
                    fontWeight = FontWeight.ExtraBold,
                    color = if (prof >= 0) BullishTeal else BearishCrimson
                )
                Spacer(modifier = Modifier.height(2.dp))
                Icon(
                    imageVector = Icons.Filled.DeleteOutline,
                    contentDescription = "O'chirish",
                    tint = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.5f),
                    modifier = Modifier
                        .size(16.dp)
                        .clickable { onDelete(trade) }
                )
            }
        }
    }
}


// --- 4. CHAT ASSISTANT SCREEN ---
@Composable
fun AssistantScreenBody(
    chatMessages: List<ChatMessage>,
    isWaiting: Boolean,
    onSendMessage: (String) -> Unit
) {
    var textInput by remember { mutableStateOf("") }
    val lazyListState = rememberLazyListState()

    // Keep chat auto scrolled
    LaunchedEffect(chatMessages.size, isWaiting) {
        if (chatMessages.isNotEmpty()) {
            lazyListState.animateScrollToItem(chatMessages.size)
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(12.dp)
    ) {
        // App Header and Brand
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(top = 10.dp, bottom = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text(
                    text = "AUREUS PROTOCOL",
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary.copy(alpha = 0.8f),
                    letterSpacing = 1.8.sp
                )
                Text(
                    text = "AI Chat Assistant",
                    fontSize = 20.sp,
                    fontWeight = FontWeight.SemiBold,
                    color = Color.White,
                    letterSpacing = 0.5.sp
                )
            }
        }

        Spacer(modifier = Modifier.height(10.dp))

        // Talk Log Box container
        Card(
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
            shape = RoundedCornerShape(24.dp),
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
                .border(1.dp, Color.White.copy(alpha = 0.05f), RoundedCornerShape(24.dp))
        ) {
            Box(modifier = Modifier.fillMaxSize().padding(8.dp)) {
                LazyColumn(
                    state = lazyListState,
                    modifier = Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    items(chatMessages) { msg ->
                        val isUser = msg.sender == "USER"
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start
                        ) {
                            Box(
                                modifier = Modifier
                                    .clip(
                                        RoundedCornerShape(
                                            topStart = 10.dp,
                                            topEnd = 10.dp,
                                            bottomStart = if (isUser) 10.dp else 0.dp,
                                            bottomEnd = if (isUser) 0.dp else 10.dp
                                        )
                                    )
                                    .background(
                                        if (isUser) MaterialTheme.colorScheme.primary else Color(0xFF1B2335)
                                    )
                                    .padding(horizontal = 12.dp, vertical = 8.dp)
                                    .widthIn(max = 280.dp)
                            ) {
                                Column {
                                    Text(
                                        text = if (isUser) msg.text else "",
                                        color = if (isUser) Color.Black else Color.White,
                                        fontSize = 13.sp,
                                        lineHeight = 18.sp,
                                        modifier = if (isUser) Modifier else Modifier.height(0.dp)
                                    )
                                    if (!isUser) {
                                        MarkdownText(text = msg.text)
                                    }
                                }
                            }
                        }
                    }

                    if (isWaiting) {
                        item {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.Start
                            ) {
                                Card(
                                    colors = CardDefaults.cardColors(containerColor = Color(0xFF1B2335)),
                                    shape = RoundedCornerShape(8.dp)
                                ) {
                                    Row(
                                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        CircularProgressIndicator(
                                            color = MaterialTheme.colorScheme.primary,
                                            strokeWidth = 2.dp,
                                            modifier = Modifier.size(12.dp)
                                        )
                                        Spacer(modifier = Modifier.width(6.dp))
                                        Text("Aureus AI yozmoqda...", color = Color.Gray, fontSize = 11.sp)
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        // Interaction Bottom Row
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedTextField(
                value = textInput,
                onValueChange = { textInput = it },
                placeholder = { Text("Savol so'rash... (RSI nima? risk boshqaruvi?)", fontSize = 12.sp, color = Color.Gray) },
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = MaterialTheme.colorScheme.primary,
                    unfocusedBorderColor = Color(0xFF1F2A3F)
                ),
                shape = RoundedCornerShape(10.dp),
                maxLines = 3,
                modifier = Modifier
                    .weight(1f)
                    .testTag("chat_text_input")
            )
            Spacer(modifier = Modifier.width(6.dp))
            FloatingActionButton(
                onClick = {
                    if (textInput.isNotBlank()) {
                        onSendMessage(textInput)
                        textInput = ""
                    }
                },
                containerColor = MaterialTheme.colorScheme.primary,
                contentColor = Color.Black,
                shape = RoundedCornerShape(10.dp),
                modifier = Modifier
                    .size(48.dp)
                    .testTag("chat_send_button")
            ) {
                Icon(Icons.Filled.Send, contentDescription = "Yuborish", modifier = Modifier.size(18.dp))
            }
        }
    }
}
