package com.haqquna.app.ui.settings

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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.FileDownload
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Save
import androidx.compose.material.icons.filled.Storage
import androidx.compose.material.icons.filled.Wifi
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.haqquna.app.AppContainer
import com.haqquna.app.data.Diagnostics
import com.haqquna.app.data.SyncRepository
import com.haqquna.app.ui.BannerLevel
import com.haqquna.app.ui.HaqqunaTopBar
import com.haqquna.app.ui.SectionCard
import com.haqquna.app.ui.StatusBanner
import com.haqquna.app.ui.TextFieldRow
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun SettingsScreen(container: AppContainer, nav: NavController) {
    val scope = rememberCoroutineScope()
    val ctx = LocalContext.current

    val server by container.settings.server.collectAsStateWithLifecycle(initialValue = "")
    val username by container.settings.username.collectAsStateWithLifecycle(initialValue = "")
    val password by container.settings.password.collectAsStateWithLifecycle(initialValue = "")
    val collector by container.settings.collector.collectAsStateWithLifecycle(initialValue = "")

    var serverField by remember { mutableStateOf("") }
    var userField by remember { mutableStateOf("") }
    var passField by remember { mutableStateOf("") }
    var collectorField by remember { mutableStateOf("") }

    LaunchedEffect(server, username, password, collector) {
        if (serverField.isEmpty()) serverField = server
        if (userField.isEmpty()) userField = username
        if (passField.isEmpty()) passField = password
        if (collectorField.isEmpty()) collectorField = collector
    }

    var testing by remember { mutableStateOf(false) }
    var testResult by remember { mutableStateOf<TestResult?>(null) }
    val entries by container.entries.observeAll().collectAsStateWithLifecycle(initialValue = emptyList())

    val exportLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.CreateDocument("application/json")
    ) { uri ->
        if (uri != null) scope.launch {
            val result = container.exporter.writeTo(uri, entries)
            result.onSuccess {
                Diagnostics.ok("تم تصدير $it حالة")
            }.onFailure {
                Diagnostics.error("فشل التصدير: ${it.message}")
            }
        }
    }

    Scaffold(
        topBar = { HaqqunaTopBar(title = "الإعدادات", onBack = { nav.popBackStack() }) }
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(vertical = 12.dp)
        ) {
            item {
                SectionCard(title = "عنوان السرفر", subtitle = "بصيغة http://192.168.1.100:5000", icon = Icons.Default.Wifi) {
                    TextFieldRow(label = "العنوان", value = serverField, onValueChange = { serverField = it })
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(
                            modifier = Modifier.weight(1f),
                            onClick = {
                                scope.launch {
                                    container.settings.setServer(serverField)
                                    Diagnostics.ok("تم حفظ عنوان السرفر")
                                }
                            }
                        ) {
                            Icon(Icons.Default.Save, null); Spacer(Modifier.width(6.dp)); Text("حفظ")
                        }
                        OutlinedButton(
                            modifier = Modifier.weight(1f),
                            onClick = {
                                scope.launch {
                                    testing = true
                                    testResult = null
                                    val outcome = container.sync.ping(com.haqquna.app.data.SettingsStore.normalizeUrl(serverField))
                                    testResult = when (outcome) {
                                        is SyncRepository.PingOutcome.Ok -> TestResult.Ok("الاتصال بالسرفر ناجح")
                                        is SyncRepository.PingOutcome.Failed -> TestResult.Fail(outcome.message)
                                    }
                                    testing = false
                                }
                            },
                            enabled = !testing
                        ) {
                            Icon(Icons.Default.Refresh, null); Spacer(Modifier.width(6.dp))
                            Text(if (testing) "..." else "اختبار")
                        }
                    }
                    val tr = testResult
                    if (tr != null) {
                        Spacer(Modifier.height(6.dp))
                        StatusBanner(
                            message = tr.message,
                            level = if (tr is TestResult.Ok) BannerLevel.SUCCESS else BannerLevel.ERROR
                        )
                    }
                }
            }
            item {
                SectionCard(title = "بيانات الدخول للمزامنة", icon = Icons.Default.Lock) {
                    TextFieldRow(label = "اسم المستخدم", value = userField, onValueChange = { userField = it })
                    TextFieldRow(
                        label = "كلمة المرور",
                        value = passField,
                        onValueChange = { passField = it },
                        keyboardType = androidx.compose.ui.text.input.KeyboardType.Password
                    )
                    Button(
                        modifier = Modifier.fillMaxWidth(),
                        onClick = {
                            scope.launch {
                                container.settings.setCredentials(userField, passField)
                                Diagnostics.ok("تم حفظ بيانات الدخول")
                            }
                        }
                    ) { Text("حفظ بيانات الدخول") }
                }
            }
            item {
                SectionCard(title = "الموظف/المتطوع", subtitle = "يُحفظ مع كل حالة جديدة", icon = Icons.Default.Person) {
                    TextFieldRow(label = "اسم الموظف", value = collectorField, onValueChange = { collectorField = it })
                    Button(
                        modifier = Modifier.fillMaxWidth(),
                        onClick = {
                            scope.launch {
                                container.settings.setCollector(collectorField)
                                Diagnostics.ok("تم حفظ اسم الموظف")
                            }
                        }
                    ) { Text("حفظ") }
                }
            }
            item {
                SectionCard(title = "النسخ الاحتياطي", icon = Icons.Default.Storage) {
                    OutlinedButton(
                        modifier = Modifier.fillMaxWidth(),
                        onClick = { exportLauncher.launch(container.exporter.defaultFilename()) }
                    ) {
                        Icon(Icons.Default.FileDownload, null); Spacer(Modifier.width(6.dp))
                        Text("تصدير نسخة احتياطية (JSON)")
                    }
                    Spacer(Modifier.height(6.dp))
                    Text(
                        "عدد الحالات الكلي على الجهاز: ${entries.size}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            item {
                DiagnosticPanel()
            }
            item { Spacer(Modifier.height(40.dp)) }
        }
    }
}

private sealed interface TestResult {
    val message: String
    data class Ok(override val message: String) : TestResult
    data class Fail(override val message: String) : TestResult
}

@Composable
private fun DiagnosticPanel() {
    val log by Diagnostics.entries.collectAsStateWithLifecycle()
    SectionCard(title = "سجلّ الأحداث") {
        if (log.isEmpty()) {
            Text("لا توجد أحداث بعد.", color = MaterialTheme.colorScheme.onSurfaceVariant)
        } else {
            val recent = log.takeLast(40).reversed()
            Column {
                recent.forEachIndexed { i, e ->
                    if (i > 0) HorizontalDivider()
                    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.Top) {
                        val (icon, color) = when (e.level) {
                            com.haqquna.app.data.DiagnosticEntry.Level.OK -> Icons.Default.CheckCircle to MaterialTheme.colorScheme.secondary
                            com.haqquna.app.data.DiagnosticEntry.Level.ERROR -> Icons.Default.Error to MaterialTheme.colorScheme.error
                            com.haqquna.app.data.DiagnosticEntry.Level.WARN -> Icons.Default.Error to MaterialTheme.colorScheme.tertiary
                            else -> Icons.Default.CheckCircle to MaterialTheme.colorScheme.outline
                        }
                        Icon(icon, null, tint = color, modifier = Modifier.height(18.dp))
                        Spacer(Modifier.width(6.dp))
                        Column(Modifier.weight(1f)) {
                            Text(e.message, style = MaterialTheme.typography.bodySmall)
                            Text(
                                SimpleDateFormat("HH:mm:ss", Locale.ENGLISH).format(Date(e.timestamp)),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.outline
                            )
                        }
                    }
                }
            }
        }
    }
}
