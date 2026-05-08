package com.haqquna.app.data

import android.content.Context
import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase
import androidx.room.TypeConverter
import androidx.room.TypeConverters
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.flow.Flow

@Entity(tableName = "entries")
data class EntryRow(
    @PrimaryKey @ColumnInfo(name = "client_uuid") val clientUuid: String,
    @ColumnInfo(name = "created_at") val createdAt: Long,
    @ColumnInfo(name = "updated_at") val updatedAt: Long,
    @ColumnInfo(name = "sync_status") val syncStatus: String,
    @ColumnInfo(name = "server_id") val serverId: Long?,
    @ColumnInfo(name = "sync_error") val syncError: String?,
    @ColumnInfo(name = "fields_json") val fieldsJson: String,
    @ColumnInfo(name = "companions_json") val companionsJson: String,
    @ColumnInfo(name = "witnesses_json") val witnessesJson: String,
    @ColumnInfo(name = "children_json") val childrenJson: String,
    @ColumnInfo(name = "attachments_json") val attachmentsJson: String,
    @ColumnInfo(name = "display_name") val displayName: String
)

class JsonConverters {
    private val gson = Gson()
    private val mapType = object : TypeToken<Map<String, String>>() {}.type
    private val companionsType = object : TypeToken<List<Companion_>>() {}.type
    private val witnessesType = object : TypeToken<List<Witness>>() {}.type
    private val childrenType = object : TypeToken<List<Child>>() {}.type
    private val attachmentsType = object : TypeToken<List<FileAttachment>>() {}.type

    fun fieldsToJson(m: Map<String, String>): String = gson.toJson(m)
    fun fieldsFromJson(s: String?): Map<String, String> =
        if (s.isNullOrBlank()) emptyMap() else gson.fromJson(s, mapType)

    fun companionsToJson(c: List<Companion_>): String = gson.toJson(c)
    fun companionsFromJson(s: String?): List<Companion_> =
        if (s.isNullOrBlank()) emptyList() else gson.fromJson(s, companionsType)

    fun witnessesToJson(w: List<Witness>): String = gson.toJson(w)
    fun witnessesFromJson(s: String?): List<Witness> =
        if (s.isNullOrBlank()) emptyList() else gson.fromJson(s, witnessesType)

    fun childrenToJson(c: List<Child>): String = gson.toJson(c)
    fun childrenFromJson(s: String?): List<Child> =
        if (s.isNullOrBlank()) emptyList() else gson.fromJson(s, childrenType)

    fun attachmentsToJson(a: List<FileAttachment>): String = gson.toJson(a)
    fun attachmentsFromJson(s: String?): List<FileAttachment> =
        if (s.isNullOrBlank()) emptyList() else gson.fromJson(s, attachmentsType)
}

fun HaqqunaEntry.toRow(c: JsonConverters): EntryRow = EntryRow(
    clientUuid = clientUuid,
    createdAt = createdAt,
    updatedAt = updatedAt,
    syncStatus = syncStatus.name,
    serverId = serverId,
    syncError = syncError,
    fieldsJson = c.fieldsToJson(fields),
    companionsJson = c.companionsToJson(companions),
    witnessesJson = c.witnessesToJson(witnesses),
    childrenJson = c.childrenToJson(children),
    attachmentsJson = c.attachmentsToJson(attachments),
    displayName = displayName
)

fun EntryRow.toEntry(c: JsonConverters): HaqqunaEntry = HaqqunaEntry(
    clientUuid = clientUuid,
    createdAt = createdAt,
    updatedAt = updatedAt,
    syncStatus = runCatching { EntryStatus.valueOf(syncStatus) }.getOrDefault(EntryStatus.DRAFT),
    serverId = serverId,
    syncError = syncError,
    fields = c.fieldsFromJson(fieldsJson),
    companions = c.companionsFromJson(companionsJson),
    witnesses = c.witnessesFromJson(witnessesJson),
    children = c.childrenFromJson(childrenJson),
    attachments = c.attachmentsFromJson(attachmentsJson)
)

@Dao
interface EntryDao {
    @Query("SELECT * FROM entries ORDER BY updated_at DESC")
    fun observeAll(): Flow<List<EntryRow>>

    @Query("SELECT * FROM entries WHERE sync_status IN ('PENDING','FAILED') ORDER BY created_at ASC")
    suspend fun pending(): List<EntryRow>

    @Query("SELECT * FROM entries WHERE client_uuid = :uuid LIMIT 1")
    suspend fun byUuid(uuid: String): EntryRow?

    @Query("SELECT client_uuid FROM entries")
    suspend fun allUuids(): List<String>

    @Query("SELECT COUNT(*) FROM entries WHERE sync_status = :status")
    fun countByStatus(status: String): Flow<Int>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(row: EntryRow)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertMany(rows: List<EntryRow>)

    @Query("DELETE FROM entries WHERE client_uuid = :uuid")
    suspend fun delete(uuid: String)

    @Query("DELETE FROM entries WHERE sync_status = 'SYNCED'")
    suspend fun deleteSynced(): Int
}

@Database(entities = [EntryRow::class], version = 1, exportSchema = false)
abstract class HaqqunaDatabase : RoomDatabase() {
    abstract fun entries(): EntryDao

    companion object {
        @Volatile private var instance: HaqqunaDatabase? = null

        fun get(ctx: Context): HaqqunaDatabase = instance ?: synchronized(this) {
            instance ?: Room.databaseBuilder(
                ctx.applicationContext,
                HaqqunaDatabase::class.java,
                "haqquna.db"
            ).fallbackToDestructiveMigration().build().also { instance = it }
        }
    }
}
