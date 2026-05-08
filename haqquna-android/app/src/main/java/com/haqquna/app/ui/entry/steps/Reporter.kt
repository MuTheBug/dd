package com.haqquna.app.ui.entry.steps

import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Assignment
import androidx.compose.material.icons.filled.PersonOutline
import androidx.compose.runtime.Composable
import com.haqquna.app.data.CaseStatus
import com.haqquna.app.ui.DropdownRow
import com.haqquna.app.ui.SectionCard
import com.haqquna.app.ui.TextFieldRow
import com.haqquna.app.ui.entry.EntryFormViewModel
import com.haqquna.app.ui.entry.FormState

@Composable
fun ReporterStep(vm: EntryFormViewModel, state: FormState) {

    SectionCard(title = "حالة الشخص الموثَّق", subtitle = "اختَر الحالة لتظهر الحقول المناسبة", icon = Icons.Default.Assignment) {
        DropdownRow(
            label = "الحالة",
            value = state.fields["status"] ?: "",
            options = CaseStatus.values().map { it.key to it.arabic },
            onChange = { vm.setField("status", it) },
            required = true
        )
        DropdownRow(
            label = "نوع الحالة",
            value = state.fields["case_type"] ?: "individual",
            options = listOf(
                "individual" to "فرد",
                "family" to "عائلة",
                "group" to "مجموعة"
            ),
            onChange = { vm.setField("case_type", it) }
        )
    }

    SectionCard(title = "المُبلِّغ", subtitle = "بيانات الشخص الذي قدّم المعلومة", icon = Icons.Default.PersonOutline) {
        TextFieldRow(
            label = "اسم المُبلِّغ",
            value = state.fields["reporter_name"] ?: "",
            onValueChange = { vm.setField("reporter_name", it) },
            required = true
        )
        DropdownRow(
            label = "صلة المُبلِّغ بالحالة",
            value = state.fields["reporter_relation"] ?: "",
            options = listOf(
                "self" to "هو نفسه",
                "father" to "الأب",
                "mother" to "الأم",
                "spouse" to "الزوج/الزوجة",
                "sibling" to "الأخ/الأخت",
                "child" to "الابن/الابنة",
                "relative" to "قريب آخر",
                "friend" to "صديق",
                "neighbor" to "جار",
                "lawyer" to "محامي",
                "other" to "آخر"
            ),
            onChange = { vm.setField("reporter_relation", it) },
            required = true
        )
        TextFieldRow(
            label = "رقم هاتف المُبلِّغ",
            value = state.fields["reporter_phone"] ?: "",
            onValueChange = { vm.setField("reporter_phone", it) },
            keyboardType = androidx.compose.ui.text.input.KeyboardType.Phone
        )
        TextFieldRow(
            label = "الرقم الوطني للمُبلِّغ",
            value = state.fields["reporter_id"] ?: "",
            onValueChange = { vm.setField("reporter_id", it) }
        )
        TextFieldRow(
            label = "اسم الموظف/المتطوع",
            value = state.fields["collector_name"] ?: "",
            onValueChange = { vm.setField("collector_name", it) }
        )
    }
}
