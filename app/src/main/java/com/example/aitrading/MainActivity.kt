package com.example.aitrading

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.*
import androidx.lifecycle.viewmodel.compose.viewModel
import com.example.aitrading.ui.screens.AuthScreen
import com.example.aitrading.ui.screens.MainScreenWith25Tabs
import com.example.aitrading.ui.theme.AITradingTheme
import com.example.aitrading.viewmodel.TradingViewModel
import com.google.firebase.auth.FirebaseAuth
import com.google.firebase.auth.ktx.auth
import com.google.firebase.ktx.Firebase

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            AITradingTheme {
                AppRootContent()
            }
        }
    }
}

@Composable
fun AppRootContent() {
    val viewModel: TradingViewModel = viewModel()
    var currentUser by remember { mutableStateOf(Firebase.auth.currentUser) }

    DisposableEffect(Unit) {
        val listener = FirebaseAuth.AuthStateListener { auth ->
            currentUser = auth.currentUser
        }
        Firebase.auth.addAuthStateListener(listener)
        onDispose {
            Firebase.auth.removeAuthStateListener(listener)
        }
    }

    if (currentUser == null) {
        AuthScreen(
            onAuthSuccess = { currentUser = Firebase.auth.currentUser }
        )
    } else {
        MainScreenWith25Tabs(viewModel = viewModel)
    }
}
