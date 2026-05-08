package com.haqquna.app

import android.app.Application
import com.haqquna.app.data.EntryRepository
import com.haqquna.app.data.HaqqunaDatabase
import com.haqquna.app.data.JsonExporter
import com.haqquna.app.data.JsonImporter
import com.haqquna.app.data.PhotoStore
import com.haqquna.app.data.SettingsStore
import com.haqquna.app.data.SyncRepository

class HaqqunaApp : Application() {

    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}

class AppContainer(app: Application) {
    val db = HaqqunaDatabase.get(app)
    val entries = EntryRepository(db.entries())
    val settings = SettingsStore(app)
    val sync = SyncRepository(app)
    val importer = JsonImporter(app)
    val exporter = JsonExporter(app)
    val photos = PhotoStore(app)
}
