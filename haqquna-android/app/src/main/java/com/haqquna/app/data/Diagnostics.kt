package com.haqquna.app.data

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

object Diagnostics {

    private const val MAX = 500

    private val _entries = MutableStateFlow<List<DiagnosticEntry>>(emptyList())
    val entries: StateFlow<List<DiagnosticEntry>> = _entries.asStateFlow()

    fun info(msg: String) = add(msg, DiagnosticEntry.Level.INFO)
    fun ok(msg: String) = add(msg, DiagnosticEntry.Level.OK)
    fun warn(msg: String) = add(msg, DiagnosticEntry.Level.WARN)
    fun error(msg: String) = add(msg, DiagnosticEntry.Level.ERROR)

    private fun add(msg: String, level: DiagnosticEntry.Level) {
        _entries.update { current ->
            val next = current + DiagnosticEntry(message = msg, level = level)
            if (next.size > MAX) next.takeLast(MAX) else next
        }
    }

    fun clear() = _entries.update { emptyList() }
}
