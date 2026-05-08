package com.haqquna.app.data

import android.content.Context
import android.net.Uri
import androidx.core.content.FileProvider
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class PhotoStore(private val ctx: Context) {

    private val baseDir: File = File(ctx.filesDir, "attachments").apply { if (!exists()) mkdirs() }

    fun newCameraTarget(field: String): CameraTarget {
        val name = "${field}_${stamp()}.jpg"
        val file = File(baseDir, name)
        val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.fileprovider", file)
        return CameraTarget(file = file, uri = uri)
    }

    fun importFromUri(uri: Uri, field: String, suggestedExt: String?): FileAttachment? {
        val ext = suggestedExt?.takeIf { it.isNotBlank() } ?: guessExt(uri)
        val targetFile = File(baseDir, "${field}_${stamp()}.$ext")
        ctx.contentResolver.openInputStream(uri)?.use { input ->
            targetFile.outputStream().use { input.copyTo(it) }
        } ?: return null

        val mime = ctx.contentResolver.getType(uri) ?: when (ext.lowercase()) {
            "jpg", "jpeg" -> "image/jpeg"
            "png" -> "image/png"
            "pdf" -> "application/pdf"
            else -> "application/octet-stream"
        }
        return FileAttachment(
            field = field,
            localPath = targetFile.absolutePath,
            mime = mime,
            displayName = targetFile.name
        )
    }

    fun delete(att: FileAttachment) {
        runCatching { File(att.localPath).delete() }
    }

    private fun stamp(): String =
        SimpleDateFormat("yyyyMMdd_HHmmss_SSS", Locale.ENGLISH).format(Date())

    private fun guessExt(uri: Uri): String {
        val type = ctx.contentResolver.getType(uri).orEmpty().lowercase()
        return when {
            "jpeg" in type || "jpg" in type -> "jpg"
            "png" in type -> "png"
            "pdf" in type -> "pdf"
            else -> uri.path?.substringAfterLast('.', "bin") ?: "bin"
        }
    }

    data class CameraTarget(val file: File, val uri: Uri)
}
