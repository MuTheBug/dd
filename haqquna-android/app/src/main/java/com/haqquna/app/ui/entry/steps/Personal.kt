package com.haqquna.app.ui.entry.steps

import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.haqquna.app.AppContainer
import com.haqquna.app.ui.DatePickerField
import com.haqquna.app.ui.DropdownRow
import com.haqquna.app.ui.SectionCard
import com.haqquna.app.ui.TextFieldRow
import com.haqquna.app.ui.entry.EntryFormViewModel
import com.haqquna.app.ui.entry.FormState

@Composable
fun PersonalStep(vm: EntryFormViewModel, state: FormState, container: AppContainer) {

    SectionCard(title = "الاسم", icon = Icons.Default.Person) {
        TextFieldRow(
            label = "الاسم الأول",
            value = state.fields["first_name"] ?: "",
            onValueChange = { vm.setField("first_name", it) },
            required = true
        )
        TextFieldRow(
            label = "اسم الأب",
            value = state.fields["father_name"] ?: "",
            onValueChange = { vm.setField("father_name", it) },
            required = true
        )
        TextFieldRow(
            label = "الكنية (اسم العائلة)",
            value = state.fields["last_name"] ?: "",
            onValueChange = { vm.setField("last_name", it) },
            required = true
        )
        TextFieldRow(
            label = "اسم الأم الكامل",
            value = state.fields["mother_name"] ?: "",
            onValueChange = { vm.setField("mother_name", it) },
            required = true
        )
    }

    SectionCard(title = "الجنس وتاريخ الميلاد") {
        DropdownRow(
            label = "الجنس",
            value = state.fields["gender"] ?: "",
            options = listOf(
                "" to "-- اختر --",
                "male" to "ذكر",
                "female" to "أنثى"
            ),
            onChange = { vm.setField("gender", it) },
            required = true
        )
        DatePickerField(
            label = "تاريخ الميلاد",
            day = state.fields["birth_day"] ?: "",
            month = state.fields["birth_month"] ?: "",
            year = state.fields["birth_year"] ?: "",
            onDateChange = { d, m, y ->
                vm.setField("birth_day", d)
                vm.setField("birth_month", m)
                vm.setField("birth_year", y)
            },
            minYear = 1900
        )
    }

    SectionCard(title = "الهوية والمحافظة") {
        DropdownRow(
            label = "المحافظة",
            value = state.fields["province"] ?: "",
            options = SyrianProvinces,
            onChange = { vm.setField("province", it) },
            required = true
        )
        TextFieldRow(
            label = "الرقم الوطني",
            value = state.fields["national_id"] ?: "",
            onValueChange = { vm.setField("national_id", it.filter { c -> c.isDigit() }.take(11)) },
            keyboardType = KeyboardType.Number,
            required = true
        )
        TextFieldRow(
            label = "رقم دفتر العائلة",
            value = state.fields["family_book_number"] ?: "",
            onValueChange = { vm.setField("family_book_number", it) }
        )
        TextFieldRow(
            label = "رقم الهاتف",
            value = state.fields["phone"] ?: "",
            onValueChange = { vm.setField("phone", it) },
            keyboardType = KeyboardType.Phone
        )
        DropdownRow(
            label = "زمرة الدم",
            value = state.fields["blood_type"] ?: "",
            options = listOf(
                "" to "-- اختر --",
                "A+" to "A+", "A-" to "A-",
                "B+" to "B+", "B-" to "B-",
                "AB+" to "AB+", "AB-" to "AB-",
                "O+" to "O+", "O-" to "O-"
            ),
            onChange = { vm.setField("blood_type", it) }
        )
    }

    SectionCard(title = "الصور والوثائق") {
        AttachmentRow(
            label = "صورة شخصية",
            field = "photo",
            mime = "image/*",
            state = state,
            container = container,
            vm = vm
        )
        Spacer(Modifier.height(6.dp))
        AttachmentRow(
            label = "وثيقة هوية (PDF أو صورة)",
            field = "document",
            mime = "*/*",
            state = state,
            container = container,
            vm = vm
        )
    }
}

private val SyrianProvinces = listOf(
    "" to "-- اختر المحافظة --",
    "اللاذقية" to "اللاذقية",
    "دمشق" to "دمشق",
    "ريف دمشق" to "ريف دمشق",
    "حلب" to "حلب",
    "حمص" to "حمص",
    "حماة" to "حماة",
    "إدلب" to "إدلب",
    "درعا" to "درعا",
    "السويداء" to "السويداء",
    "القنيطرة" to "القنيطرة",
    "الرقة" to "الرقة",
    "دير الزور" to "دير الزور",
    "الحسكة" to "الحسكة",
    "طرطوس" to "طرطوس",
    "أخرى" to "أخرى"
)
