package com.haqquna.app.ui.home

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.CloudDone
import androidx.compose.material.icons.filled.CloudUpload
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.ErrorOutline
import androidx.compose.material.icons.filled.FileUpload
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Sync
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.navigation.NavController
import com.haqquna.app.AppContainer
import com.haqquna.app.R
import com.haqquna.app.ui.Routes

@Composable
fun HomeScreen(container: AppContainer, nav: NavController) {
    val pending by container.entries.countPending().collectAsStateWithLifecycle(initialValue = 0)
    val synced by container.entries.countSynced().collectAsStateWithLifecycle(initialValue = 0)
    val failed by container.entries.countFailed().collectAsStateWithLifecycle(initialValue = 0)

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
        ) {
            CurvedHeader(pending = pending, failed = failed, onAddClick = { nav.navigate(Routes.ENTRY_NEW) })

            Spacer(Modifier.height(16.dp))

            StatsRow(pending = pending, synced = synced, failed = failed)

            Spacer(Modifier.height(8.dp))

            homeActions(pending, failed).forEach { action ->
                ActionRow(action = action, onClick = { nav.navigate(action.route) })
            }

            Spacer(Modifier.height(32.dp))
        }
    }
}

@Composable
private fun CurvedHeader(pending: Int, failed: Int, onAddClick: () -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxWidth()
            .background(
                Brush.verticalGradient(
                    listOf(
                        MaterialTheme.colorScheme.primary,
                        MaterialTheme.colorScheme.primary.copy(alpha = 0.92f),
                        MaterialTheme.colorScheme.primary.copy(alpha = 0.78f)
                    )
                ),
                shape = RoundedCornerShape(bottomStart = 36.dp, bottomEnd = 36.dp)
            )
            .statusBarsPadding()
            .padding(horizontal = 20.dp, vertical = 24.dp)
    ) {
        Column {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(
                    modifier = Modifier
                        .size(64.dp)
                        .shadow(8.dp, CircleShape)
                        .clip(CircleShape)
                        .background(Color.White),
                    contentAlignment = Alignment.Center
                ) {
                    Image(
                        painter = painterResource(id = R.drawable.logo_haqquna),
                        contentDescription = "حقنا",
                        modifier = Modifier.size(58.dp).clip(CircleShape),
                        contentScale = ContentScale.Crop
                    )
                }
                Spacer(Modifier.width(14.dp))
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        "حقنا",
                        color = MaterialTheme.colorScheme.onPrimary,
                        style = MaterialTheme.typography.headlineLarge.copy(
                            fontWeight = FontWeight.ExtraBold,
                            fontSize = 32.sp
                        )
                    )
                    Text(
                        "توثيق ميداني — يعمل بدون إنترنت",
                        color = MaterialTheme.colorScheme.onPrimary.copy(alpha = 0.85f),
                        style = MaterialTheme.typography.bodyMedium
                    )
                }
            }

            Spacer(Modifier.height(18.dp))

            StatusPill(pending = pending, failed = failed)

            Spacer(Modifier.height(16.dp))

            PrimaryAction(onAddClick = onAddClick)
        }
    }
}

@Composable
private fun StatusPill(pending: Int, failed: Int) {
    val (icon, text, accent) = when {
        failed > 0 -> Triple(Icons.Default.ErrorOutline, "$failed حالة فشلت — تحقّق من المزامنة", Color(0xFFEF4444))
        pending > 0 -> Triple(Icons.Default.Sync, "$pending حالة بانتظار المزامنة", Color(0xFFFBBF24))
        else -> Triple(Icons.Default.CloudDone, "كل البيانات متزامنة", Color(0xFF22C55E))
    }
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(50))
            .background(Color.White.copy(alpha = 0.18f))
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .size(10.dp)
                .clip(CircleShape)
                .background(accent)
        )
        Spacer(Modifier.width(8.dp))
        Icon(
            icon, null,
            tint = MaterialTheme.colorScheme.onPrimary,
            modifier = Modifier.size(18.dp)
        )
        Spacer(Modifier.width(8.dp))
        Text(
            text,
            color = MaterialTheme.colorScheme.onPrimary,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Medium
        )
    }
}

@Composable
private fun PrimaryAction(onAddClick: () -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .shadow(6.dp, RoundedCornerShape(18.dp)),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        onClick = onAddClick
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 18.dp, vertical = 16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(44.dp)
                    .clip(CircleShape)
                    .background(MaterialTheme.colorScheme.primary),
                contentAlignment = Alignment.Center
            ) {
                Icon(Icons.Default.Add, null, tint = Color.White, modifier = Modifier.size(26.dp))
            }
            Spacer(Modifier.width(14.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    "إضافة حالة جديدة",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary
                )
                Text(
                    "ابدأ توثيق حالة معتقل أو مفقود",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

@Composable
private fun StatsRow(pending: Int, synced: Int, failed: Int) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        StatTile(
            modifier = Modifier.weight(1f),
            icon = Icons.Default.Description,
            value = pending.toString(),
            label = "بانتظار المزامنة",
            color = MaterialTheme.colorScheme.tertiaryContainer,
            textColor = MaterialTheme.colorScheme.onTertiaryContainer
        )
        StatTile(
            modifier = Modifier.weight(1f),
            icon = Icons.Default.CheckCircle,
            value = synced.toString(),
            label = "تمت مزامنتها",
            color = MaterialTheme.colorScheme.secondaryContainer,
            textColor = MaterialTheme.colorScheme.onSecondaryContainer
        )
        StatTile(
            modifier = Modifier.weight(1f),
            icon = Icons.Default.ErrorOutline,
            value = failed.toString(),
            label = "فشلت",
            color = MaterialTheme.colorScheme.errorContainer,
            textColor = MaterialTheme.colorScheme.onErrorContainer
        )
    }
}

@Composable
private fun StatTile(
    modifier: Modifier,
    icon: ImageVector,
    value: String,
    label: String,
    color: Color,
    textColor: Color
) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(containerColor = color),
        shape = MaterialTheme.shapes.medium
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Icon(icon, null, tint = textColor, modifier = Modifier.size(20.dp))
            Spacer(Modifier.height(4.dp))
            Text(value, color = textColor, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text(label, color = textColor, style = MaterialTheme.typography.labelSmall)
        }
    }
}

private data class HomeAction(
    val title: String,
    val subtitle: String,
    val icon: ImageVector,
    val route: String,
    val badge: Int = 0
)

private fun homeActions(pending: Int, failed: Int): List<HomeAction> = listOf(
    HomeAction("مزامنة الحالات", "إرسال البيانات للخادم", Icons.Default.CloudUpload, Routes.SYNC, pending + failed),
    HomeAction("الحالات المحفوظة", "عرض، تعديل، حذف", Icons.Default.List, Routes.ENTRIES),
    HomeAction("استيراد JSON", "إستعادة من نسخة احتياطية", Icons.Default.FileUpload, Routes.IMPORT),
    HomeAction("الإعدادات", "حساب المزامنة والخادم", Icons.Default.Settings, Routes.SETTINGS),
    HomeAction("حول التطبيق", "المطوّر والمعلومات", Icons.Default.Info, Routes.ABOUT)
)

@Composable
private fun ActionRow(action: HomeAction, onClick: () -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 5.dp),
        shape = MaterialTheme.shapes.medium,
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp),
        onClick = onClick
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(40.dp)
                    .background(MaterialTheme.colorScheme.primaryContainer, CircleShape),
                contentAlignment = Alignment.Center
            ) {
                Icon(
                    action.icon, null,
                    tint = MaterialTheme.colorScheme.onPrimaryContainer,
                    modifier = Modifier.size(22.dp)
                )
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(action.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Text(action.subtitle, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (action.badge > 0) {
                Box(
                    modifier = Modifier
                        .background(MaterialTheme.colorScheme.error, CircleShape)
                        .padding(horizontal = 10.dp, vertical = 4.dp)
                ) {
                    Text(
                        action.badge.toString(),
                        color = MaterialTheme.colorScheme.onError,
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
        }
    }
}
