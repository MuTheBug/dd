package com.haqquna.app.data

import com.google.gson.annotations.SerializedName
import java.util.UUID

enum class CaseStatus(val key: String, val arabic: String) {
    SURVIVOR("survivor", "ناجٍ (شخص أُفرج عنه / هرب)"),
    ENFORCED("enforced", "مغيّب قسراً (لا يُعرف مصيره)"),
    DECEASED("deceased", "متوفى (مؤكد الوفاة)");

    companion object {
        fun fromKey(k: String?) = values().firstOrNull { it.key == k }
    }
}

data class Companion_(
    val name: String = "",
    val relation: String = "",
    val nationalId: String = "",
    val phone: String = "",
    val notes: String = ""
)

data class Witness(
    val name: String = "",
    val relation: String = "",
    val phone: String = "",
    val statement: String = ""
)

data class Child(
    val name: String = "",
    val gender: String = "",
    val birthYear: String = "",
    val notes: String = ""
)

data class FileAttachment(
    val field: String,
    val localPath: String,
    val mime: String,
    val displayName: String
)

enum class EntryStatus { DRAFT, PENDING, SYNCING, SYNCED, FAILED }

data class HaqqunaEntry(
    val clientUuid: String = UUID.randomUUID().toString(),
    val createdAt: Long = System.currentTimeMillis(),
    val updatedAt: Long = System.currentTimeMillis(),
    val syncStatus: EntryStatus = EntryStatus.DRAFT,
    val serverId: Long? = null,
    val syncError: String? = null,
    val fields: Map<String, String> = emptyMap(),
    val companions: List<Companion_> = emptyList(),
    val witnesses: List<Witness> = emptyList(),
    val children: List<Child> = emptyList(),
    val attachments: List<FileAttachment> = emptyList()
) {
    val displayName: String
        get() = listOfNotNull(
            fields["first_name"]?.takeIf { it.isNotBlank() },
            fields["father_name"]?.takeIf { it.isNotBlank() },
            fields["last_name"]?.takeIf { it.isNotBlank() }
        ).joinToString(" ").ifBlank { "بدون اسم" }

    val statusEnum: CaseStatus?
        get() = CaseStatus.fromKey(fields["status"])
}

data class SyncCredentials(val username: String, val password: String)

data class LoginResponse(
    @SerializedName("success") val success: Boolean,
    @SerializedName("error") val error: String? = null,
    @SerializedName("display_name") val displayName: String? = null,
    @SerializedName("role") val role: String? = null
)

data class SyncEntryResponse(
    @SerializedName("success") val success: Boolean,
    @SerializedName("server_id") val serverId: Long? = null,
    @SerializedName("duplicate_uuid") val duplicate: Boolean = false,
    @SerializedName("error") val error: String? = null,
    @SerializedName("errors") val errors: Map<String, String>? = null,
    @SerializedName("message") val message: String? = null
)

data class PingResponse(
    @SerializedName("ok") val ok: Boolean = false,
    @SerializedName("app") val app: String? = null,
    @SerializedName("version") val version: String? = null
)

data class DiagnosticEntry(
    val timestamp: Long = System.currentTimeMillis(),
    val message: String,
    val level: Level
) {
    enum class Level { INFO, OK, WARN, ERROR }
}

data class ImportSummary(
    val total: Int,
    val valid: Int,
    val duplicates: Int,
    val invalid: Int,
    val errors: List<ImportError>,
    val validEntries: List<HaqqunaEntry>
)

data class ImportError(
    val index: Int,
    val name: String,
    val errorCode: String,
    val message: String
)

data class SyncResult(
    val entriesSynced: Int,
    val entriesFailed: Int,
    val perEntry: List<EntrySyncResult>,
    val overallError: String? = null
)

data class EntrySyncResult(
    val clientUuid: String,
    val displayName: String,
    val success: Boolean,
    val serverId: Long? = null,
    val error: String? = null,
    val errorCode: String? = null
)
