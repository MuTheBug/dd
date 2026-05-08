package com.haqquna.app.ui.entry.steps

import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.haqquna.app.AppContainer
import com.haqquna.app.data.CaseStatus
import com.haqquna.app.ui.DropdownRow
import com.haqquna.app.ui.SectionCard
import com.haqquna.app.ui.TextFieldRow
import com.haqquna.app.ui.entry.EntryFormViewModel
import com.haqquna.app.ui.entry.FormState

@Composable
fun StatusDetailsStep(vm: EntryFormViewModel, state: FormState, container: AppContainer) {
    val status = CaseStatus.fromKey(state.fields["status"])

    if (status == null) {
        SectionCard(title = "اختر حالة الشخص", icon = Icons.Default.HelpOutline) {
            Text("ارجع للخطوة الأولى واختَر حالة الشخص لتظهر الحقول التفصيلية المناسبة هنا.")
        }
        return
    }

    when (status) {
        CaseStatus.ARRESTED, CaseStatus.MISSING -> ArrestSection(vm, state, status)
        CaseStatus.SURVIVOR -> SurvivorSection(vm, state, container)
        CaseStatus.DEAD -> DeathSection(vm, state)
        CaseStatus.FOUND -> FoundSection(vm, state)
    }

    DigitalEvidenceSection(vm, state, container)
    CivilRegistrySection(vm, state, container)
}

@Composable
private fun ArrestSection(vm: EntryFormViewModel, state: FormState, status: CaseStatus) {
    SectionCard(
        title = if (status == CaseStatus.ARRESTED) "تفاصيل الاعتقال" else "تفاصيل الاختفاء",
        icon = Icons.Default.Lock
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            TextFieldRow(
                label = "اليوم",
                value = state.fields["arrest_day"] ?: "",
                onValueChange = { vm.setField("arrest_day", it.filter { c -> c.isDigit() }.take(2)) },
                keyboardType = KeyboardType.Number
            )
            TextFieldRow(
                label = "الشهر",
                value = state.fields["arrest_month"] ?: "",
                onValueChange = { vm.setField("arrest_month", it.filter { c -> c.isDigit() }.take(2)) },
                keyboardType = KeyboardType.Number
            )
            TextFieldRow(
                label = "السنة",
                value = state.fields["arrest_year"] ?: "",
                onValueChange = { vm.setField("arrest_year", it.filter { c -> c.isDigit() }.take(4)) },
                keyboardType = KeyboardType.Number
            )
        }
        DropdownRow(
            label = "الجهة المسؤولة",
            value = state.fields["arrest_authority"] ?: "",
            options = listOf(
                "" to "اختر...",
                "regime" to "النظام السابق",
                "isis" to "تنظيم داعش",
                "nusra" to "جبهة النصرة",
                "sdf" to "قسد",
                "fsa" to "الجيش الحر",
                "tahrir_alsham" to "هيئة تحرير الشام",
                "criminal" to "جهة إجرامية",
                "unknown" to "غير معروف",
                "other" to "أخرى"
            ),
            onChange = { vm.setField("arrest_authority", it) },
            required = true
        )
        TextFieldRow(
            label = "مكان الاعتقال",
            value = state.fields["arrest_place"] ?: "",
            onValueChange = { vm.setField("arrest_place", it) }
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
            label = "اسم الجهة/الشخص المتسبب",
            value = state.fields["arrest_causer"] ?: "",
            onValueChange = { vm.setField("arrest_causer", it) }
        )
        TextFieldRow(
            label = "آخر مكان عُرف",
            value = state.fields["last_known_location"] ?: "",
            onValueChange = { vm.setField("last_known_location", it) }
        )
        TextFieldRow(
            label = "تاريخ آخر معلومة عن كونه حياً (yyyy-mm-dd)",
            value = state.fields["last_known_alive_date"] ?: "",
            onValueChange = { vm.setField("last_known_alive_date", it) }
        )
    }
}

@Composable
private fun SurvivorSection(vm: EntryFormViewModel, state: FormState, container: AppContainer) {
    SectionCard(title = "تفاصيل الاعتقال السابق", icon = Icons.Default.Gavel) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            TextFieldRow(
                label = "يوم الاعتقال",
                value = state.fields["arrest_day"] ?: "",
                onValueChange = { vm.setField("arrest_day", it.filter { c -> c.isDigit() }.take(2)) },
                keyboardType = KeyboardType.Number
            )
            TextFieldRow(
                label = "شهر",
                value = state.fields["arrest_month"] ?: "",
                onValueChange = { vm.setField("arrest_month", it.filter { c -> c.isDigit() }.take(2)) },
                keyboardType = KeyboardType.Number
            )
            TextFieldRow(
                label = "سنة",
                value = state.fields["arrest_year"] ?: "",
                onValueChange = { vm.setField("arrest_year", it.filter { c -> c.isDigit() }.take(4)) },
                keyboardType = KeyboardType.Number
            )
        }
        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            TextFieldRow(
                label = "يوم الإفراج",
                value = state.fields["release_day"] ?: "",
                onValueChange = { vm.setField("release_day", it.filter { c -> c.isDigit() }.take(2)) },
                keyboardType = KeyboardType.Number
            )
            TextFieldRow(
                label = "شهر",
                value = state.fields["release_month"] ?: "",
                onValueChange = { vm.setField("release_month", it.filter { c -> c.isDigit() }.take(2)) },
                keyboardType = KeyboardType.Number
            )
            TextFieldRow(
                label = "سنة",
                value = state.fields["release_year"] ?: "",
                onValueChange = { vm.setField("release_year", it.filter { c -> c.isDigit() }.take(4)) },
                keyboardType = KeyboardType.Number
            )
        }
        TextFieldRow(
            label = "تجربة الاعتقال (نصّ)",
            value = state.fields["survivor_cv_text"] ?: "",
            onValueChange = { vm.setField("survivor_cv_text", it) },
            singleLine = false,
            maxLines = 6
        )
        AttachmentRow(label = "وثيقة شهادة (PDF)", field = "survivor_cv", mime = "*/*", state = state, container = container, vm = vm)
        AttachmentRow(label = "صورة شهادة", field = "survivor_cv_photo", mime = "image/*", state = state, container = container, vm = vm)
    }
}

@Composable
private fun DeathSection(vm: EntryFormViewModel, state: FormState) {
    SectionCard(title = "تفاصيل الوفاة", icon = Icons.Default.Description) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            TextFieldRow(
                label = "اليوم",
                value = state.fields["death_day"] ?: "",
                onValueChange = { vm.setField("death_day", it.filter { c -> c.isDigit() }.take(2)) },
                keyboardType = KeyboardType.Number
            )
            TextFieldRow(
                label = "الشهر",
                value = state.fields["death_month"] ?: "",
                onValueChange = { vm.setField("death_month", it.filter { c -> c.isDigit() }.take(2)) },
                keyboardType = KeyboardType.Number
            )
            TextFieldRow(
                label = "السنة",
                value = state.fields["death_year"] ?: "",
                onValueChange = { vm.setField("death_year", it.filter { c -> c.isDigit() }.take(4)) },
                keyboardType = KeyboardType.Number
            )
        }
        TextFieldRow(
            label = "مكان الوفاة",
            value = state.fields["death_place"] ?: "",
            onValueChange = { vm.setField("death_place", it) }
        )
    }
}

@Composable
private fun FoundSection(vm: EntryFormViewModel, state: FormState) {
    SectionCard(title = "تفاصيل العثور", icon = Icons.Default.Description) {
        TextFieldRow(
            label = "تاريخ العثور (yyyy-mm-dd)",
            value = state.fields["last_known_alive_date"] ?: "",
            onValueChange = { vm.setField("last_known_alive_date", it) }
        )
        TextFieldRow(
            label = "مكان العثور",
            value = state.fields["last_known_location"] ?: "",
            onValueChange = { vm.setField("last_known_location", it) }
        )
    }
}

@Composable
private fun DigitalEvidenceSection(vm: EntryFormViewModel, state: FormState, container: AppContainer) {
    SectionCard(title = "الأدلة الرقمية", subtitle = "روابط، تسريبات، صور للوثائق", icon = Icons.Default.Description) {
        DropdownRow(
            label = "نوع الدليل",
            value = state.fields["digital_evidence_type"] ?: "",
            options = listOf(
                "" to "—",
                "leak_database" to "قاعدة تسريب",
                "social_media" to "منشور على وسائل التواصل",
                "news_article" to "مقال إخباري",
                "photo" to "صورة",
                "video" to "فيديو",
                "document" to "وثيقة",
                "other" to "آخر"
            ),
            onChange = { vm.setField("digital_evidence_type", it) }
        )
        TextFieldRow(
            label = "رابط الدليل",
            value = state.fields["digital_evidence_url"] ?: "",
            onValueChange = { vm.setField("digital_evidence_url", it) },
            keyboardType = KeyboardType.Uri,
            placeholder = "https://..."
        )
        TextFieldRow(
            label = "وصف الدليل",
            value = state.fields["digital_evidence_description"] ?: "",
            onValueChange = { vm.setField("digital_evidence_description", it) },
            singleLine = false,
            maxLines = 4
        )
        AttachmentRow(label = "لقطة شاشة (إن وُجدت)", field = "digital_evidence_screenshot", mime = "image/*", state = state, container = container, vm = vm)
    }
}

@Composable
private fun CivilRegistrySection(vm: EntryFormViewModel, state: FormState, container: AppContainer) {
    SectionCard(title = "السجل المدني", subtitle = "حالة التسجيل المدني", icon = Icons.Default.Description) {
        DropdownRow(
            label = "حالة التسجيل المدني",
            value = state.fields["civil_registry_status"] ?: "",
            options = listOf(
                "" to "—",
                "registered" to "مسجَّل",
                "deceased_registered" to "مسجَّل كمتوفى",
                "missing_registered" to "مسجَّل كمفقود",
                "not_registered" to "غير مسجَّل",
                "unknown" to "غير معروف"
            ),
            onChange = { vm.setField("civil_registry_status", it) }
        )
        TextFieldRow(
            label = "تاريخ التسجيل (yyyy-mm-dd)",
            value = state.fields["civil_registry_date"] ?: "",
            onValueChange = { vm.setField("civil_registry_date", it) }
        )
        AttachmentRow(label = "وثيقة من السجل المدني", field = "civil_registry_document", mime = "*/*", state = state, container = container, vm = vm)
    }
}
