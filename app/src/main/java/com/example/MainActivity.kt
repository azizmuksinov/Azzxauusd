package com.example

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import com.example.data.AppDatabase
import com.example.ui.AureusViewModel
import com.example.ui.AureusViewModelFactory
import com.example.ui.DashboardScreen
import com.example.ui.theme.MyApplicationTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // Initialize local database & data access objects
        val database = AppDatabase.getDatabase(applicationContext)
        val tradeDao = database.tradeDao()

        enableEdgeToEdge()
        setContent {
            MyApplicationTheme {
                // Instantiates state-holders via Jetpack Compose standard lifecycle binders
                val viewModel: AureusViewModel = androidx.lifecycle.viewmodel.compose.viewModel(
                    factory = AureusViewModelFactory(tradeDao)
                )
                
                DashboardScreen(
                    viewModel = viewModel,
                    modifier = Modifier.fillMaxSize()
                )
            }
        }
    }
}
