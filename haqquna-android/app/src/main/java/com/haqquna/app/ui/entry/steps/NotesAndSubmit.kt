package com.haqquna.app.ui.entry.steps

import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.NoteAlt
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.haqquna.app.ui.SectionCard
import com.haqquna.app.ui.TextFieldRow
import com.haqquna.app.ui.entry.EntryFormViewModel
import com.haqquna.app.ui.entry.FormState

@Composable
fun NotesAndSubmitStep(vm: EntryFormViewModel, state: FormState) {

    SectionCard(title = "ملاحظات إضافية", icon = Icons.Default.NoteAlt) {
        TextFieldRow(
            label = "ملاحظات",
            value = state.fields["notes"] ?: "",
            onValueChange = { vm.setField("notes", it) },
            singleLine = false,
            maxLines = 8
        )
        TextFieldRow(
            label = "تفاصيل قانونية",
            value = state.fields["legal_details"] ?: "",
            onValueChange = { vm.setField("legal_details", it) },
            singleLine = false,
            maxLines = 4
        )
        TextFieldRow(
            label = "اسم الجمعية المتابِعة (إن وُجدت)",
            value = state.fields["assoc_name"] ?: "",
            onValueChange = { vm.setField("assoc_name", it) }
        )
    }

    SectionCard(title = "ملخص قبل الحفظ", icon = Icons.Default.CheckCircle) {
        SummaryRow("الاسم", listOf(
            state.fields["first_name"], state.fields["father_name"], state.fields["last_name"]
        ).filterNot { it.isNullOrBlank() }.joinToString(" "))
        SummaryRow("الحالة", state.fields["status"])
        SummaryRow("المحافظة", state.fields["province"])
        SummaryRow("الرقم الوطني", state.fields["national_id"])
        SummaryRow("المُبلِّغ", state.fields["reporter_name"])
        SummaryRow("عدد المرافقين", state.companions.count { it.name.isNotBlank() }.toString())
        SummaryRow("عدد الشهود", state.witnesses.count { it.name.isNotBlank() }.toString())
        SummaryRow("عدد الأبناء", state.children.count { it.name.isNotBlank() }.toString())
        SummaryRow("الملفات المرفقة", state.attachments.size.toString())
        Spacer(Modifier.height(8.dp))
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)
        ) {
            Text(
                "اضغط زر «حفظ ومزامنة لاحقاً» أدناه لإكمال الحفظ. ستتم المزامنة لاحقاً عند الاتصال بالشبكة.",
                modifier = Modifier.padding(12.dp),
                color = MaterialTheme.colorScheme.onPrimaryContainer,
                style = MaterialTheme.typography.bodySmall
            )
        }
    }
}

@Composable
private fun SummaryRow(label: String, value: String?) {
    val v = value?.trim().orEmpty().ifBlank { "—" }
    androidx.compose.foundation.layout.Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp)
    ) {
        Text(label, fontWeight = FontWeight.Medium, modifier = Modifier.padding(end = 8.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(v, modifier = Modifier.weight(1f))
    }
}
