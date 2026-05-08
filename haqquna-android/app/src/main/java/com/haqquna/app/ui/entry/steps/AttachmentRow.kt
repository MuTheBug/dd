package com.haqquna.app.ui.entry.steps

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AttachFile
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Upload
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.haqquna.app.AppContainer
import com.haqquna.app.data.FileAttachment
import com.haqquna.app.ui.entry.EntryFormViewModel
import com.haqquna.app.ui.entry.FormState

@Composable
fun AttachmentRow(
    label: String,
    field: String,
    mime: String,
    state: FormState,
    container: AppContainer,
    vm: EntryFormViewModel,
    cameraSupported: Boolean = mime.startsWith("image")
) {
    val ctx = LocalContext.current
    val current = state.attachments.firstOrNull { it.field == field }
    val cameraTarget = remember { mutableStateOf<com.haqquna.app.data.PhotoStore.CameraTarget?>(null) }

    val pickerLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocument()
    ) { uri ->
        if (uri != null) {
            val att = container.photos.importFromUri(uri, field, null)
            if (att != null) vm.addAttachment(att)
        }
    }

    val cameraLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.TakePicture()
    ) { ok ->
        val target = cameraTarget.value
        if (ok && target != null) {
            val att = FileAttachment(
                field = field,
                localPath = target.file.absolutePath,
                mime = "image/jpeg",
                displayName = target.file.name
            )
            vm.addAttachment(att)
        }
        cameraTarget.value = null
    }

    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text(label, style = MaterialTheme.typography.labelLarge)
        Spacer(Modifier.height(4.dp))
        if (current != null) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Default.AttachFile, null, tint = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.width(6.dp))
                Text(
                    current.displayName,
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.bodySmall
                )
                IconButton(onClick = { vm.removeAttachment(field) }) {
                    Icon(Icons.Default.Delete, "حذف", tint = MaterialTheme.colorScheme.error)
                }
            }
        } else {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (cameraSupported) {
                    OutlinedButton(
                        modifier = Modifier.weight(1f),
                        onClick = {
                            val target = container.photos.newCameraTarget(field)
                            cameraTarget.value = target
                            cameraLauncher.launch(target.uri)
                        }
                    ) {
                        Icon(Icons.Default.CameraAlt, null); Spacer(Modifier.width(4.dp))
                        Text("كاميرا")
                    }
                }
                OutlinedButton(
                    modifier = Modifier.weight(1f),
                    onClick = { pickerLauncher.launch(arrayOf(mime)) }
                ) {
                    Icon(Icons.Default.Upload, null); Spacer(Modifier.width(4.dp))
                    Text("اختيار ملف")
                }
            }
        }
    }
}
