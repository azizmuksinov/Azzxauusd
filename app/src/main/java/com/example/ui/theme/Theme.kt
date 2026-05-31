package com.example.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val AureusColorScheme = darkColorScheme(
    primary = GoldPrimary,
    onPrimary = DarkBg,
    secondary = AmberSecondary,
    onSecondary = DarkBg,
    background = DarkBg,
    onBackground = TextPale,
    surface = CardSurface,
    onSurface = TextWhite,
    primaryContainer = CardSurface,
    onPrimaryContainer = GoldPrimary
)

@Composable
fun MyApplicationTheme(
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = AureusColorScheme,
        typography = Typography,
        content = content
    )
}
