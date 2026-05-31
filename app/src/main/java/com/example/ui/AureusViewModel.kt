package com.example.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.example.api.Content
import com.example.api.GenerateContentRequest
import com.example.api.GenerationConfig
import com.example.api.Part
import com.example.api.RetrofitClient
import com.example.data.Trade
import com.example.data.TradeDao
import com.example.model.GoldCandle
import com.example.utils.GoldDataGenerator
import com.example.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

enum class AureusScreen {
    MARKET,
    AI_SIGNALS,
    JOURNAL,
    ASSISTANT
}

data class ChatMessage(
    val sender: String, // "USER" or "AI"
    val text: String,
    val timestamp: Long = System.currentTimeMillis()
)

class AureusViewModel(private val tradeDao: TradeDao) : ViewModel() {

    // --- Navigation ---
    private val _currentScreen = MutableStateFlow(AureusScreen.MARKET)
    val currentScreen: StateFlow<AureusScreen> = _currentScreen.asStateFlow()

    fun navigateTo(screen: AureusScreen) {
        _currentScreen.value = screen
    }

    // --- Market Technical State ---
    private val _timeframe = MutableStateFlow("1H") // "1H", "4H", "1D"
    val timeframe: StateFlow<String> = _timeframe.asStateFlow()

    private val _candles = MutableStateFlow<List<GoldCandle>>(emptyList())
    val candles: StateFlow<List<GoldCandle>> = _candles.asStateFlow()

    private val _selectedCandle = MutableStateFlow<GoldCandle?>(null)
    val selectedCandle: StateFlow<GoldCandle?> = _selectedCandle.asStateFlow()

    init {
        loadMarketData("1H")
    }

    fun loadMarketData(tf: String) {
        _timeframe.value = tf
        viewModelScope.launch {
            val generated = withContext(Dispatchers.Default) {
                GoldDataGenerator.fetchRealTimeCandles(tf)
            }
            _candles.value = generated
            _selectedCandle.value = generated.lastOrNull()
        }
    }

    fun selectCandle(candle: GoldCandle?) {
        _selectedCandle.value = candle ?: _candles.value.lastOrNull()
    }

    // --- Room Database (Trading Journal Log) ---
    val allTrades = tradeDao.getAllTrades()

    fun addTrade(type: String, entryPrice: Double, exitPrice: Double, lotSize: Double, note: String) {
        viewModelScope.launch {
            // Gold Standard Calculation: 1 Lot = 100 Ounces of Gold
            // Profit for BUY = (Exit - Entry) * Lot * 100
            // Profit for SELL = (Entry - Exit) * Lot * 100
            val multiplier = if (type.uppercase() == "BUY") 1.0 else -1.0
            val profit = (exitPrice - entryPrice) * multiplier * lotSize * 100.0
            
            val trade = Trade(
                type = type.uppercase(),
                entryPrice = entryPrice,
                exitPrice = exitPrice,
                lotSize = lotSize,
                profit = profit,
                note = note
            )
            withContext(Dispatchers.IO) {
                tradeDao.insertTrade(trade)
            }
        }
    }

    fun deleteTrade(trade: Trade) {
        viewModelScope.launch {
            withContext(Dispatchers.IO) {
                tradeDao.deleteTrade(trade)
            }
        }
    }

    // --- AI Signal Generator with Gemini ---
    private val _isAnalyzing = MutableStateFlow(false)
    val isAnalyzing: StateFlow<Boolean> = _isAnalyzing.asStateFlow()

    private val _aiAnalysisText = MutableStateFlow<String?>(null)
    val aiAnalysisText: StateFlow<String?> = _aiAnalysisText.asStateFlow()

    fun queryAiSignal() {
        val currentCandles = _candles.value
        if (currentCandles.isEmpty()) return

        _isAnalyzing.value = true
        _aiAnalysisText.value = null

        viewModelScope.launch {
            val key = BuildConfig.GEMINI_API_KEY
            if (key.isEmpty() || key == "MY_GEMINI_API_KEY") {
                // Return descriptive localized Uzbek fallback when key is not active
                val fallback = generateFallbackSignalUzbek(currentCandles.last())
                _aiAnalysisText.value = fallback
                _isAnalyzing.value = false
                return@launch
            }

            // Build full textual summary of recent market data
            val last15 = currentCandles.takeLast(15)
            val candleSummary = last15.joinToString("\n") { c ->
                "Yopilish: $${String.format("%.2f", c.close)}, RSI: ${String.format("%.1f", c.rsi ?: 50.0)}, SMA20: $${String.format("%.2f", c.sma20 ?: c.close)}"
            }

            val lastCandle = currentCandles.last()
            val prompt = """
                Sen Aureus XAUUSD professional AI trading tizimisan (Uzbek tilida javob ber).
                Oltin narxlarini va texnik tahlil ko'rsatkichlarini tahlil qil:
                
                $candleSummary
                
                So'nggi indikatorlar:
                - Joriy Oltin Narxi: $${String.format("%.2f", lastCandle.close)}
                - RSI (14): ${String.format("%.1f", lastCandle.rsi ?: 50.0)}
                - SMA 20: $${String.format("%.2f", lastCandle.sma20 ?: lastCandle.close)}
                - SMA 50: $${String.format("%.2f", lastCandle.sma50 ?: lastCandle.close)}
                - Kunlik eng baland: $${String.format("%.2f", lastCandle.high)}
                - Kunlik eng past: $${String.format("%.2f", lastCandle.low)}
                - Hozirgi tanlangan Taymfreym: ${_timeframe.value}
                
                Iltimos quyidagilarga asosan mukammal O'zbek tilida, chiroyli dizaynda va his-tuyg'usiz professional javob ber:
                1. 📈 BOZOR TAHLILI: Narx darajalari va kuch zonasi (bullish/bearish).
                2. 🚦 SIGNALLAR: [STRONG BUY / BUY / NEUTRAL / SELL / STRONG SELL] va aniq texnik sabablar.
                3. 🎯 DARAJALAR: Kirish nuqtasi, TP (Take Profit) va SL (Stop Loss) aniq raqamli darajalari.
                4. ⚠️ RISK LEVEL: Havfsizlik va ehtiyot choralari (past, o'rtacha, yuqori).
            """.trimIndent()

            try {
                val request = GenerateContentRequest(
                    contents = listOf(Content(parts = listOf(Part(text = prompt)))),
                    generationConfig = GenerationConfig(temperature = 0.4f)
                )

                val response = withContext(Dispatchers.IO) {
                    RetrofitClient.service.generateContent(key, request)
                }

                val aiResponseText = response.candidates?.firstOrNull()?.content?.parts?.firstOrNull()?.text
                if (!aiResponseText.isNullOrBlank()) {
                    _aiAnalysisText.value = aiResponseText
                } else {
                    _aiAnalysisText.value = "Kechirasiz, sun'iy intellekt tahlili muvaffaqiyatsiz tugadi. Namuna signal tahlilini yuklaymiz:\n\n" + generateFallbackSignalUzbek(lastCandle)
                }
            } catch (e: Exception) {
                _aiAnalysisText.value = "Xatolik yuz berdi: ${e.localizedMessage ?: "Tizim ulanishida cheklov"}\n\nNamuna signal tahlili yuklandi:\n\n" + generateFallbackSignalUzbek(lastCandle)
            } finally {
                _isAnalyzing.value = false
            }
        }
    }

    private fun generateFallbackSignalUzbek(last: GoldCandle): String {
        val rsi = last.rsi ?: 50.0
        val price = last.close
        val signal = if (rsi < 35) "STRONG BUY" else if (rsi > 65) "STRONG SELL" else if (rsi < 50) "BUY" else "SELL"
        val tp = if (signal.contains("BUY")) price + 42.0 else price - 42.0
        val sl = if (signal.contains("BUY")) price - 22.0 else price + 22.0
        val text = """
            📈 **BOZOR TAHLILI (Simulyatsiya):**
            Joriy oltin narxi **$${String.format("%.2f", price)}** atrofida shakllanmoqda. RSI ko'rsatkichi **${String.format("%.1f", rsi)}** da bo'lib, bozor ${if (rsi > 60) "overbought (o'ta qizigan)" else if (rsi < 40) "oversold (arzonlashgan)" else "neytral barqaror"} holatdaligini ko'rsatadi. 
            SMA_20 ($${String.format("%.2f", last.sma20 ?: (price - 5.0))}) chizig'i narxdan ${if (price > (last.sma20 ?: 0.0)) "pastda bo'lib, buqa (bulish)" else "tepada bo'lib, ayiq (bearish)"} harakatini tasdiqlamoqda.

            🚦 **PREMIUM SIGNAL:**
            **$signal**
            
            **Texnik sabab:** RSI va SMA kombinatsiyasi bozorning keyingi qisqa muddatli burilishini ko'rsatmoqda. Narx impulsiv ravishda o'zgarish arafasida.

            🎯 **SAREUS MAQSADLI DARAJALAR (TP / SL):**
            - **Kirish narxi:** $${String.format("%.2f", price)}
            - **Take Profit (TP):** $${String.format("%.2f", tp)}
            - **Stop Loss (SL):** $${String.format("%.2f", sl)}

            ⚠️ RISK DARAJA: **O'rtacha**
            _Eslatma: Haqiqiy savdo qilishdan oldin risk modelingizni va kapitalingizni boshqaring._
        """.trimIndent()
        return text
    }

    // --- AI Chat Coach ---
    private val _chatMessages = MutableStateFlow<List<ChatMessage>>(
        listOf(
            ChatMessage("AI", "Salom! Men Aureus AI professional Oltin bo'yicha yordamchingizman. XAUUSD bozori, trading strategiyalari, texnik ko'rsatkichlar yoki risklarni boshqarish haqida so'rang, yordam beraman!")
        )
    )
    val chatMessages: StateFlow<List<ChatMessage>> = _chatMessages.asStateFlow()

    private val _isChatWaiting = MutableStateFlow(false)
    val isChatWaiting: StateFlow<Boolean> = _isChatWaiting.asStateFlow()

    fun sendChatMessage(text: String) {
        if (text.isBlank()) return
        
        val userMsg = ChatMessage("USER", text)
        _chatMessages.value = _chatMessages.value + userMsg
        _isChatWaiting.value = true

        viewModelScope.launch {
            val key = BuildConfig.GEMINI_API_KEY
            if (key.isEmpty() || key == "MY_GEMINI_API_KEY") {
                // Pre-configured elegant responses in Uzbek depending on search strings
                val response = getOfflineReplyUzbek(text)
                _chatMessages.value = _chatMessages.value + ChatMessage("AI", response)
                _isChatWaiting.value = false
                return@launch
            }

            // Standard Gemini API Query
            val currentContext = _chatMessages.value.takeLast(6).joinToString("\n") { 
                "${it.sender}: ${it.text}"
            }
            val prompt = """
                Sariq oltin (XAUUSD) tradingi bo'yicha professional maslahatchisan.
                Mana savollarning qisqacha konteksti:
                
                $currentContext
                
                Oxirgi foydalanuvchi savoli: "$text"
                
                Iltimos chiroyli, motivatsion va professional O'zbek tilida javob yoz. Javob qisqa, lo'nda lekin texnik jihatdan to'la bo'lsin.
            """.trimIndent()

            try {
                val request = GenerateContentRequest(
                    contents = listOf(Content(parts = listOf(Part(text = prompt)))),
                    generationConfig = GenerationConfig(temperature = 0.5f)
                )

                val response = withContext(Dispatchers.IO) {
                    RetrofitClient.service.generateContent(key, request)
                }

                val aiMsg = response.candidates?.firstOrNull()?.content?.parts?.firstOrNull()?.text
                if (!aiMsg.isNullOrBlank()) {
                    _chatMessages.value = _chatMessages.value + ChatMessage("AI", aiMsg)
                } else {
                    _chatMessages.value = _chatMessages.value + ChatMessage("AI", "Kechirasiz, Serverda yuklama yuqori bo'lganligi sababli javob bera olmadim. Savolingiz bo'yicha yana bir bor so'rab ko'ring.")
                }
            } catch (e: Exception) {
                _chatMessages.value = _chatMessages.value + ChatMessage("AI", "Tizimda kichik ulanish xatoli: ${e.localizedMessage ?: "Tekshiruv ulanishi muvaffaqiyatsiz"}. Mana siz so'ragan mavzuga doir foydali maslahat:\n\n" + getOfflineReplyUzbek(text))
            } finally {
                _isChatWaiting.value = false
            }
        }
    }

    private fun getOfflineReplyUzbek(query: String): String {
        val q = query.lowercase()
        return when {
            q.contains("rsi") || q.contains("indikator") -> """
                **RSI (Relative Strength Index) Indikatori haqida:**
                RSI 0 dan 100 gacha bo'lgan diapazonda o'lchanadi. 
                - **30 dan past ko'rsatkich:** Oltinning haddan tashqari ko'p sotilganini (Oversold) anglatadi, bu odatda xarid qilish (BUY) signali hisoblanadi.
                - **70 dan yuqori ko'rsatkich:** Oltinning haddan tashqari qizitib yuborilganini (Overbought) anglatadi, bu sotish (SELL) signali bo'lishi mumkin.
                Oltin kabi o'ta trendli bozorlarda RSI 50 chizig'ini qaysi tomonga kesib o'tishiga ham e'tibor qaratish kerak.
            """.trimIndent()
            q.contains("strateg") || q.contains("tizim") || q.contains("usul") -> """
                **Oltin (XAUUSD) uchun eng foydali Strategiyalar:**
                1. **Breakout Strategy:** Oltin ko'pincha asosiy qo'llab-quvvatlash va qarshilik zonalarini yorgandan keyin kuchli impuls beradi. Konsolidatsiya doirasining yuqori yoki pastki chegaralarini yorib o'tishini kuting.
                2. **Scalping (1H/ 15M):** Kichik tahlil taymfreymlarida RSI va MACD yordamida kichik lotlar bilan tez-tez narx harakatidan foydalanish.
                3. **Trend Following (SMA 20/50 cross):** 20 kunlik SMA 50 kunlik SMA-ni kross qilganda (oltin krossover) trend boshlangani tasdiqlanadi.
            """.trimIndent()
            q.contains("risk") || q.contains("lot") || q.contains("pul") -> """
                **Aureus Risk Nazorati Qoidalari:**
                - **1% Qoidasi:** Hech qachon bir dona savdoda umumiy kapitalingizning 1%-2% dan ortig'idan risk qilmang.
                - **Stop Loss Majburiy:** Oltin o'ta tez va spekulyativ o'zgaradi. SL qo'ymaslik hisob varag'ingizni (deposit) butkul tozalovchi asosiy xatodir.
                - **Muvofiq Lot Tanlash:** ${"$"}1000 depozit uchun maksimal barqaror lot o'lchami `0.01` dan `0.03` gacha tavsiya etiladi.
            """.trimIndent()
            else -> """
                Oltin (Gold/XAUUSD) — dunyodagi eng likvidli va ayni paytda o'ta likvidli harakatchan instrumentdir. 
                U AQSH dollarining kuchi (DXY indeks) va geosiyosiy vaziyatlar bilan teskari bog'liqlikka ega. 
                Sizga savdo rejasi tuzish, risklarni hisoblash yoki texnik tahlillar bo'yicha yana qanday maslahat bera olaman?
            """.trimIndent()
        }
    }
}

class AureusViewModelFactory(private val tradeDao: TradeDao) : ViewModelProvider.Factory {
    override fun <T : ViewModel> create(modelClass: Class<T>): T {
        if (modelClass.isAssignableFrom(AureusViewModel::class.java)) {
            @Suppress("UNCHECKED_CAST")
            return AureusViewModel(tradeDao) as T
        }
        throw IllegalArgumentException("Unknown ViewModel class")
    }
}
