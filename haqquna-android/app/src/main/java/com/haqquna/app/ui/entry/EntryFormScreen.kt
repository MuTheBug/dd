package com.haqquna.app.ui.entry

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.ArrowForward
import androidx.compose.material.icons.filled.Save
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavController
import com.haqquna.app.AppContainer
import com.haqquna.app.ui.HaqqunaTopBar
import com.haqquna.app.ui.entry.steps.AddressStep
import com.haqquna.app.ui.entry.steps.CompanionsStep
import com.haqquna.app.ui.entry.steps.NotesAndSubmitStep
import com.haqquna.app.ui.entry.steps.PersonalStep
import com.haqquna.app.ui.entry.steps.ReporterStep
import com.haqquna.app.ui.entry.steps.StatusDetailsStep
import com.haqquna.app.ui.entry.steps.WitnessesStep
import kotlinx.coroutines.launch

@Composable
fun EntryFormScreen(container: AppContainer, nav: NavController, uuid: String?) {
    val vm: EntryFormViewModel = viewModel()
    val state by vm.state.collectAsStateWithLifecycle()
    val scope = rememberCoroutineScope()

    LaunchedEffect(uuid) { vm.load(uuid) }

    var showSaveError by remember { mutableStateOf<List<ValidationError>?>(null) }
    var showSaveSuccess by remember { mutableStateOf(false) }
    var saveErrorMsg by remember { mutableStateOf<String?>(null) }

    Scaffold(
        topBar = {
            HaqqunaTopBar(
                title = if (state.existing) "تعديل حالة" else "حالة جديدة",
                subtitle = FormSteps.titles[state.currentStep],
                onBack = { nav.popBackStack() }
            )
        },
        bottomBar = {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .navigationBarsPadding()
                    .padding(horizontal = 16.dp, vertical = 12.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                if (state.currentStep > 0) {
                    OutlinedButton(onClick = { vm.prevStep() }, modifier = Modifier.weight(1f)) {
                        Icon(Icons.Default.ArrowForward, null); Spacer(Modifier.width(6.dp))
                        Text("السابق")
                    }
                }
                if (state.currentStep < FormSteps.size - 1) {
                    Button(onClick = { vm.nextStep() }, modifier = Modifier.weight(1f)) {
                        Text("التالي"); Spacer(Modifier.width(6.dp))
                        Icon(Icons.Default.ArrowBack, null)
                    }
                } else {
                    Button(
                        onClick = {
                            scope.launch {
                                when (val r = vm.save(asPending = true)) {
                                    is SaveResult.Ok -> showSaveSuccess = true
                                    is SaveResult.Invalid -> showSaveError = r.errors
                                    is SaveResult.Error -> saveErrorMsg = r.message
                                }
                            }
                        },
                        modifier = Modifier.weight(1f),
                        colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.secondary)
                    ) {
                        Icon(Icons.Default.Save, null); Spacer(Modifier.width(6.dp))
                        Text("حفظ ومزامنة لاحقاً")
                    }
                }
            }
        }
    ) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding)) {
            StepIndicator(state.currentStep, vm::goTo)
            HorizontalDivider()
            LinearProgressIndicator(
                progress = { (state.currentStep + 1f) / FormSteps.size },
                modifier = Modifier.fillMaxWidth().height(3.dp)
            )
            val scrollState = rememberScrollState()
            LaunchedEffect(state.currentStep) { scrollState.scrollTo(0) }
            Box(modifier = Modifier.weight(1f)) {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .verticalScroll(scrollState)
                        .padding(vertical = 8.dp)
                ) {
                    when (state.currentStep) {
                        0 -> ReporterStep(vm, state)
                        1 -> PersonalStep(vm, state, container)
                        2 -> StatusDetailsStep(vm, state, container)
                        3 -> CompanionsStep(vm, state)
                        4 -> WitnessesStep(vm, state)
                        5 -> AddressStep(vm, state)
                        else -> NotesAndSubmitStep(vm, state)
                    }
                    Spacer(Modifier.height(80.dp))
                }
            }
        }
    }

    if (showSaveError != null) {
        val errs = showSaveError!!
        AlertDialog(
            onDismissRequest = { showSaveError = null },
            title = { Text("بيانات ناقصة") },
            text = {
                Column {
                    Text("الحقول التالية مطلوبة:", fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(6.dp))
                    errs.forEach {
                        Text("• ${it.label} (الخطوة: ${FormSteps.titles[it.step]})")
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = {
                    val firstStep = errs.minOf { it.step }
                    showSaveError = null
                    vm.goTo(firstStep)
                }) { Text("الذهاب للخطوة") }
            },
            dismissButton = { TextButton(onClick = { showSaveError = null }) { Text("إغلاق") } }
        )
    }

    if (showSaveSuccess) {
        AlertDialog(
            onDismissRequest = { showSaveSuccess = false; nav.popBackStack() },
            title = { Text("تم الحفظ") },
            text = { Text("تم حفظ الحالة بنجاح. ستتم مزامنتها عند تشغيل المزامنة من الصفحة الرئيسية.") },
            confirmButton = {
                TextButton(onClick = { showSaveSuccess = false; nav.popBackStack() }) { Text("حسناً") }
            }
        )
    }

    saveErrorMsg?.let { msg ->
        AlertDialog(
            onDismissRequest = { saveErrorMsg = null },
            title = { Text("فشل الحفظ") },
            text = { Text(msg) },
            confirmButton = { TextButton(onClick = { saveErrorMsg = null }) { Text("حسناً") } }
        )
    }
}

@Composable
private fun StepIndicator(current: Int, onSelect: (Int) -> Unit) {
    LazyRow(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        itemsIndexed(FormSteps.titles) { i, title ->
            FilterChip(
                selected = i == current,
                onClick = { onSelect(i) },
                label = { Text("${i + 1}. $title") }
            )
        }
    }
}
