package com.haqquna.app.ui.sync

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
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
import androidx.compose.material.icons.filled.CloudUpload
import androidx.compose.material.icons.filled.DeleteSweep
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.haqquna.app.AppContainer
import com.haqquna.app.data.Diagnostics
import com.haqquna.app.data.EntrySyncResult
import com.haqquna.app.data.EntryStatus
import com.haqquna.app.data.SettingsStore
import com.haqquna.app.data.SyncRepository
import com.haqquna.app.ui.BannerLevel
import com.haqquna.app.ui.HaqqunaTopBar
import com.haqquna.app.ui.SectionCard
import com.haqquna.app.ui.StatusBanner
import kotlinx.coroutines.launch

@Composable
fun SyncScreen(container: AppContainer, nav: NavController) {
    val scope = rememberCoroutineScope()

    val server by container.settings.server.collectAsStateWithLifecycle(initialValue = "")
    val username by container.settings.username.collectAsStateWithLifecycle(initialValue = "")
    val password by container.settings.password.collectAsStateWithLifecycle(initialValue = "")
    val pendingCount by container.entries.countPending().collectAsStateWithLifecycle(initialValue = 0)
    val failedCount by container.entries.countFailed().collectAsStateWithLifecycle(initialValue = 0)
    val syncedCount by container.entries.countSynced().collectAsStateWithLifecycle(initialValue = 0)

    var inProgress by remember { mutableStateOf(false) }
    var current by remember { mutableIntStateOf(0) }
    var total by remember { mutableIntStateOf(0) }
    var results by remember { mutableStateOf<List<EntrySyncResult>>(emptyList()) }
    var bannerMsg by remember { mutableStateOf<Pair<String, BannerLevel>?>(null) }
    var showClearDialog by remember { mutableStateOf(false) }

    Scaffold(
        topBar = { HaqqunaTopBar(title = "المزامنة", onBack = { nav.popBackStack() }) }
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(vertical = 12.dp)
        ) {
            item {
                SummaryCard(
                    server = server,
                    pending = pendingCount,
                    failed = failedCount,
                    synced = syncedCount
                )
            }
            bannerMsg?.let {
                item { StatusBanner(it.first, it.second) }
            }

            item {
                SectionCard(title = "إجراءات", icon = Icons.Default.Sync) {
                    val canSync = !inProgress && (pendingCount + failedCount) > 0
                    Button(
                        modifier = Modifier.fillMaxWidth(),
                        enabled = canSync,
                        onClick = {
                            scope.launch {
                                if (username.isBlank() || password.isBlank()) {
                                    bannerMsg = "يجب إدخال بيانات الدخول من الإعدادات أولاً" to BannerLevel.WARNING
                                    return@launch
                                }
                                bannerMsg = null
                                results = emptyList()
                                inProgress = true
                                current = 0

                                Diagnostics.info("بدء المزامنة...")
                                val pingOutcome = container.sync.ping(SettingsStore.normalizeUrl(server))
                                if (pingOutcome is SyncRepository.PingOutcome.Failed) {
                                    bannerMsg = "تعذّر الوصول للسرفر: ${pingOutcome.message}" to BannerLevel.ERROR
                                    Diagnostics.error("فشل الاتصال بالسرفر: ${pingOutcome.message}")
                                    inProgress = false
                                    return@launch
                                }

                                val login = container.sync.login(SettingsStore.normalizeUrl(server), username, password)
                                if (login is SyncRepository.LoginOutcome.Failed) {
                                    bannerMsg = login.message to BannerLevel.ERROR
                                    Diagnostics.error("فشل تسجيل الدخول: ${login.message}")
                                    inProgress = false
                                    return@launch
                                }

                                val pending = container.entries.pending()
                                total = pending.size
                                if (total == 0) {
                                    bannerMsg = "لا توجد حالات بانتظار المزامنة" to BannerLevel.INFO
                                    inProgress = false
                                    return@launch
                                }

                                val perEntry = mutableListOf<EntrySyncResult>()
                                for ((idx, entry) in pending.withIndex()) {
                                    current = idx + 1
                                    container.entries.markSyncing(entry.clientUuid)
                                    val r = container.sync.submitEntry(
                                        SettingsStore.normalizeUrl(server), username, password, entry
                                    )
                                    perEntry += r
                                    if (r.success) {
                                        container.entries.markSynced(entry.clientUuid, r.serverId)
                                        Diagnostics.ok("تمّت مزامنة ${entry.displayName}")
                                    } else {
                                        container.entries.markFailed(entry.clientUuid, r.error ?: "خطأ غير معروف")
                                        Diagnostics.error("فشل ${entry.displayName}: ${r.error}")
                                    }
                                    results = perEntry.toList()
                                }

                                val ok = perEntry.count { it.success }
                                val fail = perEntry.size - ok
                                bannerMsg = if (fail == 0)
                                    "اكتملت المزامنة: $ok حالة" to BannerLevel.SUCCESS
                                else
                                    "اكتملت المزامنة: نجح $ok وفشل $fail" to BannerLevel.WARNING

                                inProgress = false
                            }
                        }
                    ) {
                        Icon(Icons.Default.CloudUpload, null); Spacer(Modifier.width(8.dp))
                        Text(if (inProgress) "جاري المزامنة..." else "بدء المزامنة (${pendingCount + failedCount})")
                    }
                    if (inProgress && total > 0) {
                        Spacer(Modifier.height(12.dp))
                        LinearProgressIndicator(
                            progress = { current.toFloat() / total },
                            modifier = Modifier.fillMaxWidth()
                        )
                        Text(
                            "$current / $total",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                    Spacer(Modifier.height(8.dp))
                    OutlinedButton(
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !inProgress && syncedCount > 0,
                        onClick = { showClearDialog = true }
                    ) {
                        Icon(Icons.Default.DeleteSweep, null); Spacer(Modifier.width(6.dp))
                        Text("حذف الحالات المتزامنة من الجهاز ($syncedCount)")
                    }
                }
            }

            if (results.isNotEmpty()) {
                item {
                    SectionCard(title = "نتائج آخر مزامنة") {
                        val ok = results.count { it.success }
                        val fail = results.size - ok
                        Text("نجحت: $ok • فشلت: $fail", style = MaterialTheme.typography.bodyMedium)
                    }
                }
                items(results, key = { it.clientUuid }) { r ->
                    ResultRow(r)
                }
            }
            item { Spacer(Modifier.height(40.dp)) }
        }
    }

    if (showClearDialog) {
        AlertDialog(
            onDismissRequest = { showClearDialog = false },
            title = { Text("حذف الحالات المتزامنة؟") },
            text = { Text("سيتم حذف $syncedCount حالة من هذا الجهاز فقط. البيانات على السرفر لن تتأثر.") },
            confirmButton = {
                TextButton(onClick = {
                    showClearDialog = false
                    scope.launch {
                        val n = container.entries.deleteSynced()
                        bannerMsg = "تم حذف $n حالة من الجهاز" to BannerLevel.SUCCESS
                        Diagnostics.ok("حذف $n حالة متزامنة من الجهاز")
                    }
                }) { Text("حذف", color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = {
                TextButton(onClick = { showClearDialog = false }) { Text("إلغاء") }
            }
        )
    }
}

@Composable
private fun SummaryCard(server: String, pending: Int, failed: Int, synced: Int) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp),
        shape = MaterialTheme.shapes.medium,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)
    ) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
            Text("السرفر", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onPrimaryContainer)
            Text(server, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium)
            Spacer(Modifier.height(12.dp))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceAround) {
                Stat(label = "بالانتظار", value = pending)
                Stat(label = "فشلت", value = failed)
                Stat(label = "متزامنة", value = synced)
            }
        }
    }
}

@Composable
private fun Stat(label: String, value: Int) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(value.toString(), style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Text(label, style = MaterialTheme.typography.labelSmall)
    }
}

@Composable
private fun ResultRow(r: EntrySyncResult) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
        shape = MaterialTheme.shapes.small,
        colors = CardDefaults.cardColors(
            containerColor = if (r.success)
                MaterialTheme.colorScheme.secondaryContainer
            else
                MaterialTheme.colorScheme.errorContainer
        )
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            val icon = if (r.success) Icons.Default.CheckCircle else Icons.Default.Error
            val color = if (r.success) MaterialTheme.colorScheme.onSecondaryContainer
            else MaterialTheme.colorScheme.onErrorContainer
            Icon(icon, null, tint = color)
            Spacer(Modifier.width(8.dp))
            Column(Modifier.weight(1f)) {
                Text(r.displayName, fontWeight = FontWeight.Medium, color = color)
                if (!r.success && r.error != null) Text(
                    r.error,
                    style = MaterialTheme.typography.bodySmall,
                    color = color
                )
                if (r.success && r.serverId != null) Text(
                    "رقم السرفر: ${r.serverId}",
                    style = MaterialTheme.typography.labelSmall,
                    color = color
                )
            }
        }
    }
}
