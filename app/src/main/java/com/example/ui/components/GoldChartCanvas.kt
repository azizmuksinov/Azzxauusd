package com.example.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.model.GoldCandle
import com.example.ui.theme.BullishTeal
import com.example.ui.theme.BearishCrimson
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun GoldChartCanvas(
    candles: List<GoldCandle>,
    selectedCandle: GoldCandle?,
    onCandleSelected: (GoldCandle) -> Unit,
    modifier: Modifier = Modifier
) {
    if (candles.isEmpty()) {
        Box(modifier = modifier.fillMaxSize()) {
            Text("Ma'lumotlar yuklanmoqda...", color = Color.White, modifier = Modifier.padding(16.dp))
        }
        return
    }

    // Interactive pointer offset
    var dragX by remember { mutableStateOf<Float?>(null) }
    val dateFormat = remember { SimpleDateFormat("HH:mm dd-MMM", Locale.US) }

    Column(modifier = modifier) {
        // Main Candle Chart + SMA Overlays
        Box(
            modifier = Modifier
                .weight(2f)
                .fillMaxWidth()
                .background(Color(0xFF16181D))
                .pointerInput(candles) {
                    detectTapGestures { offset ->
                        val width = size.width.toFloat()
                        val colWidth = width / candles.size
                        val index = (offset.x / colWidth).toInt().coerceIn(0, candles.size - 1)
                        onCandleSelected(candles[index])
                        dragX = offset.x
                    }
                }
                .pointerInput(candles) {
                    detectDragGestures(
                        onDragStart = { offset ->
                            val width = size.width.toFloat()
                            val colWidth = width / candles.size
                            val index = (offset.x / colWidth).toInt().coerceIn(0, candles.size - 1)
                            onCandleSelected(candles[index])
                            dragX = offset.x
                        },
                        onDragEnd = { dragX = null },
                        onDragCancel = { dragX = null },
                        onDrag = { change, _ ->
                            val width = size.width.toFloat()
                            val colWidth = width / candles.size
                            val x = change.position.x
                            val index = (x / colWidth).toInt().coerceIn(0, candles.size - 1)
                            onCandleSelected(candles[index])
                            dragX = x
                        }
                    )
                }
        ) {
            Canvas(modifier = Modifier.fillMaxSize()) {
                val canvasWidth = size.width
                val canvasHeight = size.height
                val totalCandles = candles.size
                val candleWidth = canvasWidth / totalCandles

                // Find min and max price inside current viewport to scale y-axis
                val visiblePrices = candles.flatMap { listOf(it.high, it.low) }
                val maxPrice = (visiblePrices.maxOrNull() ?: 2400.0) * 1.002
                val minPrice = (visiblePrices.minOrNull() ?: 2300.0) * 0.998
                val priceRange = maxPrice - minPrice

                // Coordinates mapper
                fun getRawY(price: Double): Float {
                    return (canvasHeight - ((price - minPrice) / priceRange) * canvasHeight).toFloat()
                }

                // 1. Draw horizontal technical grid lines (6 dividers)
                val gridCount = 5
                for (i in 0..gridCount) {
                    val gridY = (canvasHeight / gridCount) * i
                    val gridPrice = maxPrice - (priceRange / gridCount) * i
                    
                    drawLine(
                        color = Color(0xFF2E323D),
                        start = Offset(0f, gridY),
                        end = Offset(canvasWidth, gridY),
                        strokeWidth = 1f
                    )

                    // Draw price numbers
                    drawContext.canvas.nativeCanvas.drawText(
                        String.format("$%.1f", gridPrice),
                        16f,
                        gridY - 8f,
                        android.graphics.Paint().apply {
                            color = android.graphics.Color.GRAY
                            textSize = 26f
                            isAntiAlias = true
                        }
                    )
                }

                // 2. Draw Candlesticks
                candles.forEachIndexed { index, candle ->
                    val x = (index * candleWidth) + (candleWidth / 2f)
                    
                    // Colors
                    val isBullish = candle.close >= candle.open
                    val candleColor = if (isBullish) BullishTeal else BearishCrimson

                    // Wick
                    drawLine(
                        color = candleColor,
                        start = Offset(x, getRawY(candle.high)),
                        end = Offset(x, getRawY(candle.low)),
                        strokeWidth = 2f
                    )

                    // Body
                    val bodyTop = getRawY(maxOf(candle.open, candle.close))
                    val bodyBottom = getRawY(minOf(candle.open, candle.close))
                    val bodyHeight = maxOf(3f, bodyBottom - bodyTop)

                    drawRect(
                        color = candleColor,
                        topLeft = Offset(x - (candleWidth * 0.35f), bodyTop),
                        size = Size(candleWidth * 0.7f, bodyHeight)
                    )
                }

                // 3. Draw SMA 20 (Orange) & SMA 50 (Blue) Overlay Lines
                val sma20Path = Path()
                val sma50Path = Path()
                var sma20Started = false
                var sma50Started = false

                candles.forEachIndexed { index, candle ->
                    val x = (index * candleWidth) + (candleWidth / 2f)

                    candle.sma20?.let { sma ->
                        val y = getRawY(sma)
                        if (!sma20Started) {
                            sma20Path.moveTo(x, y)
                            sma20Started = true
                        } else {
                            sma20Path.lineTo(x, y)
                        }
                    }

                    candle.sma50?.let { sma ->
                        val y = getRawY(sma)
                        if (!sma50Started) {
                            sma50Path.moveTo(x, y)
                            sma50Started = true
                        } else {
                            sma50Path.lineTo(x, y)
                        }
                    }
                }

                drawPath(
                    path = sma20Path,
                    color = Color(0xFFF39C12),
                    style = Stroke(width = 3f)
                )

                drawPath(
                    path = sma50Path,
                    color = Color(0xFF29B6F6),
                    style = Stroke(width = 3f)
                )

                // 4. Draw interactive crosshair cursor line
                dragX?.let { x ->
                    val colWidth = canvasWidth / candles.size
                    val idx = (x / colWidth).toInt().coerceIn(0, candles.size - 1)
                    val lineX = (idx * colWidth) + (colWidth / 2f)

                    drawLine(
                        color = Color.White.copy(alpha = 0.5f),
                        start = Offset(lineX, 0f),
                        end = Offset(lineX, canvasHeight),
                        strokeWidth = 1.5f,
                        pathEffect = androidx.compose.ui.graphics.PathEffect.dashPathEffect(floatArrayOf(10f, 10f))
                    )

                    // Overlay target price crosshair marker
                    val selected = candles[idx]
                    val lineY = getRawY(selected.close)
                    drawLine(
                        color = Color.White.copy(alpha = 0.5f),
                        start = Offset(0f, lineY),
                        end = Offset(canvasWidth, lineY),
                        strokeWidth = 1.5f,
                        pathEffect = androidx.compose.ui.graphics.PathEffect.dashPathEffect(floatArrayOf(10f, 10f))
                    )
                }
            }
        }

        Spacer(modifier = Modifier.height(6.dp))

        // RSI Sub-Panel Layout
        Box(
            modifier = Modifier
                .height(110.dp)
                .fillMaxWidth()
                .background(Color(0xFF111317))
        ) {
            Canvas(modifier = Modifier.fillMaxSize()) {
                val canvasWidth = size.width
                val canvasHeight = size.height
                val totalCandles = candles.size
                val candleWidth = canvasWidth / totalCandles

                // RSI bounds are always 0 - 100
                fun getRsiY(rsiValue: Double): Float {
                    return (canvasHeight - (rsiValue.toFloat() / 100f) * canvasHeight)
                }

                // Horizontal Guide Lines at 30 (Oversold), 50, and 70 (Overbought)
                val overboughtY = getRsiY(70.0)
                val oversoldY = getRsiY(30.0)
                val neutralY = getRsiY(50.0)

                // Draw shaded mid-zone range
                drawRect(
                    color = Color(0xFF9C27B0).copy(alpha = 0.05f),
                    topLeft = Offset(0f, overboughtY),
                    size = Size(canvasWidth, oversoldY - overboughtY)
                )

                // Limit guide dotted lines
                drawLine(
                    color = Color(0xFFEF5350).copy(alpha = 0.5f),
                    start = Offset(0f, overboughtY),
                    end = Offset(canvasWidth, overboughtY),
                    strokeWidth = 1.5f
                )
                drawLine(
                    color = Color(0xFF26A69A).copy(alpha = 0.5f),
                    start = Offset(0f, oversoldY),
                    end = Offset(canvasWidth, oversoldY),
                    strokeWidth = 1.5f
                )
                drawLine(
                    color = Color.Gray.copy(alpha = 0.2f),
                    start = Offset(0f, neutralY),
                    end = Offset(canvasWidth, neutralY),
                    strokeWidth = 1f
                )

                // Draw RSI labels
                drawContext.canvas.nativeCanvas.drawText("RSI (14) Overbought 70", 16f, overboughtY - 6f, android.graphics.Paint().apply {
                    color = android.graphics.Color.parseColor("#EF5350")
                    textSize = 22f
                })
                drawContext.canvas.nativeCanvas.drawText("RSI (14) Oversold 30", 16f, oversoldY + 22f, android.graphics.Paint().apply {
                    color = android.graphics.Color.parseColor("#26A69A")
                    textSize = 22f
                })

                // Draw RSI flow path line
                val rsiPath = Path()
                var systemStarted = false
                candles.forEachIndexed { index, candle ->
                    val x = (index * candleWidth) + (candleWidth / 2f)
                    val rsi = candle.rsi ?: 50.0
                    val y = getRsiY(rsi)

                    if (!systemStarted) {
                        rsiPath.moveTo(x, y)
                        systemStarted = true
                    } else {
                        rsiPath.lineTo(x, y)
                    }
                }

                drawPath(
                    path = rsiPath,
                    color = Color(0xFF9C27B0),
                    style = Stroke(width = 3.5f)
                )

                // Draw vertical crosshair timeline matching top graph
                dragX?.let { x ->
                    val colWidth = canvasWidth / candles.size
                    val idx = (x / colWidth).toInt().coerceIn(0, candles.size - 1)
                    val lineX = (idx * colWidth) + (colWidth / 2f)

                    drawLine(
                        color = Color.White.copy(alpha = 0.3f),
                        start = Offset(lineX, 0f),
                        end = Offset(lineX, canvasHeight),
                        strokeWidth = 1.5f
                    )
                }
            }
        }
    }
}
