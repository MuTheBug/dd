package com.haqquna.app.ui.entry.steps

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Gavel
import androidx.compose.material.icons.filled.NoteAlt
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.haqquna.app.ui.DropdownRow
import com.haqquna.app.ui.SectionCard
import com.haqquna.app.ui.TextFieldRow
import com.haqquna.app.ui.entry.EntryFormViewModel
import com.haqquna.app.ui.entry.FormState

@Composable
fun NotesAndSubmitStep(vm: EntryFormViewModel, state: FormState) {

    SectionCard(title = "المشاكل القانونية والجمعيات", icon = Icons.Default.Gavel) {
        DropdownRow(
            label = "هل يوجد مشاكل قانونية؟",
            value = state.fields["legal"] ?: "",
            options = listOf("" to "-- اختر --", "نعم" to "نعم", "لا" to "لا"),
            onChange = { vm.setField("legal", it) }
        )
        if (state.fields["legal"] == "نعم") {
            TextFieldRow(
                label = "تفاصيل المشاكل القانونية",
                value = state.fields["legal_details"] ?: "",
                onValueChange = { vm.setField("legal_details", it) },
                singleLine = false,
                maxLines = 4
            )
        }
        DropdownRow(
            label = "مسجل لدى جمعية؟",
            value = state.fields["assoc"] ?: "",
            options = listOf("" to "-- اختر --", "نعم" to "نعم", "لا" to "لا"),
            onChange = { vm.setField("assoc", it) }
        )
        if (state.fields["assoc"] == "نعم") {
            TextFieldRow(
                label = "اسم الجمعية",
                value = state.fields["assoc_name"] ?: "",
                onValueChange = { vm.setField("assoc_name", it) }
            )
        }
        TextFieldRow(
            label = "نوع الخدمة المطلوبة",
            value = state.fields["service_type"] ?: "",
            onValueChange = { vm.setField("service_type", it) },
            placeholder = "توثيق، مساعدة قانونية، إلخ"
        )
        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            val checked = state.fields["is_officially_registered"] == "1"
            Checkbox(
                checked = checked,
                onCheckedChange = { vm.setField("is_officially_registered", if (it) "1" else "") }
            )
            Text("مسجل رسمياً لدى الجهات المعنية", modifier = Modifier.padding(start = 6.dp))
        }
    }

    SectionCard(title = "منهجية التوثيق", icon = Icons.Default.Description) {
        Text(
            "اختر الوسوم المناسبة لطريقة جمع وتوثيق هذه الحالة:",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Spacer(Modifier.height(6.dp))
        MethodologyTagPicker(vm, state)
        Spacer(Modifier.height(6.dp))
        TextFieldRow(
            label = "ملاحظات إضافية حول المنهجية",
            value = state.fields["methodology_notes"] ?: "",
            onValueChange = { vm.setField("methodology_notes", it) },
            singleLine = false,
            maxLines = 3
        )
        DropdownRow(
            label = "نوع المنهجية",
            value = state.fields["methodology_type"] ?: "",
            options = listOf("" to "-- اختر --") + MethodologyTypes,
            onChange = { vm.setField("methodology_type", it) }
        )
    }

    SectionCard(title = "ملاحظات إضافية", icon = Icons.Default.NoteAlt) {
        TextFieldRow(
            label = "ملاحظات",
            value = state.fields["notes"] ?: "",
            onValueChange = { vm.setField("notes", it) },
            placeholder = "أي ملاحظات إضافية أو معلومات لم تُذكر أعلاه...",
            singleLine = false,
            maxLines = 8
        )
    }

    SectionCard(title = "ملخص قبل الحفظ", icon = Icons.Default.CheckCircle) {
        SummaryRow("الاسم", listOf(
            state.fields["first_name"], state.fields["father_name"], state.fields["last_name"]
        ).filterNot { it.isNullOrBlank() }.joinToString(" "))
        SummaryRow("التصنيف", state.fields["status"])
        SummaryRow("نوع الحالة", state.fields["case_type"])
        SummaryRow("المحافظة", state.fields["province"])
        SummaryRow("الرقم الوطني", state.fields["national_id"])
        SummaryRow("المُبلِّغ", state.fields["reporter_name"])
        SummaryRow("نوع المصدر", state.fields["source_type"])
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
private fun MethodologyTagPicker(vm: EntryFormViewModel, state: FormState) {
    val selected = (state.fields["methodology_tags"] ?: "")
        .split('|').filter { it.isNotBlank() }.toSet()
    MethodologyTags.chunked(2).forEach { pair ->
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            pair.forEach { tag ->
                FilterChip(
                    modifier = Modifier.weight(1f),
                    selected = tag in selected,
                    onClick = {
                        val next = if (tag in selected) selected - tag else selected + tag
                        vm.setField("methodology_tags", next.joinToString("|"))
                    },
                    label = { Text(tag, style = MaterialTheme.typography.bodySmall) }
                )
            }
            if (pair.size == 1) Spacer(modifier = Modifier.weight(1f))
        }
    }
}

@Composable
private fun SummaryRow(label: String, value: String?) {
    val v = value?.trim().orEmpty().ifBlank { "—" }
    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp)) {
        Text(label, fontWeight = FontWeight.Medium, modifier = Modifier.padding(end = 8.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(v, modifier = Modifier.weight(1f))
    }
}

private val MethodologyTags = listOf(
    "مقابلة مباشرة",
    "مقابلة هاتفية",
    "مقابلة عبر الإنترنت",
    "شهادة شاهد عيان",
    "شهادة أحد الأقارب",
    "تسريبات قيصر",
    "وثائق رسمية",
    "بيانات السجل المدني",
    "تقارير إعلامية",
    "منشورات وسائل التواصل",
    "تقارير منظمات حقوقية",
    "أرشيف رقمي",
    "تحليل صور/فيديو",
    "تقاطع معلومات من مصادر متعددة",
    "زيارة ميدانية",
    "بلاغ مجهول"
)

private val MethodologyTypes = listOf(
    "interview" to "مقابلة شخصية",
    "document_review" to "مراجعة وثائق",
    "open_source" to "تحقيق مصادر مفتوحة",
    "field_visit" to "زيارة ميدانية",
    "remote_interview" to "مقابلة عن بعد",
    "database_cross_ref" to "تقاطع قواعد بيانات",
    "witness_testimony" to "شهادة شاهد",
    "other" to "أخرى"
)
