package com.example.data

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "trades")
data class Trade(
    @PrimaryKey(autoGenerate = true) val id: Int = 0,
    val type: String, // "BUY" or "SELL"
    val entryPrice: Double,
    val exitPrice: Double,
    val lotSize: Double,
    val profit: Double,
    val date: Long = System.currentTimeMillis(),
    val note: String = ""
)
