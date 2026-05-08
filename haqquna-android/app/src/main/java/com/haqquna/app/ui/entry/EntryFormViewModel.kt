package com.haqquna.app.ui.entry

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.haqquna.app.HaqqunaApp
import com.haqquna.app.data.Child
import com.haqquna.app.data.Companion_
import com.haqquna.app.data.EntryStatus
import com.haqquna.app.data.FileAttachment
import com.haqquna.app.data.HaqqunaEntry
import com.haqquna.app.data.Witness
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.UUID

class EntryFormViewModel(app: Application) : AndroidViewModel(app) {

    private val container = (app as HaqqunaApp).container

    private val _state = MutableStateFlow(FormState())
    val state: StateFlow<FormState> = _state.asStateFlow()

    private var loaded = false

    fun load(uuid: String?) {
        if (loaded) return
        loaded = true

        viewModelScope.launch {
            if (uuid == null) {
                val snapshot = container.settings.snapshot()
                _state.update { it.copy(fields = it.fields + ("collector_name" to snapshot.collector)) }
            } else {
                container.entries.byUuid(uuid)?.let { e ->
                    _state.update {
                        FormState(
                            uuid = e.clientUuid,
                            existing = true,
                            fields = e.fields,
                            companions = e.companions,
                            witnesses = e.witnesses,
                            children = e.children,
                            attachments = e.attachments,
                            currentStep = 0,
                            syncStatus = e.syncStatus
                        )
                    }
                }
            }
        }
    }

    fun setField(key: String, value: String) {
        _state.update { it.copy(fields = it.fields + (key to value)) }
    }

    fun goTo(step: Int) {
        _state.update { it.copy(currentStep = step.coerceIn(0, FormSteps.size - 1)) }
    }

    fun nextStep() {
        _state.update { it.copy(currentStep = (it.currentStep + 1).coerceAtMost(FormSteps.size - 1)) }
    }

    fun prevStep() {
        _state.update { it.copy(currentStep = (it.currentStep - 1).coerceAtLeast(0)) }
    }

    // Companions
    fun addCompanion() = _state.update { it.copy(companions = it.companions + Companion_()) }
    fun removeCompanion(idx: Int) = _state.update {
        it.copy(companions = it.companions.toMutableList().also { l -> l.removeAt(idx) })
    }
    fun updateCompanion(idx: Int, c: Companion_) = _state.update {
        it.copy(companions = it.companions.toMutableList().also { l -> l[idx] = c })
    }

    // Witnesses
    fun addWitness() = _state.update { it.copy(witnesses = it.witnesses + Witness()) }
    fun removeWitness(idx: Int) = _state.update {
        it.copy(witnesses = it.witnesses.toMutableList().also { l -> l.removeAt(idx) })
    }
    fun updateWitness(idx: Int, w: Witness) = _state.update {
        it.copy(witnesses = it.witnesses.toMutableList().also { l -> l[idx] = w })
    }

    // Children
    fun addChild() = _state.update { it.copy(children = it.children + Child()) }
    fun removeChild(idx: Int) = _state.update {
        it.copy(children = it.children.toMutableList().also { l -> l.removeAt(idx) })
    }
    fun updateChild(idx: Int, c: Child) = _state.update {
        it.copy(children = it.children.toMutableList().also { l -> l[idx] = c })
    }

    // Attachments
    fun addAttachment(att: FileAttachment) {
        val replacingFor = att.field
        _state.update { st ->
            val without = st.attachments.filter { it.field != replacingFor }
            for (old in st.attachments.filter { it.field == replacingFor }) {
                container.photos.delete(old)
            }
            st.copy(attachments = without + att)
        }
    }

    fun removeAttachment(field: String) {
        _state.update { st ->
            for (old in st.attachments.filter { it.field == field }) container.photos.delete(old)
            st.copy(attachments = st.attachments.filter { it.field != field })
        }
    }

    fun validate(): List<ValidationError> {
        val errors = mutableListOf<ValidationError>()
        val f = _state.value.fields
        fun req(key: String, label: String, step: Int) {
            if (f[key].isNullOrBlank()) errors += ValidationError(step, key, label)
        }
        // Step 0 — Reporter & Classification
        req("status", "تصنيف الحالة", 0)
        req("reporter_name", "اسم المُبلِّغ", 0)
        req("reporter_relation", "صلة المُبلِّغ", 0)
        req("source_type", "نوع المصدر", 0)
        // Step 1 — Personal
        req("first_name", "الاسم الأول", 1)
        req("father_name", "اسم الأب", 1)
        req("last_name", "اسم العائلة", 1)
        req("mother_name", "اسم الأم", 1)
        req("gender", "الجنس", 1)
        req("province", "المحافظة", 1)
        req("national_id", "الرقم الوطني", 1)
        // Step 2 — Arrest / Status details
        req("arrest_authority", "الجهة المعتقِلة", 2)
        req("arrest_reason", "سبب الاعتقال", 2)
        // Step 5 — Address & Housing
        req("address", "العنوان الحالي", 5)
        req("housing_type", "نوع السكن", 5)
        return errors
    }

    suspend fun save(asPending: Boolean): SaveResult {
        val errors = validate()
        if (errors.isNotEmpty()) return SaveResult.Invalid(errors)

        val st = _state.value
        val entry = HaqqunaEntry(
            clientUuid = st.uuid ?: UUID.randomUUID().toString(),
            createdAt = System.currentTimeMillis(),
            updatedAt = System.currentTimeMillis(),
            syncStatus = if (asPending) EntryStatus.PENDING else EntryStatus.DRAFT,
            fields = st.fields,
            companions = st.companions.filter { it.name.isNotBlank() },
            witnesses = st.witnesses.filter { it.name.isNotBlank() },
            children = st.children.filter { it.name.isNotBlank() },
            attachments = st.attachments
        )
        return runCatching {
            container.entries.save(entry)
            SaveResult.Ok(entry.clientUuid)
        }.getOrElse { SaveResult.Error(it.message ?: "خطأ في الحفظ") }
    }
}

data class FormState(
    val uuid: String? = null,
    val existing: Boolean = false,
    val fields: Map<String, String> = emptyMap(),
    val companions: List<Companion_> = emptyList(),
    val witnesses: List<Witness> = emptyList(),
    val children: List<Child> = emptyList(),
    val attachments: List<FileAttachment> = emptyList(),
    val currentStep: Int = 0,
    val syncStatus: EntryStatus = EntryStatus.DRAFT
)

data class ValidationError(val step: Int, val field: String, val label: String)

sealed interface SaveResult {
    data class Ok(val uuid: String) : SaveResult
    data class Invalid(val errors: List<ValidationError>) : SaveResult
    data class Error(val message: String) : SaveResult
}

object FormSteps {
    val titles = listOf(
        "الحالة والمُبلِّغ",
        "البيانات الشخصية",
        "تفاصيل الحالة",
        "المرافقون",
        "الشهود",
        "العائلة والعنوان",
        "ملاحظات وحفظ"
    )
    val size = titles.size
}
