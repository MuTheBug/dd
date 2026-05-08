package com.haqquna.app.ui.entry.steps

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ChildCare
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.FamilyRestroom
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.LocalHospital
import androidx.compose.material.icons.filled.School
import androidx.compose.material.icons.filled.Work
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.haqquna.app.ui.DropdownRow
import com.haqquna.app.ui.SectionCard
import com.haqquna.app.ui.TextFieldRow
import com.haqquna.app.ui.entry.EntryFormViewModel
import com.haqquna.app.ui.entry.FormState

@Composable
fun AddressStep(vm: EntryFormViewModel, state: FormState) {

    SectionCard(title = "الحالة العائلية", icon = Icons.Default.FamilyRestroom) {
        DropdownRow(
            label = "الحالة الاجتماعية",
            value = state.fields["marital"] ?: "",
            options = listOf(
                "" to "—",
                "single" to "أعزب/عزباء",
                "married" to "متزوج/ـة",
                "divorced" to "مطلق/ـة",
                "widowed" to "أرمل/ـة"
            ),
            onChange = { vm.setField("marital", it) }
        )
        when (state.fields["marital"]) {
            "single" -> {
                TextFieldRow(label = "اسم ولي الأمر", value = state.fields["guardian_name"] ?: "", onValueChange = { vm.setField("guardian_name", it) })
                TextFieldRow(label = "صلة ولي الأمر", value = state.fields["guardian_relation"] ?: "", onValueChange = { vm.setField("guardian_relation", it) })
                TextFieldRow(
                    label = "هاتف ولي الأمر",
                    value = state.fields["guardian_phone"] ?: "",
                    onValueChange = { vm.setField("guardian_phone", it) },
                    keyboardType = KeyboardType.Phone
                )
            }
            "married", "widowed" -> {
                TextFieldRow(label = "اسم الزوج/الزوجة", value = state.fields["spouse_name"] ?: "", onValueChange = { vm.setField("spouse_name", it) })
                TextFieldRow(
                    label = "هاتف الزوج/الزوجة",
                    value = state.fields["spouse_phone"] ?: "",
                    onValueChange = { vm.setField("spouse_phone", it) },
                    keyboardType = KeyboardType.Phone
                )
            }
            "divorced" -> {
                TextFieldRow(label = "اسم الطليق/ة", value = state.fields["ex_spouse_name"] ?: "", onValueChange = { vm.setField("ex_spouse_name", it) })
            }
        }
    }

    SectionCard(title = "الأبناء", icon = Icons.Default.ChildCare) {
        OutlinedButton(modifier = Modifier.fillMaxWidth(), onClick = { vm.addChild() }) {
            Icon(Icons.Default.Add, null); Spacer(Modifier.width(6.dp))
            Text("إضافة ابن/ابنة")
        }
    }
    state.children.forEachIndexed { idx, c ->
        Card(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
            shape = MaterialTheme.shapes.medium,
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
        ) {
            androidx.compose.foundation.layout.Column(modifier = Modifier.padding(14.dp)) {
                Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text("طفل #${idx + 1}", modifier = Modifier.weight(1f), fontWeight = FontWeight.SemiBold)
                    IconButton(onClick = { vm.removeChild(idx) }) {
                        Icon(Icons.Default.Delete, "حذف", tint = MaterialTheme.colorScheme.error)
                    }
                }
                TextFieldRow(label = "الاسم", value = c.name, onValueChange = { vm.updateChild(idx, c.copy(name = it)) })
                DropdownRow(
                    label = "الجنس",
                    value = c.gender,
                    options = listOf("" to "—", "male" to "ذكر", "female" to "أنثى"),
                    onChange = { vm.updateChild(idx, c.copy(gender = it)) }
                )
                TextFieldRow(
                    label = "سنة الميلاد",
                    value = c.birthYear,
                    onValueChange = { vm.updateChild(idx, c.copy(birthYear = it.filter { ch -> ch.isDigit() }.take(4))) },
                    keyboardType = KeyboardType.Number
                )
                TextFieldRow(
                    label = "ملاحظات",
                    value = c.notes,
                    onValueChange = { vm.updateChild(idx, c.copy(notes = it)) },
                    singleLine = false,
                    maxLines = 2
                )
            }
        }
    }

    SectionCard(title = "العنوان والسكن", icon = Icons.Default.Home) {
        DropdownRow(
            label = "نطاق العنوان",
            value = state.fields["address_area"] ?: "",
            options = listOf(
                "" to "—",
                "city" to "مدينة",
                "village" to "قرية",
                "camp" to "مخيم",
                "displaced" to "نزوح"
            ),
            onChange = { vm.setField("address_area", it) }
        )
        TextFieldRow(
            label = "العنوان التفصيلي",
            value = state.fields["address"] ?: "",
            onValueChange = { vm.setField("address", it) },
            singleLine = false,
            maxLines = 3
        )
        DropdownRow(
            label = "نوع السكن",
            value = state.fields["housing_type"] ?: "",
            options = listOf(
                "" to "—",
                "owned" to "ملك",
                "rented" to "إيجار",
                "shelter" to "مأوى",
                "displaced" to "نازح",
                "tent" to "خيمة",
                "other" to "آخر"
            ),
            onChange = { vm.setField("housing_type", it) }
        )
        TextFieldRow(
            label = "قيمة الإيجار (إن وُجد)",
            value = state.fields["rent_amount"] ?: "",
            onValueChange = { vm.setField("rent_amount", it) },
            keyboardType = KeyboardType.Number
        )
    }

    SectionCard(title = "العمل والمهنة", icon = Icons.Default.Work) {
        DropdownRow(
            label = "حالة العمل",
            value = state.fields["employment"] ?: "",
            options = listOf(
                "" to "—",
                "employed" to "يعمل",
                "unemployed" to "بدون عمل",
                "student" to "طالب",
                "retired" to "متقاعد",
                "homemaker" to "ربة منزل",
                "disabled" to "غير قادر للعمل"
            ),
            onChange = { vm.setField("employment", it) }
        )
        TextFieldRow(
            label = "المهنة",
            value = state.fields["profession"] ?: "",
            onValueChange = { vm.setField("profession", it) }
        )
        TextFieldRow(
            label = "جهة العمل",
            value = state.fields["employer"] ?: "",
            onValueChange = { vm.setField("employer", it) }
        )
        TextFieldRow(
            label = "اسم المعيل (إن وُجد)",
            value = state.fields["breadwinner"] ?: "",
            onValueChange = { vm.setField("breadwinner", it) }
        )
    }

    SectionCard(title = "التعليم", icon = Icons.Default.School) {
        DropdownRow(
            label = "المستوى التعليمي",
            value = state.fields["education"] ?: "",
            options = listOf(
                "" to "—",
                "none" to "لا يقرأ ولا يكتب",
                "read_write" to "يقرأ ويكتب",
                "primary" to "ابتدائي",
                "preparatory" to "إعدادي",
                "secondary" to "ثانوي",
                "vocational" to "مهني",
                "university" to "جامعي",
                "postgrad" to "دراسات عليا"
            ),
            onChange = { vm.setField("education", it) }
        )
        TextFieldRow(label = "الاختصاص", value = state.fields["edu_specialization"] ?: "", onValueChange = { vm.setField("edu_specialization", it) })
        TextFieldRow(label = "اسم الجامعة/المعهد", value = state.fields["edu_university"] ?: "", onValueChange = { vm.setField("edu_university", it) })
    }

    SectionCard(title = "الحالة الصحية", icon = Icons.Default.LocalHospital) {
        TextFieldRow(
            label = "أمراض مزمنة",
            value = state.fields["chronic"] ?: "",
            onValueChange = { vm.setField("chronic", it) },
            placeholder = "ضغط الدم، السكري، ربو..."
        )
        TextFieldRow(
            label = "تفاصيل أخرى",
            value = state.fields["other_diseases"] ?: "",
            onValueChange = { vm.setField("other_diseases", it) },
            singleLine = false,
            maxLines = 3
        )
        TextFieldRow(
            label = "احتياجات خاصة",
            value = state.fields["special_needs_details"] ?: "",
            onValueChange = { vm.setField("special_needs_details", it) },
            singleLine = false,
            maxLines = 3
        )
    }
}
