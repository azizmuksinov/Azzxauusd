package com.example.data

import androidx.room.*
import kotlinx.coroutines.flow.Flow

@Dao
interface TradeDao {
    @Query("SELECT * FROM trades ORDER BY date DESC")
    fun getAllTrades(): Flow<List<Trade>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertTrade(trade: Trade)

    @Delete
    suspend fun deleteTrade(trade: Trade)

    @Update
    suspend fun updateTrade(trade: Trade)
}
