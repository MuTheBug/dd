package com.haqquna.app.ui.entry.steps

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.Gavel
import androidx.compose.material.icons.filled.HelpOutline
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.Checkbox
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.haqquna.app.AppContainer
import com.haqquna.app.data.CaseStatus
import com.haqquna.app.ui.DatePickerField
import com.haqquna.app.ui.DropdownRow
import com.haqquna.app.ui.SectionCard
import com.haqquna.app.ui.SingleDatePickerField
import com.haqquna.app.ui.TextFieldRow
import com.haqquna.app.ui.entry.EntryFormViewModel
import com.haqquna.app.ui.entry.FormState

@Composable
fun StatusDetailsStep(vm: EntryFormViewModel, state: FormState, container: AppContainer) {
    val status = CaseStatus.fromKey(state.fields["status"])

    if (status == null) {
        SectionCard(title = "اختر تصنيف الحالة", icon = Icons.Default.HelpOutline) {
            Text("ارجع للخطوة الأولى واختَر تصنيف الحالة لتظهر الحقول التفصيلية المناسبة هنا.")
        }
        return
    }

    ArrestSection(vm, state)
    if (status == CaseStatus.SURVIVOR) SurvivorSection(vm, state, container)
    if (status == CaseStatus.DECEASED) DeathSection(vm, state)

    DigitalEvidenceSection(vm, state, container)
    CivilRegistrySection(vm, state, container)
    ConflictingInfoSection(vm, state)
}

@Composable
private fun ArrestSection(vm: EntryFormViewModel, state: FormState) {
    SectionCard(title = "تفاصيل الاعتقال والاحتجاز", icon = Icons.Default.Lock) {
        DatePickerField(
            label = "تاريخ الاعتقال",
            day = state.fields["arrest_day"] ?: "",
            month = state.fields["arrest_month"] ?: "",
            year = state.fields["arrest_year"] ?: "",
            onDateChange = { d, m, y ->
                vm.setField("arrest_day", d)
                vm.setField("arrest_month", m)
                vm.setField("arrest_year", y)
            },
            minYear = 1970
        )
        DropdownRow(
            label = "الجهة المعتقِلة",
            value = state.fields["arrest_authority"] ?: "",
            options = listOf("" to "-- اختر --") + ArrestAuthorities.map { it to it },
            onChange = { vm.setField("arrest_authority", it) },
            required = true
        )
        DropdownRow(
            label = "مكان الاحتجاز / المعتقل",
            value = state.fields["arrest_place"] ?: "",
            options = listOf("" to "-- اختر --") + DetentionFacilities.map { it to it },
            onChange = { vm.setField("arrest_place", it) }
        )
        TextFieldRow(
            label = "سبب الاعتقال",
            value = state.fields["arrest_reason"] ?: "",
            onValueChange = { vm.setField("arrest_reason", it) },
            placeholder = "مظاهرة، تقرير كيدي، حاجز...",
            singleLine = false,
            maxLines = 3,
            required = true
        )
        TextFieldRow(
            label = "المتسبب بالاعتقال (إن وُجد)",
            value = state.fields["arrest_causer"] ?: "",
            onValueChange = { vm.setField("arrest_causer", it) },
            placeholder = "اسم الشخص أو الجهة"
        )
        TextFieldRow(
            label = "آخر مكان معروف",
            value = state.fields["last_known_location"] ?: "",
            onValueChange = { vm.setField("last_known_location", it) }
        )
        SingleDatePickerField(
            label = "آخر تاريخ عُرف أنه حي",
            value = state.fields["last_known_alive_date"] ?: "",
            onValueChange = { vm.setField("last_known_alive_date", it) },
            minYear = 1970
        )
    }
}

@Composable
private fun SurvivorSection(vm: EntryFormViewModel, state: FormState, container: AppContainer) {
    SectionCard(title = "بيانات الإفراج (للناجين)", icon = Icons.Default.Gavel) {
        DatePickerField(
            label = "تاريخ الإفراج",
            day = state.fields["release_day"] ?: "",
            month = state.fields["release_month"] ?: "",
            year = state.fields["release_year"] ?: "",
            onDateChange = { d, m, y ->
                vm.setField("release_day", d)
                vm.setField("release_month", m)
                vm.setField("release_year", y)
            },
            minYear = 1970
        )
        TextFieldRow(
            label = "وصف تجربة الاعتقال",
            value = state.fields["survivor_cv_text"] ?: "",
            onValueChange = { vm.setField("survivor_cv_text", it) },
            placeholder = "وصف مختصر لتجربة الاعتقال والاحتجاز...",
            singleLine = false,
            maxLines = 6
        )
        AttachmentRow(label = "ملخص التجربة (PDF/صورة)", field = "survivor_cv", mime = "*/*", state = state, container = container, vm = vm)
        AttachmentRow(label = "صورة بعد الإفراج", field = "survivor_cv_photo", mime = "image/*", state = state, container = container, vm = vm)
    }
}

@Composable
private fun DeathSection(vm: EntryFormViewModel, state: FormState) {
    SectionCard(title = "بيانات الوفاة", icon = Icons.Default.Description) {
        DatePickerField(
            label = "تاريخ الوفاة",
            day = state.fields["death_day"] ?: "",
            month = state.fields["death_month"] ?: "",
            year = state.fields["death_year"] ?: "",
            onDateChange = { d, m, y ->
                vm.setField("death_day", d)
                vm.setField("death_month", m)
                vm.setField("death_year", y)
            },
            minYear = 1970
        )
        TextFieldRow(
            label = "مكان الوفاة",
            value = state.fields["death_place"] ?: "",
            onValueChange = { vm.setField("death_place", it) },
            placeholder = "مكان الوفاة إن عُرف"
        )
    }
}

@Composable
private fun DigitalEvidenceSection(vm: EntryFormViewModel, state: FormState, container: AppContainer) {
    SectionCard(title = "الأدلة الرقمية", subtitle = "بروتوكول بيركلي - تسريبات، مصادر مفتوحة", icon = Icons.Default.Description) {
        DropdownRow(
            label = "نوع الدليل الرقمي",
            value = state.fields["digital_evidence_type"] ?: "",
            options = listOf("" to "-- لا يوجد --") + DigitalEvidenceTypes,
            onChange = { vm.setField("digital_evidence_type", it) }
        )
        DropdownRow(
            label = "مستوى الأدلة",
            value = state.fields["evidence_level"] ?: "unverified",
            options = EvidenceLevels,
            onChange = { vm.setField("evidence_level", it) }
        )
        TextFieldRow(
            label = "عدد مصادر الأدلة",
            value = state.fields["evidence_sources_count"] ?: "0",
            onValueChange = { vm.setField("evidence_sources_count", it.filter { c -> c.isDigit() }.take(3)) },
            keyboardType = KeyboardType.Number
        )
        TextFieldRow(
            label = "رابط الدليل",
            value = state.fields["digital_evidence_url"] ?: "",
            onValueChange = { vm.setField("digital_evidence_url", it) },
            keyboardType = KeyboardType.Uri,
            placeholder = "https://..."
        )
        DropdownRow(
            label = "حالة الرابط",
            value = state.fields["digital_evidence_url_status"] ?: "",
            options = listOf(
                "" to "-- اختر --",
                "active" to "فعّال",
                "deleted" to "محذوف",
                "archived" to "مؤرشف",
                "unknown" to "غير معروف",
                "no_url" to "لم يكن هناك رابط أصلاً",
                "url_forgotten" to "الرابط غير متاح (نُسي)"
            ),
            onChange = { vm.setField("digital_evidence_url_status", it) }
        )
        TextFieldRow(
            label = "رابط المصدر الأصلي",
            value = state.fields["source_url"] ?: "",
            onValueChange = { vm.setField("source_url", it) },
            placeholder = "https://... وثّق الرابط حتى لو كان محذوفاً",
            keyboardType = KeyboardType.Uri
        )
        SingleDatePickerField(
            label = "تاريخ الدليل الرقمي",
            value = state.fields["digital_evidence_date"] ?: "",
            onValueChange = { vm.setField("digital_evidence_date", it) },
            minYear = 1980
        )
        TextFieldRow(
            label = "الاسم الوارد في الدليل",
            value = state.fields["digital_evidence_person_name"] ?: "",
            onValueChange = { vm.setField("digital_evidence_person_name", it) },
            placeholder = "الاسم كما ظهر في التسريبات"
        )
        SingleDatePickerField(
            label = "تاريخ الوفاة الوارد في الدليل",
            value = state.fields["digital_evidence_death_date"] ?: "",
            onValueChange = { vm.setField("digital_evidence_death_date", it) },
            minYear = 1970
        )
        TextFieldRow(
            label = "وصف الدليل",
            value = state.fields["digital_evidence_description"] ?: "",
            onValueChange = { vm.setField("digital_evidence_description", it) },
            singleLine = false,
            maxLines = 4
        )
        AttachmentRow(label = "لقطة شاشة للدليل", field = "digital_evidence_screenshot", mime = "image/*", state = state, container = container, vm = vm)
    }
}

@Composable
private fun CivilRegistrySection(vm: EntryFormViewModel, state: FormState, container: AppContainer) {
    SectionCard(title = "حالة السجل المدني (النفوس)", icon = Icons.Default.Description) {
        DropdownRow(
            label = "حالة السجل المدني",
            value = state.fields["civil_registry_status"] ?: "",
            options = CivilRegistryStatuses,
            onChange = { vm.setField("civil_registry_status", it) }
        )
        SingleDatePickerField(
            label = "تاريخ مراجعة النفوس",
            value = state.fields["civil_registry_date"] ?: "",
            onValueChange = { vm.setField("civil_registry_date", it) },
            minYear = 1980
        )
        AttachmentRow(label = "وثيقة من النفوس", field = "civil_registry_document", mime = "*/*", state = state, container = container, vm = vm)
    }
}

@Composable
private fun ConflictingInfoSection(vm: EntryFormViewModel, state: FormState) {
    SectionCard(title = "معلومات متضاربة", icon = Icons.Default.Warning) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            val checked = state.fields["has_conflicting_info"] == "1"
            Checkbox(
                checked = checked,
                onCheckedChange = { vm.setField("has_conflicting_info", if (it) "1" else "") }
            )
            Text(
                "يوجد تضارب في المعلومات (مثال: التسريبات تقول متوفى لكن النفوس تقول حي)",
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(start = 6.dp)
            )
        }
        if (state.fields["has_conflicting_info"] == "1") {
            Spacer(Modifier.height(6.dp))
            TextFieldRow(
                label = "تفاصيل التضارب",
                value = state.fields["conflicting_info_details"] ?: "",
                onValueChange = { vm.setField("conflicting_info_details", it) },
                singleLine = false,
                maxLines = 4
            )
        }
    }
}

private val ArrestAuthorities = listOf(
    "الأمن العسكري",
    "الأمن السياسي",
    "أمن الدولة",
    "المخابرات الجوية",
    "الدفاع الوطني",
    "الشرطة العسكرية",
    "الأمن الجنائي",
    "الجيش",
    "حاجز أمني",
    "دورية مشتركة",
    "غير معروف",
    "أخرى"
)

private val DetentionFacilities = listOf(
    "صيدنايا الامني (الاحمر)",
    "صيدنايا القضائي (الابيض)",
    "فرع 215، بسرية المداهمة والاقتحام",
    "فرع 216، فرع الدوريات",
    "فرع 227، فرع المنطقة",
    "فرع 235 فرع فلسطين",
    "فرع 248، التحقيق العسكري",
    "فرع 251، فرع الخطيب",
    "فرع 285، فرع التحقيق",
    "فرع 293",
    "فرع 295، مكافحة الإرهاب",
    "فرع الأمن العسكري",
    "فرع الأمن السياسي",
    "فرع أمن الدولة",
    "فرع المخابرات الجوية",
    "السجن المدني",
    "سجن تدمر",
    "سجن عدرا",
    "سجن حمص المركزي",
    "مطار المزة",
    "المدينة الرياضية",
    "غير معروف",
    "أخرى"
)

private val DigitalEvidenceTypes = listOf(
    "caesar_files" to "ملفات قيصر",
    "leaked_database" to "تسريبات قاعدة بيانات",
    "social_media" to "وسائل التواصل الاجتماعي",
    "news_report" to "تقرير إخباري",
    "ngo_report" to "تقرير منظمة",
    "civil_registry" to "سجل مدني",
    "official_document" to "وثيقة رسمية",
    "other" to "أخرى"
)

private val EvidenceLevels = listOf(
    "high" to "عالي - أدلة موثقة متعددة",
    "medium" to "متوسط - دليل واحد موثق",
    "low" to "منخفض - شهادة شفهية فقط",
    "unverified" to "غير مُتحقق منه"
)

private val CivilRegistryStatuses = listOf(
    "alive" to "حي في السجل المدني",
    "deceased" to "متوفى في السجل المدني",
    "unknown" to "غير معروف",
    "not_checked" to "لم يتم التحقق"
)
