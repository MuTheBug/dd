package com.haqquna.app.ui

import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.PressInteraction
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.Close
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.DisplayMode
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import java.util.Calendar
import java.util.TimeZone

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DatePickerField(
    label: String,
    day: String,
    month: String,
    year: String,
    onDateChange: (day: String, month: String, year: String) -> Unit,
    required: Boolean = false,
    minYear: Int = 1900,
    maxYear: Int = currentYear() + 1
) {
    val display = if (year.isNotBlank() && month.isNotBlank() && day.isNotBlank()) {
        "${day.padStart(2, '0')} / ${month.padStart(2, '0')} / ${year.padStart(4, '0')}"
    } else ""

    val initialMillis = remember(day, month, year) {
        if (year.isNotBlank() && month.isNotBlank() && day.isNotBlank()) {
            runCatching {
                val cal = Calendar.getInstance(TimeZone.getTimeZone("UTC"))
                cal.set(year.toInt(), month.toInt() - 1, day.toInt(), 0, 0, 0)
                cal.set(Calendar.MILLISECOND, 0)
                cal.timeInMillis
            }.getOrNull()
        } else null
    }

    DateField(
        label = label,
        display = display,
        required = required,
        initialMillis = initialMillis,
        minYear = minYear,
        maxYear = maxYear,
        onClear = { onDateChange("", "", "") },
        onSelect = { millis ->
            val c = Calendar.getInstance(TimeZone.getTimeZone("UTC"))
            c.timeInMillis = millis
            onDateChange(
                c.get(Calendar.DAY_OF_MONTH).toString(),
                (c.get(Calendar.MONTH) + 1).toString(),
                c.get(Calendar.YEAR).toString()
            )
        }
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SingleDatePickerField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
    required: Boolean = false,
    minYear: Int = 1900,
    maxYear: Int = currentYear() + 1
) {
    val parts = value.split("-")
    val valid = parts.size == 3 && parts.all { it.isNotBlank() }
    val display = if (valid) {
        "${parts[2].padStart(2, '0')} / ${parts[1].padStart(2, '0')} / ${parts[0].padStart(4, '0')}"
    } else ""

    val initialMillis = remember(value) {
        if (valid) {
            runCatching {
                val cal = Calendar.getInstance(TimeZone.getTimeZone("UTC"))
                cal.set(parts[0].toInt(), parts[1].toInt() - 1, parts[2].toInt(), 0, 0, 0)
                cal.set(Calendar.MILLISECOND, 0)
                cal.timeInMillis
            }.getOrNull()
        } else null
    }

    DateField(
        label = label,
        display = display,
        required = required,
        initialMillis = initialMillis,
        minYear = minYear,
        maxYear = maxYear,
        onClear = { onValueChange("") },
        onSelect = { millis ->
            val c = Calendar.getInstance(TimeZone.getTimeZone("UTC"))
            c.timeInMillis = millis
            val y = c.get(Calendar.YEAR)
            val m = (c.get(Calendar.MONTH) + 1).toString().padStart(2, '0')
            val d = c.get(Calendar.DAY_OF_MONTH).toString().padStart(2, '0')
            onValueChange("$y-$m-$d")
        }
    )
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun DateField(
    label: String,
    display: String,
    required: Boolean,
    initialMillis: Long?,
    minYear: Int,
    maxYear: Int,
    onClear: () -> Unit,
    onSelect: (Long) -> Unit
) {
    var showDialog by remember { mutableStateOf(false) }
    val labelText = if (required) "$label *" else label

    val source = remember { MutableInteractionSource() }
    LaunchedEffect(source) {
        source.interactions.collect { interaction ->
            if (interaction is PressInteraction.Release) showDialog = true
        }
    }

    OutlinedTextField(
        value = display,
        onValueChange = {},
        readOnly = true,
        interactionSource = source,
        label = { Text(labelText) },
        placeholder = { Text("اضغط لاختيار التاريخ") },
        trailingIcon = {
            if (display.isNotBlank()) {
                IconButton(onClick = onClear) {
                    Icon(Icons.Default.Close, "حذف")
                }
            } else {
                Icon(
                    Icons.Default.CalendarMonth, null,
                    modifier = Modifier.padding(end = 8.dp)
                )
            }
        },
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)
    )

    if (showDialog) {
        val pickerState = rememberDatePickerState(
            initialSelectedDateMillis = initialMillis,
            yearRange = minYear..maxYear,
            initialDisplayMode = DisplayMode.Picker
        )
        DatePickerDialog(
            onDismissRequest = { showDialog = false },
            confirmButton = {
                TextButton(onClick = {
                    pickerState.selectedDateMillis?.let(onSelect)
                    showDialog = false
                }) { Text("تأكيد") }
            },
            dismissButton = {
                TextButton(onClick = { showDialog = false }) { Text("إلغاء") }
            }
        ) {
            DatePicker(state = pickerState, showModeToggle = false)
        }
    }
}

private fun currentYear(): Int = Calendar.getInstance().get(Calendar.YEAR)
