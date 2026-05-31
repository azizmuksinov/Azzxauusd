package com.example.api

import com.squareup.moshi.JsonClass
import okhttp3.OkHttpClient
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import retrofit2.http.GET
import retrofit2.http.Path
import retrofit2.http.Query
import java.util.concurrent.TimeUnit

@JsonClass(generateAdapter = true)
data class YahooQuote(
    val open: List<Double?>?,
    val high: List<Double?>?,
    val low: List<Double?>?,
    val close: List<Double?>?,
    val volume: List<Long?>?
)

@JsonClass(generateAdapter = true)
data class YahooIndicators(
    val quote: List<YahooQuote>?
)

@JsonClass(generateAdapter = true)
data class YahooResult(
    val timestamp: List<Long>?,
    val indicators: YahooIndicators?
)

@JsonClass(generateAdapter = true)
data class YahooChart(
    val result: List<YahooResult>?,
    val error: Any?
)

@JsonClass(generateAdapter = true)
data class YahooResponse(
    val chart: YahooChart?
)

interface YahooFinanceService {
    @GET("v8/finance/chart/{symbol}")
    suspend fun getChart(
        @Path("symbol") symbol: String,
        @Query("interval") interval: String,
        @Query("range") range: String
    ): YahooResponse
}

object YahooFinanceClient {
    private const val BASE_URL = "https://query1.finance.yahoo.com/"

    private val okHttpClient = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    val service: YahooFinanceService by lazy {
        val retrofit = Retrofit.Builder()
            .baseUrl(BASE_URL)
            .client(okHttpClient)
            .addConverterFactory(MoshiConverterFactory.create())
            .build()
        retrofit.create(YahooFinanceService::class.java)
    }
}
