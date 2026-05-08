package com.haqquna.app.data

import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

class EntryRepository(
    private val dao: EntryDao,
    private val converters: JsonConverters = JsonConverters()
) {

    fun observeAll(): Flow<List<HaqqunaEntry>> =
        dao.observeAll().map { rows -> rows.map { it.toEntry(converters) } }

    fun countPending(): Flow<Int> = dao.countByStatus(EntryStatus.PENDING.name)
    fun countSynced(): Flow<Int> = dao.countByStatus(EntryStatus.SYNCED.name)
    fun countFailed(): Flow<Int> = dao.countByStatus(EntryStatus.FAILED.name)

    suspend fun byUuid(uuid: String): HaqqunaEntry? = dao.byUuid(uuid)?.toEntry(converters)

    suspend fun pending(): List<HaqqunaEntry> = dao.pending().map { it.toEntry(converters) }

    suspend fun save(entry: HaqqunaEntry) {
        dao.upsert(entry.copy(updatedAt = System.currentTimeMillis()).toRow(converters))
    }

    suspend fun saveMany(entries: List<HaqqunaEntry>) {
        dao.upsertMany(entries.map { it.toRow(converters) })
    }

    suspend fun delete(uuid: String) = dao.delete(uuid)

    suspend fun deleteSynced(): Int = dao.deleteSynced()

    suspend fun existingUuids(): Set<String> = dao.allUuids().toSet()

    suspend fun markPending(uuid: String) {
        val current = dao.byUuid(uuid) ?: return
        dao.upsert(current.copy(syncStatus = EntryStatus.PENDING.name, syncError = null))
    }

    suspend fun markSyncing(uuid: String) {
        val current = dao.byUuid(uuid) ?: return
        dao.upsert(current.copy(syncStatus = EntryStatus.SYNCING.name, syncError = null))
    }

    suspend fun markSynced(uuid: String, serverId: Long?) {
        val current = dao.byUuid(uuid) ?: return
        dao.upsert(current.copy(
            syncStatus = EntryStatus.SYNCED.name,
            serverId = serverId,
            syncError = null
        ))
    }

    suspend fun markFailed(uuid: String, error: String) {
        val current = dao.byUuid(uuid) ?: return
        dao.upsert(current.copy(syncStatus = EntryStatus.FAILED.name, syncError = error))
    }
}
