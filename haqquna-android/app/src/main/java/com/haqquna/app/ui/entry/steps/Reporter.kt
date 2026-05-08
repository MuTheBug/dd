package com.haqquna.app.ui.entry.steps

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Assignment
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.PersonOutline
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.haqquna.app.data.CaseStatus
import com.haqquna.app.ui.DropdownRow
import com.haqquna.app.ui.SectionCard
import com.haqquna.app.ui.TextFieldRow
import com.haqquna.app.ui.entry.EntryFormViewModel
import com.haqquna.app.ui.entry.FormState

@Composable
fun ReporterStep(vm: EntryFormViewModel, state: FormState) {

    SectionCard(title = "تصنيف الحالة", subtitle = "اختَر التصنيف لتظهر الحقول المناسبة", icon = Icons.Default.Assignment) {
        DropdownRow(
            label = "تصنيف الحالة",
            value = state.fields["status"] ?: "",
            options = listOf("" to "-- اختر التصنيف --") +
                CaseStatus.values().map { it.key to it.arabic },
            onChange = { vm.setField("status", it) },
            required = true
        )
        DropdownRow(
            label = "نوع الحالة التفصيلي",
            value = state.fields["case_type"] ?: "",
            options = caseTypeOptionsFor(state.fields["status"]),
            onChange = { vm.setField("case_type", it) }
        )
    }

    SectionCard(title = "المُبلِّغ", subtitle = "بيانات الشخص الذي قدّم المعلومة", icon = Icons.Default.PersonOutline) {
        TextFieldRow(
            label = "اسم المُبلِّغ",
            value = state.fields["reporter_name"] ?: "",
            onValueChange = { vm.setField("reporter_name", it) },
            placeholder = "الاسم الكامل للمُبلِّغ",
            required = true
        )
        DropdownRow(
            label = "صلة المُبلِّغ بالضحية",
            value = state.fields["reporter_relation"] ?: "",
            options = listOf("" to "-- اختر الصلة --") + ReporterRelations.map { it to it },
            onChange = { vm.setField("reporter_relation", it) },
            required = true
        )
        TextFieldRow(
            label = "هاتف المُبلِّغ",
            value = state.fields["reporter_phone"] ?: "",
            onValueChange = { vm.setField("reporter_phone", it) },
            keyboardType = KeyboardType.Phone
        )
        TextFieldRow(
            label = "رقم هوية المُبلِّغ",
            value = state.fields["reporter_id"] ?: "",
            onValueChange = { vm.setField("reporter_id", it) },
            placeholder = "الرقم الوطني للمُبلِّغ"
        )
        TextFieldRow(
            label = "اسم جامع البيانات",
            value = state.fields["collector_name"] ?: "",
            onValueChange = { vm.setField("collector_name", it) },
            placeholder = "اسم الموظف/المتطوع"
        )
        TextFieldRow(
            label = "تاريخ جمع البيانات (yyyy-mm-dd)",
            value = state.fields["collection_date"] ?: "",
            onValueChange = { vm.setField("collection_date", it) }
        )
    }

    SectionCard(title = "نوع المصدر", icon = Icons.Default.Description) {
        DropdownRow(
            label = "نوع المصدر",
            value = state.fields["source_type"] ?: "",
            options = listOf("" to "-- اختر نوع المصدر --") + SourceTypes.map { it to it },
            onChange = { vm.setField("source_type", it) },
            required = true
        )
        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            val checked = state.fields["informant_consent"] == "1"
            Checkbox(
                checked = checked,
                onCheckedChange = { vm.setField("informant_consent", if (it) "1" else "") }
            )
            Text(
                "أقرّ بموافقتي الواعية على جمع هذه المعلومات واستخدامها لأغراض التوثيق وفق بروتوكول بيركلي",
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(start = 6.dp)
            )
        }
    }
}

private val ReporterRelations = listOf(
    "أم", "أب", "أخ", "أخت", "زوج/ة", "ابن/ة",
    "قريب", "صديق", "جار", "زميل", "الشخص نفسه", "أخرى"
)

private val SourceTypes = listOf(
    "مقابلة مباشرة",
    "مقابلة هاتفية",
    "وثائق رسمية",
    "مصادر مفتوحة",
    "شهادة شاهد",
    "تسريبات",
    "إحالة",
    "أخرى"
)

private fun caseTypeOptionsFor(status: String?): List<Pair<String, String>> {
    val base = listOf("" to "-- اختر التصنيف أولاً --")
    return when (status) {
        "survivor" -> base + listOf(
            "survivor_documented" to "ناجٍ - لديه وثائق",
            "survivor_undocumented" to "ناجٍ - بدون وثائق"
        )
        "enforced" -> base + listOf(
            "enforced_disappearance_no_info" to "اختفاء قسري - لا معلومات بعد الاعتقال",
            "enforced_disappearance_leaked_not_confirmed" to "تسريبات تؤكد الوفاة - غير مؤكد بالنفوس",
            "enforced_disappearance_witnesses_alive_registry" to "شهود على الاعتقال - حي بالنفوس"
        )
        "deceased" -> base + listOf(
            "enforced_disappearance_leaked_confirmed_dead" to "تسريبات + مؤكد بالنفوس",
            "enforced_disappearance_civil_registry_dead" to "متوفى بحسب النفوس فقط",
            "deceased_caesar_files" to "متوفى - ملفات قيصر"
        )
        else -> base
    }
}
