package com.haqquna.app.ui.entry.steps

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Group
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.haqquna.app.data.Companion_
import com.haqquna.app.ui.SectionCard
import com.haqquna.app.ui.TextFieldRow
import com.haqquna.app.ui.entry.EntryFormViewModel
import com.haqquna.app.ui.entry.FormState

@Composable
fun CompanionsStep(vm: EntryFormViewModel, state: FormState) {
    SectionCard(
        title = "المرافقون",
        subtitle = "أشخاص اعتُقلوا/فقدوا مع الشخص الموثَّق",
        icon = Icons.Default.Group
    ) {
        Text(
            "أضف الأشخاص الذين رافقوا الحالة في الاعتقال أو الاختفاء.",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Spacer(Modifier.height(8.dp))
        OutlinedButton(modifier = Modifier.fillMaxWidth(), onClick = { vm.addCompanion() }) {
            Icon(Icons.Default.Add, null); Spacer(Modifier.width(6.dp))
            Text("إضافة مرافق")
        }
    }
    state.companions.forEachIndexed { idx, c ->
        Card(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
            shape = MaterialTheme.shapes.medium,
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
        ) {
            androidx.compose.foundation.layout.Column(modifier = Modifier.padding(14.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        "مرافق #${idx + 1}",
                        modifier = Modifier.weight(1f),
                        fontWeight = FontWeight.SemiBold
                    )
                    IconButton(onClick = { vm.removeCompanion(idx) }) {
                        Icon(Icons.Default.Delete, "حذف", tint = MaterialTheme.colorScheme.error)
                    }
                }
                TextFieldRow(label = "الاسم", value = c.name, onValueChange = { vm.updateCompanion(idx, c.copy(name = it)) })
                TextFieldRow(label = "الصلة بالحالة", value = c.relation, onValueChange = { vm.updateCompanion(idx, c.copy(relation = it)) })
                TextFieldRow(
                    label = "الرقم الوطني",
                    value = c.nationalId,
                    onValueChange = { vm.updateCompanion(idx, c.copy(nationalId = it)) },
                    keyboardType = androidx.compose.ui.text.input.KeyboardType.Number
                )
                TextFieldRow(
                    label = "رقم الهاتف",
                    value = c.phone,
                    onValueChange = { vm.updateCompanion(idx, c.copy(phone = it)) },
                    keyboardType = androidx.compose.ui.text.input.KeyboardType.Phone
                )
                TextFieldRow(
                    label = "ملاحظات",
                    value = c.notes,
                    onValueChange = { vm.updateCompanion(idx, c.copy(notes = it)) },
                    singleLine = false,
                    maxLines = 3
                )
            }
        }
    }
}
