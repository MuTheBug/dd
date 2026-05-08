package com.haqquna.app.data

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "haqquna_settings")

class SettingsStore(private val ctx: Context) {

    private object Keys {
        val SERVER = stringPreferencesKey("server_url")
        val USERNAME = stringPreferencesKey("sync_user")
        val PASSWORD = stringPreferencesKey("sync_pass")
        val COLLECTOR = stringPreferencesKey("collector_name")
    }

    val server: Flow<String> = ctx.dataStore.data.map { it[Keys.SERVER] ?: DEFAULT_SERVER }
    val username: Flow<String> = ctx.dataStore.data.map { it[Keys.USERNAME] ?: "" }
    val password: Flow<String> = ctx.dataStore.data.map { it[Keys.PASSWORD] ?: "" }
    val collector: Flow<String> = ctx.dataStore.data.map { it[Keys.COLLECTOR] ?: "" }

    suspend fun snapshot(): Snapshot {
        val prefs = ctx.dataStore.data.first()
        return Snapshot(
            server = prefs[Keys.SERVER] ?: DEFAULT_SERVER,
            username = prefs[Keys.USERNAME] ?: "",
            password = prefs[Keys.PASSWORD] ?: "",
            collector = prefs[Keys.COLLECTOR] ?: ""
        )
    }

    suspend fun setServer(url: String) = ctx.dataStore.edit { it[Keys.SERVER] = normalizeUrl(url) }
    suspend fun setCredentials(user: String, pass: String) = ctx.dataStore.edit {
        it[Keys.USERNAME] = user
        it[Keys.PASSWORD] = pass
    }
    suspend fun setCollector(name: String) = ctx.dataStore.edit { it[Keys.COLLECTOR] = name }

    data class Snapshot(
        val server: String,
        val username: String,
        val password: String,
        val collector: String
    )

    companion object {
        const val DEFAULT_SERVER = "http://192.168.1.100:5000"

        fun normalizeUrl(raw: String): String {
            val s = raw.trim().trimEnd('/')
            if (s.isEmpty()) return DEFAULT_SERVER
            return if (s.startsWith("http://") || s.startsWith("https://")) s else "http://$s"
        }
    }
}
