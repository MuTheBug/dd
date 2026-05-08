package com.haqquna.app.ui.imp

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.FileUpload
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.navigation.NavController
import com.haqquna.app.AppContainer
import com.haqquna.app.data.Diagnostics
import com.haqquna.app.data.EntryStatus
import com.haqquna.app.data.ImportError
import com.haqquna.app.data.ImportSummary
import com.haqquna.app.ui.BannerLevel
import com.haqquna.app.ui.HaqqunaTopBar
import com.haqquna.app.ui.SectionCard
import com.haqquna.app.ui.StatusBanner
import kotlinx.coroutines.launch

@Composable
fun ImportScreen(container: AppContainer, nav: NavController) {
    val scope = rememberCoroutineScope()

    var summary by remember { mutableStateOf<ImportSummary?>(null) }
    var loading by remember { mutableStateOf(false) }
    var fatalError by remember { mutableStateOf<String?>(null) }
    var importedCount by remember { mutableStateOf<Int?>(null) }
    var showConfirm by remember { mutableStateOf(false) }

    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri ->
        if (uri != null) {
            loading = true
            fatalError = null
            summary = null
            importedCount = null
            scope.launch {
                val existing = container.entries.existingUuids()
                val result = container.importer.parse(uri, existing)
                result.onSuccess { sum ->
                    summary = sum
                    Diagnostics.info("قراءة ملف الاستيراد: ${sum.total} سجل، ${sum.valid} صالح، ${sum.duplicates} مكرر، ${sum.invalid} غير صالح")
                }.onFailure { e ->
                    fatalError = e.message ?: "فشل غير معروف"
                    Diagnostics.error("فشل قراءة ملف الاستيراد: ${e.message}")
                }
                loading = false
            }
        }
    }

    Scaffold(
        topBar = { HaqqunaTopBar(title = "استيراد من JSON", onBack = { nav.popBackStack() }) }
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(vertical = 12.dp)
        ) {
            item {
                SectionCard(title = "اختر ملف نسخة احتياطية", icon = Icons.Default.FileUpload) {
                    Text(
                        "اختر ملف JSON تم تصديره من تطبيق حقنا (هذا التطبيق أو النسخة على المتصفح). " +
                                "سيتم التحقق من كل حالة ثم عرض ملخص قبل الإضافة الفعلية.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(Modifier.height(12.dp))
                    Button(
                        modifier = Modifier.fillMaxWidth(),
                        onClick = { launcher.launch(arrayOf("application/json", "text/plain", "*/*")) },
                        enabled = !loading
                    ) {
                        Icon(Icons.Default.FileUpload, null); Spacer(Modifier.width(8.dp))
                        Text(if (loading) "جاري التحليل..." else "اختيار ملف JSON")
                    }
                }
            }

            fatalError?.let {
                item { StatusBanner("فشل قراءة الملف: $it", BannerLevel.ERROR) }
            }

            importedCount?.let {
                item { StatusBanner("تم استيراد $it حالة بنجاح", BannerLevel.SUCCESS) }
            }

            summary?.let { sum ->
                item { SummaryCard(sum) }

                if (sum.valid > 0) {
                    item {
                        Button(
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp),
                            onClick = { showConfirm = true }
                        ) {
                            Text("استيراد ${sum.valid} حالة")
                        }
                    }
                }

                if (sum.errors.isNotEmpty()) {
                    item {
                        SectionCard(title = "تفاصيل الأخطاء (${sum.errors.size})", icon = Icons.Default.Warning) {
                            Text(
                                "هذه الحالات لن يتم استيرادها. راجعها يدوياً في ملف JSON إن أردت إصلاحها.",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                    items(sum.errors, key = { "${it.index}-${it.errorCode}" }) {
                        ErrorRow(it)
                    }
                }

                if (sum.valid > 0) {
                    item {
                        SectionCard(title = "الحالات الصالحة (${sum.valid})", icon = Icons.Default.CheckCircle) {
                            sum.validEntries.take(20).forEach { e ->
                                Text("• ${e.displayName}", style = MaterialTheme.typography.bodySmall)
                            }
                            if (sum.validEntries.size > 20) {
                                Text(
                                    "...و ${sum.validEntries.size - 20} حالة أخرى",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    }
                }
            }

            item { Spacer(Modifier.height(40.dp)) }
        }
    }

    if (showConfirm && summary != null) {
        val sum = summary!!
        AlertDialog(
            onDismissRequest = { showConfirm = false },
            title = { Text("تأكيد الاستيراد") },
            text = {
                Column {
                    Text("سيتم إضافة ${sum.valid} حالة جديدة إلى هذا الجهاز.")
                    if (sum.duplicates > 0) Text("• ستُتخطّى ${sum.duplicates} حالة موجودة مسبقاً")
                    if (sum.invalid > 0) Text("• ستُتخطّى ${sum.invalid} حالة غير صالحة")
                    Spacer(Modifier.height(6.dp))
                    Text("الحالات المستوردة ستكون بحالة \"بانتظار المزامنة\" حتى تقوم بتشغيل المزامنة.")
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    showConfirm = false
                    scope.launch {
                        val toImport = sum.validEntries.map { it.copy(syncStatus = EntryStatus.PENDING) }
                        container.entries.saveMany(toImport)
                        importedCount = toImport.size
                        summary = null
                        Diagnostics.ok("تمّ استيراد ${toImport.size} حالة")
                    }
                }) { Text("استيراد") }
            },
            dismissButton = { TextButton(onClick = { showConfirm = false }) { Text("إلغاء") } }
        )
    }
}

@Composable
private fun SummaryCard(sum: ImportSummary) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp),
        shape = MaterialTheme.shapes.medium,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)
    ) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
            Text("ملخّص الملف", fontWeight = FontWeight.Bold, color = MaterialTheme.colorScheme.onPrimaryContainer)
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.SpaceAround, modifier = Modifier.fillMaxWidth()) {
                Stat("الإجمالي", sum.total, MaterialTheme.colorScheme.onPrimaryContainer)
                Stat("صالحة", sum.valid, MaterialTheme.colorScheme.secondary)
                Stat("مكررة", sum.duplicates, MaterialTheme.colorScheme.tertiary)
                Stat("غير صالحة", sum.invalid, MaterialTheme.colorScheme.error)
            }
        }
    }
}

@Composable
private fun Stat(label: String, value: Int, color: androidx.compose.ui.graphics.Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value.toString(), color = color, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.titleLarge)
        Text(label, style = MaterialTheme.typography.labelSmall, color = color)
    }
}

@Composable
private fun ErrorRow(e: ImportError) {
    val isDup = e.errorCode == "duplicate" || e.errorCode == "duplicate_in_file"
    Card(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 3.dp),
        shape = MaterialTheme.shapes.small,
        colors = CardDefaults.cardColors(
            containerColor = if (isDup) MaterialTheme.colorScheme.tertiaryContainer
            else MaterialTheme.colorScheme.errorContainer
        )
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Icon(
                if (isDup) Icons.Default.Warning else Icons.Default.Error,
                null,
                tint = if (isDup) MaterialTheme.colorScheme.onTertiaryContainer
                else MaterialTheme.colorScheme.onErrorContainer
            )
            Spacer(Modifier.width(8.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    "#${e.index + 1} — ${e.name}",
                    fontWeight = FontWeight.Medium,
                    color = if (isDup) MaterialTheme.colorScheme.onTertiaryContainer
                    else MaterialTheme.colorScheme.onErrorContainer
                )
                Text(
                    e.message + suggestionFor(e.errorCode),
                    style = MaterialTheme.typography.bodySmall,
                    color = if (isDup) MaterialTheme.colorScheme.onTertiaryContainer
                    else MaterialTheme.colorScheme.onErrorContainer
                )
            }
        }
    }
}

private fun suggestionFor(code: String): String = when (code) {
    "missing_uuid" -> " — أضف \"client_uuid\" للسجل (مثلاً UUID v4)."
    "missing_fields" -> " — أضف كائن \"fields\" يحتوي بيانات الحالة."
    "missing_name" -> " — أضف على الأقل أحد: \"first_name\" أو \"last_name\"."
    "duplicate" -> " — هذه الحالة موجودة على الجهاز مسبقاً، تخطّ إذا لم ترد دمجها."
    "duplicate_in_file" -> " — هذه الحالة مكررة داخل الملف نفسه."
    else -> ""
}
