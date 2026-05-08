package com.haqquna.app.ui

import androidx.compose.runtime.Composable
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.haqquna.app.AppContainer
import com.haqquna.app.ui.entries.EntriesListScreen
import com.haqquna.app.ui.entry.EntryFormScreen
import com.haqquna.app.ui.home.HomeScreen
import com.haqquna.app.ui.imp.ImportScreen
import com.haqquna.app.ui.settings.SettingsScreen
import com.haqquna.app.ui.sync.SyncScreen

object Routes {
    const val HOME = "home"
    const val ENTRY_NEW = "entry/new"
    const val ENTRY_EDIT = "entry/{uuid}"
    fun entryEdit(uuid: String) = "entry/$uuid"
    const val ENTRIES = "entries"
    const val SYNC = "sync"
    const val SETTINGS = "settings"
    const val IMPORT = "import"
}

@Composable
fun HaqqunaRoot(container: AppContainer) {
    val nav = rememberNavController()

    NavHost(navController = nav, startDestination = Routes.HOME) {
        composable(Routes.HOME) { HomeScreen(container, nav) }
        composable(Routes.ENTRY_NEW) { EntryFormScreen(container, nav, uuid = null) }
        composable(
            Routes.ENTRY_EDIT,
            arguments = listOf(navArgument("uuid") { type = NavType.StringType })
        ) { backStack ->
            val uuid = backStack.arguments?.getString("uuid")
            EntryFormScreen(container, nav, uuid = uuid)
        }
        composable(Routes.ENTRIES) { EntriesListScreen(container, nav) }
        composable(Routes.SYNC) { SyncScreen(container, nav) }
        composable(Routes.SETTINGS) { SettingsScreen(container, nav) }
        composable(Routes.IMPORT) { ImportScreen(container, nav) }
    }
}
