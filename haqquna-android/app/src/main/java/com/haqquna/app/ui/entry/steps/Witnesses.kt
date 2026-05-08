package com.haqquna.app.ui.entry.steps

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.RecordVoiceOver
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
import com.haqquna.app.ui.SectionCard
import com.haqquna.app.ui.TextFieldRow
import com.haqquna.app.ui.entry.EntryFormViewModel
import com.haqquna.app.ui.entry.FormState

@Composable
fun WitnessesStep(vm: EntryFormViewModel, state: FormState) {
    SectionCard(
        title = "الشهود",
        subtitle = "أشخاص شهدوا الحالة أو لديهم معلومة موثَّقة",
        icon = Icons.Default.RecordVoiceOver
    ) {
        OutlinedButton(modifier = Modifier.fillMaxWidth(), onClick = { vm.addWitness() }) {
            Icon(Icons.Default.Add, null); Spacer(Modifier.width(6.dp))
            Text("إضافة شاهد")
        }
    }
    state.witnesses.forEachIndexed { idx, w ->
        Card(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
            shape = MaterialTheme.shapes.medium,
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
        ) {
            androidx.compose.foundation.layout.Column(modifier = Modifier.padding(14.dp)) {
                Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text("شاهد #${idx + 1}", modifier = Modifier.weight(1f), fontWeight = FontWeight.SemiBold)
                    IconButton(onClick = { vm.removeWitness(idx) }) {
                        Icon(Icons.Default.Delete, "حذف", tint = MaterialTheme.colorScheme.error)
                    }
                }
                TextFieldRow(label = "الاسم", value = w.name, onValueChange = { vm.updateWitness(idx, w.copy(name = it)) })
                TextFieldRow(label = "الصلة بالحالة", value = w.relation, onValueChange = { vm.updateWitness(idx, w.copy(relation = it)) })
                TextFieldRow(
                    label = "رقم الهاتف",
                    value = w.phone,
                    onValueChange = { vm.updateWitness(idx, w.copy(phone = it)) },
                    keyboardType = androidx.compose.ui.text.input.KeyboardType.Phone
                )
                TextFieldRow(
                    label = "الشهادة/المعلومة",
                    value = w.statement,
                    onValueChange = { vm.updateWitness(idx, w.copy(statement = it)) },
                    singleLine = false,
                    maxLines = 5
                )
            }
        }
    }
}
