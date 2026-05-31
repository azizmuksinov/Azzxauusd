package com.example.model

data class GoldCandle(
    val timestamp: Long,
    val open: Double,
    val high: Double,
    val low: Double,
    val close: Double,
    val volume: Double,
    val sma20: Double? = null,
    val sma50: Double? = null,
    val rsi: Double? = null
)
