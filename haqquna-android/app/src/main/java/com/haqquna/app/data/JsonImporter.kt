package com.haqquna.app.data

import android.content.Context
import android.net.Uri
import com.google.gson.JsonArray
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.io.BufferedReader

class JsonImporter(private val ctx: Context) {

    suspend fun parse(uri: Uri, existingUuids: Set<String>): Result<ImportSummary> = runCatching {
        val text = ctx.contentResolver.openInputStream(uri)?.use {
            it.bufferedReader(Charsets.UTF_8).use(BufferedReader::readText)
        } ?: throw IllegalStateException("تعذّر فتح الملف")

        if (text.isBlank()) throw IllegalStateException("الملف فارغ")
        if (text.length > 200 * 1024 * 1024) throw IllegalStateException("الملف كبير جداً (الحد الأقصى 200MB)")

        val root = try {
            JsonParser.parseString(text)
        } catch (e: Exception) {
            throw IllegalStateException("الملف ليس JSON صالحاً: ${e.message ?: "خطأ في التحليل"}")
        }

        if (!root.isJsonArray) throw IllegalStateException(
            "صيغة الملف غير صحيحة — يجب أن يحتوي على مصفوفة من الحالات. " +
                    "استخدم ملف تم تصديره من ميزة \"تصدير نسخة احتياطية\"."
        )

        val arr = root.asJsonArray
        val total = arr.size()
        if (total == 0) {
            return@runCatching ImportSummary(0, 0, 0, 0, emptyList(), emptyList())
        }

        val errors = mutableListOf<ImportError>()
        val valid = mutableListOf<HaqqunaEntry>()
        val seenInFile = mutableSetOf<String>()

        for (i in 0 until total) {
            val node = arr[i]
            if (!node.isJsonObject) {
                errors += ImportError(i, "حالة #${i + 1}", "not_object", "السجل #${i + 1} ليس كائناً")
                continue
            }
            val obj = node.asJsonObject
            val label = nameFromObject(obj, i)

            val uuid = obj.get("client_uuid")?.takeIf { !it.isJsonNull }?.asString?.trim()
            if (uuid.isNullOrBlank()) {
                errors += ImportError(i, label, "missing_uuid", "معرّف الحالة (client_uuid) مفقود")
                continue
            }

            val fieldsNode = obj.get("fields")
            if (fieldsNode == null || !fieldsNode.isJsonObject) {
                errors += ImportError(i, label, "missing_fields", "حقل البيانات (fields) مفقود أو غير صحيح")
                continue
            }
            val fields = fieldsNode.asJsonObject.toStringMap()

            val first = fields["first_name"]?.trim().orEmpty()
            val last = fields["last_name"]?.trim().orEmpty()
            if (first.isEmpty() && last.isEmpty()) {
                errors += ImportError(i, label, "missing_name", "الاسم الأول واسم العائلة مفقودان")
                continue
            }

            if (uuid in existingUuids) {
                errors += ImportError(i, label, "duplicate", "موجودة مسبقاً في الجهاز (نفس المعرّف)")
                continue
            }
            if (uuid in seenInFile) {
                errors += ImportError(i, label, "duplicate_in_file", "مكررة داخل نفس الملف")
                continue
            }
            seenInFile += uuid

            val companions = (obj.get("companions") as? JsonArray)?.let { parseCompanions(it) } ?: emptyList()
            val witnesses = (obj.get("witnesses") as? JsonArray)?.let { parseWitnesses(it) } ?: emptyList()
            val children = (obj.get("children") as? JsonArray)?.let { parseChildren(it) } ?: emptyList()

            val statusKey = obj.get("status")?.takeIf { !it.isJsonNull }?.asString ?: "PENDING"
            val syncStatus = runCatching { EntryStatus.valueOf(statusKey.uppercase()) }
                .getOrDefault(EntryStatus.PENDING)

            valid += HaqqunaEntry(
                clientUuid = uuid,
                createdAt = obj.get("created_at")?.takeIf { !it.isJsonNull }?.asLong
                    ?: System.currentTimeMillis(),
                updatedAt = System.currentTimeMillis(),
                syncStatus = syncStatus,
                serverId = obj.get("server_id")?.takeIf { !it.isJsonNull }?.asLong,
                fields = fields,
                companions = companions,
                witnesses = witnesses,
                children = children
            )
        }

        ImportSummary(
            total = total,
            valid = valid.size,
            duplicates = errors.count { it.errorCode == "duplicate" || it.errorCode == "duplicate_in_file" },
            invalid = errors.size - errors.count { it.errorCode == "duplicate" || it.errorCode == "duplicate_in_file" },
            errors = errors,
            validEntries = valid
        )
    }

    private fun nameFromObject(obj: JsonObject, i: Int): String {
        obj.get("display_name")?.takeIf { !it.isJsonNull }?.asString?.takeIf { it.isNotBlank() }?.let { return it }
        val fieldsNode = obj.get("fields") as? JsonObject ?: return "حالة #${i + 1}"
        val parts = listOfNotNull(
            fieldsNode.get("first_name")?.takeIf { !it.isJsonNull }?.asString,
            fieldsNode.get("father_name")?.takeIf { !it.isJsonNull }?.asString,
            fieldsNode.get("last_name")?.takeIf { !it.isJsonNull }?.asString
        ).filter { it.isNotBlank() }
        return if (parts.isEmpty()) "حالة #${i + 1}" else parts.joinToString(" ")
    }

    private fun JsonObject.toStringMap(): Map<String, String> = entrySet().associate { (k, v) ->
        k to (if (v.isJsonNull) "" else if (v.isJsonPrimitive) v.asString else v.toString())
    }

    private fun parseCompanions(arr: JsonArray): List<Companion_> = arr.mapNotNull { el ->
        (el as? JsonObject)?.let {
            Companion_(
                name = it.str("name"),
                relation = it.str("relation"),
                nationalId = it.str("national_id"),
                phone = it.str("phone"),
                notes = it.str("notes")
            )
        }
    }

    private fun parseWitnesses(arr: JsonArray): List<Witness> = arr.mapNotNull { el ->
        (el as? JsonObject)?.let {
            Witness(
                name = it.str("name"),
                relation = it.str("relation"),
                phone = it.str("phone"),
                statement = it.str("statement")
            )
        }
    }

    private fun parseChildren(arr: JsonArray): List<Child> = arr.mapNotNull { el ->
        (el as? JsonObject)?.let {
            Child(
                name = it.str("name"),
                gender = it.str("gender"),
                birthYear = it.str("birth_year"),
                notes = it.str("notes")
            )
        }
    }

    private fun JsonObject.str(key: String): String =
        get(key)?.takeIf { !it.isJsonNull && it.isJsonPrimitive }?.asString.orEmpty()
}
