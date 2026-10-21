package com.example.aitrading.data

import android.content.Context
import android.util.Log
import com.google.firebase.auth.ktx.auth
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.ktx.Firebase
import kotlinx.coroutines.tasks.await

class TradingRepository(private val db: FirebaseFirestore) {

    constructor(context: Context) : this(
        FirebaseFirestore.getInstance(
            context.applicationContext.getString(
                context.resources.getIdentifier("firestore_database_id", "string", context.packageName)
            )
        )
    )

    private val auth = Firebase.auth

    private fun requireUserId(): String {
        return auth.currentUser?.uid ?: "guest_user"
    }

    suspend fun saveWatchlist(symbols: List<String>) {
        val uid = requireUserId()
        try {
            val data = mapOf("symbols" to symbols, "updatedAt" to System.currentTimeMillis())
            db.collection("users").document(uid).collection("watchlist").document("main").set(data).await()
        } catch (e: Exception) {
            Log.e("TradingRepository", "Error saving watchlist", e)
        }
    }

    suspend fun loadWatchlist(): List<String> {
        val uid = requireUserId()
        return try {
            val doc = db.collection("users").document(uid).collection("watchlist").document("main").get().await()
            @Suppress("UNCHECKED_CAST")
            doc.get("symbols") as? List<String> ?: listOf("NIFTY", "BANKNIFTY", "RELIANCE", "TCS")
        } catch (e: Exception) {
            listOf("NIFTY", "BANKNIFTY", "RELIANCE", "TCS")
        }
    }
}
