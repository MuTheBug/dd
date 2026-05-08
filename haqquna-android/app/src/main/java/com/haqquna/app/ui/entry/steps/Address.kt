package com.haqquna.app.ui.entry.steps

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
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
import androidx.compose.material3.Checkbox
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
            options = listOf("" to "-- اختر --") + MaritalStatuses,
            onChange = { vm.setField("marital", it) }
        )
        TextFieldRow(label = "اسم ولي الأمر / المعرّف", value = state.fields["guardian_name"] ?: "", onValueChange = { vm.setField("guardian_name", it) })
        TextFieldRow(label = "صلة ولي الأمر", value = state.fields["guardian_relation"] ?: "", onValueChange = { vm.setField("guardian_relation", it) })
        TextFieldRow(
            label = "هاتف ولي الأمر",
            value = state.fields["guardian_phone"] ?: "",
            onValueChange = { vm.setField("guardian_phone", it) },
            keyboardType = KeyboardType.Phone
        )
        when (state.fields["marital"]) {
            "married", "widowed" -> {
                TextFieldRow(label = "اسم الزوج/ة", value = state.fields["spouse_name"] ?: "", onValueChange = { vm.setField("spouse_name", it) })
                TextFieldRow(
                    label = "هاتف الزوج/ة",
                    value = state.fields["spouse_phone"] ?: "",
                    onValueChange = { vm.setField("spouse_phone", it) },
                    keyboardType = KeyboardType.Phone
                )
            }
            "divorced" -> {
                TextFieldRow(label = "اسم الزوج/ة السابق/ة", value = state.fields["ex_spouse_name"] ?: "", onValueChange = { vm.setField("ex_spouse_name", it) })
            }
        }
    }

    SectionCard(title = "الأبناء", icon = Icons.Default.ChildCare) {
        OutlinedButton(modifier = Modifier.fillMaxWidth(), onClick = { vm.addChild() }) {
            Icon(Icons.Default.Add, null); Spacer(Modifier.width(6.dp))
            Text("إضافة طفل")
        }
    }
    state.children.forEachIndexed { idx, c ->
        Card(
            modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp),
            shape = MaterialTheme.shapes.medium,
            colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)
        ) {
            Column(modifier = Modifier.padding(14.dp)) {
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
                    options = listOf("" to "--", "male" to "ذكر", "female" to "أنثى"),
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
            label = "المنطقة / الحي",
            value = state.fields["address_area"] ?: "",
            options = listOf("" to "-- اختر المنطقة --") + AddressAreas.map { it to it },
            onChange = { vm.setField("address_area", it) }
        )
        TextFieldRow(
            label = "العنوان الحالي",
            value = state.fields["address"] ?: "",
            onValueChange = { vm.setField("address", it) },
            placeholder = "العنوان التفصيلي",
            singleLine = false,
            maxLines = 3,
            required = true
        )
        DropdownRow(
            label = "نوع السكن",
            value = state.fields["housing_type"] ?: "",
            options = listOf("" to "-- اختر --") + HousingTypes.map { it to it },
            onChange = { vm.setField("housing_type", it) },
            required = true
        )
        TextFieldRow(
            label = "مبلغ الإيجار (إن وُجد)",
            value = state.fields["rent_amount"] ?: "",
            onValueChange = { vm.setField("rent_amount", it) },
            placeholder = "بالليرة السورية"
        )
    }

    SectionCard(title = "العمل والمهنة", icon = Icons.Default.Work) {
        TextFieldRow(
            label = "الوضع الوظيفي",
            value = state.fields["employment"] ?: "",
            onValueChange = { vm.setField("employment", it) },
            placeholder = "يعمل / لا يعمل"
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
            label = "المعيل",
            value = state.fields["breadwinner"] ?: "",
            onValueChange = { vm.setField("breadwinner", it) },
            placeholder = "اسم المعيل"
        )
        TextFieldRow(
            label = "مهنة المعيل",
            value = state.fields["breadwinner_job"] ?: "",
            onValueChange = { vm.setField("breadwinner_job", it) }
        )
        DropdownRow(
            label = "صلة المعيل بالضحية",
            value = state.fields["breadwinner_relation"] ?: "",
            options = listOf("" to "-- اختر --") + ReporterRelationsList.map { it to it },
            onChange = { vm.setField("breadwinner_relation", it) }
        )
    }

    SectionCard(title = "التحصيل العلمي", icon = Icons.Default.School) {
        DropdownRow(
            label = "المستوى التعليمي",
            value = state.fields["education"] ?: "",
            options = listOf("" to "-- اختر --") + EducationLevels.map { it to it },
            onChange = { vm.setField("education", it) }
        )
        DropdownRow(
            label = "نوع الدراسة",
            value = state.fields["edu_type"] ?: "",
            options = listOf("" to "-- اختر --") + EduTypes.map { it to it },
            onChange = { vm.setField("edu_type", it) }
        )
        TextFieldRow(label = "الاختصاص", value = state.fields["edu_specialization"] ?: "", onValueChange = { vm.setField("edu_specialization", it) })
        TextFieldRow(label = "الجامعة / المعهد", value = state.fields["edu_university"] ?: "", onValueChange = { vm.setField("edu_university", it) })
    }

    SectionCard(title = "الحالة الصحية", icon = Icons.Default.LocalHospital) {
        ChronicChecklist(vm, state)
        TextFieldRow(
            label = "أمراض أخرى غير مذكورة",
            value = state.fields["other_diseases"] ?: "",
            onValueChange = { vm.setField("other_diseases", it) },
            singleLine = false,
            maxLines = 3
        )
        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            val checked = state.fields["has_special_needs"] == "1"
            Checkbox(
                checked = checked,
                onCheckedChange = { vm.setField("has_special_needs", if (it) "1" else "") }
            )
            Text("احتياجات خاصة", modifier = Modifier.padding(start = 6.dp))
        }
        if (state.fields["has_special_needs"] == "1") {
            TextFieldRow(
                label = "تفاصيل الاحتياجات الخاصة",
                value = state.fields["special_needs_details"] ?: "",
                onValueChange = { vm.setField("special_needs_details", it) },
                singleLine = false,
                maxLines = 3
            )
        }
    }
}

@Composable
private fun ChronicChecklist(vm: EntryFormViewModel, state: FormState) {
    val selected = (state.fields["chronic_list"] ?: "").split('|').filter { it.isNotBlank() }.toSet()
    Text("الأمراض المزمنة (اختر ما ينطبق)", style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium, modifier = Modifier.padding(top = 4.dp, bottom = 4.dp))
    val rows = ChronicDiseases.chunked(2)
    rows.forEach { pair ->
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            pair.forEach { disease ->
                Row(
                    modifier = Modifier.weight(1f),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    val on = disease in selected
                    Checkbox(
                        checked = on,
                        onCheckedChange = { checked ->
                            val next = if (checked) selected + disease else selected - disease
                            vm.setField("chronic_list", next.joinToString("|"))
                        }
                    )
                    Text(disease, style = MaterialTheme.typography.bodySmall)
                }
            }
            if (pair.size == 1) Spacer(modifier = Modifier.weight(1f))
        }
    }
}

private val MaritalStatuses = listOf(
    "single" to "أعزب/عزباء",
    "married" to "متزوج/ة",
    "divorced" to "مطلق/ة",
    "widowed" to "أرمل/ة"
)

private val AddressAreas = listOf(
    "الرمل الجنوبي", "قنينص", "الحفة", "الصليبة", "العوينة",
    "الأشرفية", "بستان الصيداوي", "الطابيات", "شيخ ضاهر",
    "حي القصور", "مرتقلا", "شارع انطاكيا", "حي السجن",
    "مشروع القلعة", "شارع ميسلون", "سوق الداية", "الريجي",
    "شارع بور سعيد", "حي الفاروس", "طريق الحرش", "خارج اللاذقية", "أخرى"
)

private val HousingTypes = listOf("ملك", "إيجار", "رهن", "مستضاف", "أخرى")

private val EducationLevels = listOf(
    "أمّي", "ابتدائية", "إعدادية", "ثانوية", "معهد",
    "بكالوريوس", "ماجستير", "دكتوراه"
)

private val EduTypes = listOf("علمي", "أدبي", "شرعي", "مهني", "تجاري", "صناعي", "نسوي", "أخرى")

private val ReporterRelationsList = listOf(
    "أم", "أب", "أخ", "أخت", "زوج/ة", "ابن/ة",
    "قريب", "صديق", "جار", "زميل", "الشخص نفسه", "أخرى"
)

private val ChronicDiseases = listOf(
    "ضغط الدم", "السكري", "الربو", "أمراض القلب", "الكلى",
    "الكبد", "السرطان", "الصرع", "الثلاسيميا", "فقر الدم",
    "التهاب المفاصل", "هشاشة العظام", "الغدة الدرقية",
    "أمراض الجهاز الهضمي", "أمراض الجهاز التنفسي",
    "أمراض نفسية", "اكتئاب", "اضطراب ما بعد الصدمة (PTSD)",
    "إعاقة حركية", "إعاقة بصرية", "إعاقة سمعية", "أخرى"
)
