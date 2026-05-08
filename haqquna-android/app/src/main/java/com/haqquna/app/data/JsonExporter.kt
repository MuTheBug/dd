package com.haqquna.app.data

import android.content.Context
import android.net.Uri
import com.google.gson.GsonBuilder
import com.google.gson.JsonObject
import com.google.gson.JsonArray
import com.google.gson.JsonElement
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class JsonExporter(private val ctx: Context) {

    private val gson = GsonBuilder().setPrettyPrinting().create()

    suspend fun writeTo(uri: Uri, entries: List<HaqqunaEntry>): Result<Int> = runCatching {
        val arr = JsonArray()
        for (e in entries) arr.add(toJson(e))

        ctx.contentResolver.openOutputStream(uri, "wt")?.use { os ->
            os.bufferedWriter(Charsets.UTF_8).use { it.write(gson.toJson(arr)) }
        } ?: throw IllegalStateException("تعذّر فتح ملف التصدير")

        entries.size
    }

    fun defaultFilename(): String {
        val ts = SimpleDateFormat("yyyy-MM-dd_HHmm", Locale.ENGLISH).format(Date())
        return "haqquna_backup_$ts.json"
    }

    private fun toJson(e: HaqqunaEntry): JsonElement {
        val obj = JsonObject()
        obj.addProperty("client_uuid", e.clientUuid)
        obj.addProperty("created_at", e.createdAt)
        obj.addProperty("updated_at", e.updatedAt)
        obj.addProperty("status", e.syncStatus.name)
        obj.addProperty("display_name", e.displayName)
        e.serverId?.let { obj.addProperty("server_id", it) }

        val fields = JsonObject()
        for ((k, v) in e.fields) fields.addProperty(k, v)
        obj.add("fields", fields)

        obj.add("companions", gson.toJsonTree(e.companions))
        obj.add("witnesses", gson.toJsonTree(e.witnesses))
        obj.add("children", gson.toJsonTree(e.children))

        return obj
    }
}
