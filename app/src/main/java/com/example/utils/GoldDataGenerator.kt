package com.example.utils

import com.example.model.GoldCandle
import kotlin.math.abs

object GoldDataGenerator {

    suspend fun fetchRealTimeCandles(timeframe: String): List<GoldCandle> {
        val symbol = "GC=F" // Gold (XAU) Futures contract on Yahoo Finance
        val (interval, range) = when (timeframe) {
            "1H" -> Pair("1h", "5d")
            "4H" -> Pair("1h", "15d") // Yahoo API does not native-support 4h nicely, so we show expanded 1H 15 Days
            else -> Pair("1d", "90d") // "1D"
        }

        return try {
            val response = com.example.api.YahooFinanceClient.service.getChart(symbol, interval, range)
            val result = response.chart?.result?.firstOrNull()
            val timestamps = result?.timestamp
            val quote = result?.indicators?.quote?.firstOrNull()

            if (timestamps != null && quote != null) {
                val list = ArrayList<GoldCandle>()
                for (i in timestamps.indices) {
                    val t = timestamps[i] * 1000L // convert to ms
                    val o = quote.open?.getOrNull(i)
                    val h = quote.high?.getOrNull(i)
                    val l = quote.low?.getOrNull(i)
                    val c = quote.close?.getOrNull(i)
                    val v = quote.volume?.getOrNull(i)?.toDouble() ?: 0.0

                    if (o != null && h != null && l != null && c != null) {
                        list.add(
                            GoldCandle(
                                timestamp = t,
                                open = o,
                                high = h,
                                low = l,
                                close = c,
                                volume = v
                            )
                        )
                    }
                }
                
                if (list.isNotEmpty()) {
                    calculateIndicators(list)
                } else {
                    generateCandles(timeframe, 80)
                }
            } else {
                generateCandles(timeframe, 80)
            }
        } catch (e: Exception) {
            android.util.Log.e("GoldDataGenerator", "Yahoo Finance error, using mock generator fallback", e)
            generateCandles(timeframe, 80)
        }
    }

    fun generateCandles(timeframe: String, count: Int = 100): List<GoldCandle> {
        val candles = ArrayList<GoldCandle>()
        
        // Base parameters depending on timeframe
        var price = when (timeframe) {
            "1H" -> 2415.5
            "4H" -> 2390.0
            else -> 2355.0 // "1D"
        }
        
        val intervalMs = when (timeframe) {
            "1H" -> 3600000L
            "4H" -> 14400000L
            else -> 86400000L
        }
        
        var currentMs = System.currentTimeMillis() - (count * intervalMs)
        val random = java.util.Random(42) // Seeded for reproducibility
        
        for (i in 0 until count) {
            currentMs += intervalMs
            
            // Generate standard market oscillations
            val trend = 0.5 * (i - count / 3.0) / count // general upward bias
            val vol = 4.0 + random.nextDouble() * 12.0
            val move = (random.nextDouble() - 0.48 + trend) * vol
            
            val open = price
            val close = price + move
            val high = maxOf(open, close) + random.nextDouble() * (vol * 0.4)
            val low = minOf(open, close) - random.nextDouble() * (vol * 0.4)
            val volume = 1000.0 + random.nextDouble() * 9000.0
            
            price = close
            
            candles.add(
                GoldCandle(
                    timestamp = currentMs,
                    open = open,
                    high = high,
                    low = low,
                    close = close,
                    volume = volume
                )
            )
        }
        
        // Post-process to calculate indicators
        return calculateIndicators(candles)
    }

    private fun calculateIndicators(rawCandles: List<GoldCandle>): List<GoldCandle> {
        val result = rawCandles.toMutableList()
        
        // 1. Calculate SMA 20 and SMA 50
        for (i in result.indices) {
            val sma20 = if (i >= 19) {
                result.subList(i - 19, i + 1).map { it.close }.average()
            } else null
            
            val sma50 = if (i >= 49) {
                result.subList(i - 49, i + 1).map { it.close }.average()
            } else null
            
            result[i] = result[i].copy(sma20 = sma20, sma50 = sma50)
        }
        
        // 2. Calculate RSI (14)
        // First, calculate price changes (gains/losses)
        val changes = DoubleArray(result.size)
        for (i in 1 until result.size) {
            changes[i] = result[i].close - result[i - 1].close
        }
        
        for (i in result.indices) {
            if (i < 14) {
                result[i] = result[i].copy(rsi = 50.0) // baseline default
                continue
            }
            
            var sumGain = 0.0
            var sumLoss = 0.0
            
            // Calculate averages over the 14 window
            for (j in i - 13..i) {
                val diff = changes[j]
                if (diff > 0) {
                    sumGain += diff
                } else {
                    sumLoss += abs(diff)
                }
            }
            
            val avgGain = sumGain / 14.0
            val avgLoss = sumLoss / 14.0
            
            val rsi = if (avgLoss == 0.0) {
                100.0
            } else {
                val rs = avgGain / avgLoss
                100.0 - (100.0 / (1.0 + rs))
            }
            
            result[i] = result[i].copy(rsi = rsi)
        }
        
        return result
    }
}
