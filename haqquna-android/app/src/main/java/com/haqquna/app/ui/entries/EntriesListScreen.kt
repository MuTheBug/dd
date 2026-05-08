package com.haqquna.app.ui.entries

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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Error
import androidx.compose.material.icons.filled.HourglassEmpty
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.haqquna.app.AppContainer
import com.haqquna.app.data.EntryStatus
import com.haqquna.app.data.HaqqunaEntry
import com.haqquna.app.ui.HaqqunaTopBar
import com.haqquna.app.ui.Routes
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun EntriesListScreen(container: AppContainer, nav: NavController) {
    val entries by container.entries.observeAll().collectAsStateWithLifecycle(initialValue = emptyList())
    val scope = rememberCoroutineScope()
    var pendingDelete by remember { mutableStateOf<HaqqunaEntry?>(null) }

    Scaffold(
        topBar = { HaqqunaTopBar(title = "الحالات المحفوظة", onBack = { nav.popBackStack() }) },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { nav.navigate(Routes.ENTRY_NEW) },
                containerColor = MaterialTheme.colorScheme.primary,
                contentColor = MaterialTheme.colorScheme.onPrimary
            ) {
                Icon(Icons.Default.Add, null)
                Spacer(Modifier.width(8.dp))
                Text("جديدة")
            }
        }
    ) { padding ->
        if (entries.isEmpty()) {
            EmptyState(modifier = Modifier.fillMaxSize().padding(padding))
        } else {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(vertical = 8.dp, horizontal = 0.dp),
                verticalArrangement = Arrangement.spacedBy(0.dp)
            ) {
                items(entries, key = { it.clientUuid }) { entry ->
                    EntryRow(
                        entry = entry,
                        onClick = { nav.navigate(Routes.entryEdit(entry.clientUuid)) },
                        onDelete = { pendingDelete = entry }
                    )
                }
                item { Spacer(Modifier.height(80.dp)) }
            }
        }
    }

    if (pendingDelete != null) {
        val entry = pendingDelete!!
        AlertDialog(
            onDismissRequest = { pendingDelete = null },
            title = { Text("حذف الحالة؟") },
            text = {
                Text(
                    "سيتم حذف \"${entry.displayName}\" من هذا الجهاز فقط. " +
                            (if (entry.syncStatus == EntryStatus.SYNCED) "تم رفعها للسرفر مسبقاً." else "لم تتم مزامنتها بعد.")
                )
            },
            confirmButton = {
                TextButton(onClick = {
                    val toDelete = entry.clientUuid
                    pendingDelete = null
                    scope.launch { container.entries.delete(toDelete) }
                }) { Text("حذف", color = MaterialTheme.colorScheme.error) }
            },
            dismissButton = { TextButton(onClick = { pendingDelete = null }) { Text("إلغاء") } }
        )
    }
}

@Composable
private fun EmptyState(modifier: Modifier) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(
            Icons.Default.Description,
            null,
            tint = MaterialTheme.colorScheme.outline,
            modifier = Modifier.size(64.dp)
        )
        Spacer(Modifier.height(12.dp))
        Text("لا توجد حالات محفوظة بعد", style = MaterialTheme.typography.titleMedium)
        Text(
            "اضغط زر «جديدة» لإضافة أول حالة",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

@Composable
private fun EntryRow(entry: HaqqunaEntry, onClick: () -> Unit, onDelete: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
        shape = MaterialTheme.shapes.medium,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        onClick = onClick
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            StatusIcon(entry.syncStatus)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(entry.displayName, fontWeight = FontWeight.SemiBold, style = MaterialTheme.typography.titleMedium)
                Row {
                    val provo = entry.fields["province"]?.takeIf { it.isNotBlank() }
                    val statusAr = entry.statusEnum?.arabic
                    Text(
                        listOfNotNull(statusAr, provo).joinToString(" • ").ifBlank { "—" },
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                Text(
                    "آخر تعديل: ${formatDate(entry.updatedAt)}",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.outline
                )
                if (entry.syncError != null) {
                    Text(
                        "⚠ ${entry.syncError}",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.error
                    )
                }
            }
            IconButton(onClick = onDelete) {
                Icon(Icons.Default.Delete, "حذف", tint = MaterialTheme.colorScheme.error)
            }
        }
    }
}

@Composable
private fun StatusIcon(status: EntryStatus) {
    val (icon, color) = when (status) {
        EntryStatus.DRAFT -> Icons.Default.Description to MaterialTheme.colorScheme.outline
        EntryStatus.PENDING -> Icons.Default.HourglassEmpty to MaterialTheme.colorScheme.tertiary
        EntryStatus.SYNCING -> Icons.Default.Sync to MaterialTheme.colorScheme.primary
        EntryStatus.SYNCED -> Icons.Default.CheckCircle to MaterialTheme.colorScheme.secondary
        EntryStatus.FAILED -> Icons.Default.Error to MaterialTheme.colorScheme.error
    }
    Box(
        modifier = Modifier
            .size(40.dp)
            .padding(2.dp),
        contentAlignment = Alignment.Center
    ) {
        Icon(icon, null, tint = color, modifier = Modifier.size(28.dp))
    }
}

private fun formatDate(ms: Long): String {
    return SimpleDateFormat("yyyy-MM-dd HH:mm", Locale.ENGLISH).format(Date(ms))
}
