package com.haqquna.app.data

import android.content.Context
import android.net.Uri
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import retrofit2.HttpException
import java.io.File
import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException

class SyncRepository(
    private val ctx: Context,
    private val api: SyncApi = ApiClient.api,
    private val gson: com.google.gson.Gson = ApiClient.gson
) {

    suspend fun ping(serverBase: String): PingOutcome {
        val url = "${serverBase.trimEnd('/')}/api/sync/ping"
        return try {
            val resp = api.ping(url)
            if (resp.isSuccessful && resp.body()?.ok == true) PingOutcome.Ok
            else PingOutcome.Failed(httpErrorMessage(resp.code()))
        } catch (e: Exception) {
            PingOutcome.Failed(networkErrorMessage(e))
        }
    }

    suspend fun login(serverBase: String, user: String, pass: String): LoginOutcome {
        val url = "${serverBase.trimEnd('/')}/api/sync/login"
        if (user.isBlank() || pass.isBlank()) return LoginOutcome.Failed("اسم المستخدم وكلمة المرور مطلوبان")
        return try {
            val dummy = MultipartBody.Part.createFormData("noop", "1")
            val resp = api.login(url, user, pass, dummy)
            val body = resp.body()
            when {
                resp.isSuccessful && body?.success == true ->
                    LoginOutcome.Ok(displayName = body.displayName ?: user, role = body.role ?: "")
                resp.code() == 401 -> LoginOutcome.Failed("اسم المستخدم أو كلمة المرور غير صحيحة")
                resp.code() == 403 -> LoginOutcome.Failed("هذا الحساب لا يملك صلاحية المزامنة")
                else -> LoginOutcome.Failed(body?.error ?: httpErrorMessage(resp.code()))
            }
        } catch (e: Exception) {
            LoginOutcome.Failed(networkErrorMessage(e))
        }
    }

    suspend fun submitEntry(
        serverBase: String,
        user: String,
        pass: String,
        entry: HaqqunaEntry
    ): EntrySyncResult {
        val url = "${serverBase.trimEnd('/')}/api/sync/entries"

        val textParts = buildTextParts(entry)
        val fileParts = buildFileParts(entry)

        return try {
            val resp = api.submitEntry(url, user, pass, textParts, fileParts)
            val body = resp.body()
            when {
                resp.isSuccessful && body?.success == true -> EntrySyncResult(
                    clientUuid = entry.clientUuid,
                    displayName = entry.displayName,
                    success = true,
                    serverId = body.serverId
                )
                resp.code() == 401 -> EntrySyncResult(
                    clientUuid = entry.clientUuid,
                    displayName = entry.displayName,
                    success = false,
                    error = "بيانات الدخول غير صحيحة",
                    errorCode = "auth"
                )
                resp.code() == 403 -> EntrySyncResult(
                    clientUuid = entry.clientUuid,
                    displayName = entry.displayName,
                    success = false,
                    error = "الحساب لا يملك صلاحية المزامنة",
                    errorCode = "role"
                )
                resp.code() == 400 -> {
                    val msgs = body?.errors?.values?.joinToString("، ") ?: body?.error ?: "بيانات غير صالحة"
                    EntrySyncResult(
                        clientUuid = entry.clientUuid,
                        displayName = entry.displayName,
                        success = false,
                        error = "خطأ في البيانات: $msgs",
                        errorCode = "validation"
                    )
                }
                else -> EntrySyncResult(
                    clientUuid = entry.clientUuid,
                    displayName = entry.displayName,
                    success = false,
                    error = body?.error ?: httpErrorMessage(resp.code()),
                    errorCode = "http_${resp.code()}"
                )
            }
        } catch (e: Exception) {
            EntrySyncResult(
                clientUuid = entry.clientUuid,
                displayName = entry.displayName,
                success = false,
                error = networkErrorMessage(e),
                errorCode = "network"
            )
        }
    }

    private fun buildTextParts(entry: HaqqunaEntry): Map<String, RequestBody> {
        val plainText = "text/plain; charset=utf-8".toMediaType()
        val parts = mutableMapOf<String, RequestBody>()

        fun put(key: String, value: String) {
            if (value.isNotEmpty()) parts[key] = value.toRequestBody(plainText)
        }

        put("client_uuid", entry.clientUuid)
        entry.fields.forEach { (k, v) -> put(k, v) }

        if (entry.companions.isNotEmpty()) {
            put("companions_count", entry.companions.size.toString())
            entry.companions.forEachIndexed { i, c ->
                put("companion_name_$i", c.name)
                put("companion_relation_$i", c.relation)
                put("companion_national_id_$i", c.nationalId)
                put("companion_phone_$i", c.phone)
                put("companion_notes_$i", c.notes)
            }
        }

        if (entry.witnesses.isNotEmpty()) {
            put("witnesses_data", gson.toJson(entry.witnesses))
        }

        if (entry.children.isNotEmpty()) {
            put("children_data", gson.toJson(entry.children))
            put("has_kids", "yes")
            put("kids_count", entry.children.size.toString())
        }

        return parts
    }

    private fun buildFileParts(entry: HaqqunaEntry): List<MultipartBody.Part> {
        val parts = mutableListOf<MultipartBody.Part>()
        for (att in entry.attachments) {
            val file = File(att.localPath)
            if (!file.exists()) continue
            val media = (att.mime.takeIf { it.isNotBlank() } ?: "application/octet-stream").toMediaTypeOrNull()
            val body = file.asRequestBody(media)
            parts += MultipartBody.Part.createFormData(att.field, att.displayName, body)
        }
        return parts
    }

    private fun httpErrorMessage(code: Int): String = when (code) {
        400 -> "البيانات المرسلة غير صالحة"
        401 -> "بيانات الدخول غير صحيحة"
        403 -> "ليست لديك صلاحية"
        404 -> "نقطة الاتصال غير موجودة على السرفر — تأكد من العنوان"
        500 -> "خطأ في السرفر"
        502, 503, 504 -> "السرفر غير متاح حالياً"
        else -> "خطأ في الاتصال (HTTP $code)"
    }

    private fun networkErrorMessage(e: Exception): String = when (e) {
        is UnknownHostException -> "تعذّر الوصول للعنوان — تحقّق من اسم الخادم/الـIP"
        is ConnectException -> "السرفر مغلق أو غير متاح على هذا العنوان والمنفذ"
        is SocketTimeoutException -> "انتهت مهلة الاتصال — السرفر بطيء أو الشبكة ضعيفة"
        is HttpException -> "خطأ HTTP ${e.code()}"
        is IOException -> "خطأ في الشبكة: ${e.message ?: "غير معروف"}"
        else -> "خطأ غير متوقع: ${e.message ?: e.javaClass.simpleName}"
    }

    sealed interface PingOutcome {
        data object Ok : PingOutcome
        data class Failed(val message: String) : PingOutcome
    }

    sealed interface LoginOutcome {
        data class Ok(val displayName: String, val role: String) : LoginOutcome
        data class Failed(val message: String) : LoginOutcome
    }
}
