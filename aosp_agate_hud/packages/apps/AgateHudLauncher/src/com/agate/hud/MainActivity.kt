package com.agate.hud

import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas as AndroidCanvas
import android.graphics.RuntimeShader
import android.graphics.drawable.BitmapDrawable
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.ShaderBrush
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat
import com.agate.hud.agent.AppEntry
import com.agate.hud.agent.HudAgentEngine
import com.agate.hud.data.SystemTelemetry
import com.agate.hud.data.TelemetrySnapshot
import com.agate.hud.ui.HudShaders
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private val HudObsidian = Color(0xFF04070D)
private val HudGlass = Color(0xCC0A111D)
private val HudCyan = Color(0xFF00E5FF)
private val HudAmber = Color(0xFFFF9F1C)
private val HudEmerald = Color(0xFF00E599)
private val HudCrimson = Color(0xFFFF4D6D)
private val HudText = Color(0xFFEAF3FF)
private val HudMuted = Color(0xFF7B90AB)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        val telemetry = SystemTelemetry(this)
        val agent = HudAgentEngine(this, telemetry)

        setContent {
            AgateCockpitApp(telemetry, agent)
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        // Launcher ignores back on home screen
    }
}

@Composable
fun AgateCockpitApp(telemetry: SystemTelemetry, agent: HudAgentEngine) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    var snap by remember { mutableStateOf(TelemetrySnapshot()) }
    var apps by remember { mutableStateOf<List<AppEntry>>(emptyList()) }
    var timeStr by remember { mutableStateOf("00:00:00") }
    var dateStr by remember { mutableStateOf("") }
    var gpuTime by remember { mutableStateOf(0f) }

    var agentInput by remember { mutableStateOf("") }
    var agentReply by remember { mutableStateOf("Agate HUD Kokpit hazır. Komut yazabilir veya kadranlara dokunabilirsin.") }
    var agentBadge by remember { mutableStateOf("AGATE AI") }
    var showDrawer by remember { mutableStateOf(false) }
    var showAgentConfig by remember { mutableStateOf(false) }
    var drawerFilter by remember { mutableStateOf("") }

    // Poll telemetry every 1s & load apps
    LaunchedEffect(Unit) {
        apps = agent.loadLaunchableApps()
        val tf = SimpleDateFormat("HH:mm:ss", Locale("tr", "TR"))
        val df = SimpleDateFormat("dd MMM · EEE", Locale("tr", "TR"))
        while (true) {
            snap = telemetry.readSnapshot()
            val now = Date()
            timeStr = tf.format(now)
            dateStr = df.format(now).uppercase(Locale("tr", "TR"))
            delay(1000)
        }
    }

    // Smooth 60/120Hz GPU shader clock via Compose frame callback
    LaunchedEffect(Unit) {
        val startNs = withFrameNanos { it }
        while (true) {
            withFrameNanos { nowNs ->
                gpuTime = (nowNs - startNs) / 1_000_000_000f
            }
        }
    }

    val bgShader = remember { RuntimeShader(HudShaders.COCKPIT_BACKGROUND_AGSL) }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(HudObsidian)
    ) {
        // 1. Full-screen GPU AGSL Cockpit Horizon & Plasma Shader
        Canvas(modifier = Modifier.fillMaxSize()) {
            bgShader.setFloatUniform("uResolution", size.width, size.height)
            bgShader.setFloatUniform("uTime", gpuTime)
            bgShader.setFloatUniform("uCpuLoad", (snap.cpuPct / 100f).coerceIn(0f, 1f))
            bgShader.setFloatUniform("uAccentMix", if (snap.chargeCutoffActive) 0.55f else 0.12f)
            drawRect(brush = ShaderBrush(bgShader))
        }

        // 2. Main Automotive i-Cockpit HUD Layout
        Column(
            modifier = Modifier
                .fillMaxSize()
                .statusBarsPadding()
                .navigationBarsPadding()
                .padding(horizontal = 16.dp, vertical = 10.dp),
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            // TOP HUD HEADER BAR (Clock + Date + Live Sensors)
            TopHudBar(
                timeStr = timeStr,
                dateStr = dateStr,
                snap = snap,
                onSettingsClick = { showAgentConfig = true }
            )

            Spacer(Modifier.height(10.dp))

            // DUAL GPU RADIAL COCKPIT GAUGES (Mercedes / BMW / Peugeot 508 style)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(176.dp),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                GpuRadialGaugeCard(
                    modifier = Modifier.weight(1f).fillMaxHeight(),
                    title = "ENERJİ & PİL",
                    valueText = "${snap.batteryPct}%",
                    subText = if (snap.chargeCutoffActive) "⛔ %70 LİMİTTE" else "${snap.batteryMa} mA · ${"%.1f".format(snap.batteryTempC)}°C",
                    progress = snap.batteryPct / 100f,
                    gpuTime = gpuTime,
                    startCol = if (snap.chargeCutoffActive) HudAmber else HudEmerald,
                    endCol = HudCyan,
                    onClick = {
                        val next = !snap.chargeLimitEnabled
                        telemetry.setChargeLimitEnabled(next)
                        snap = telemetry.readSnapshot()
                        agentReply = if (next) "Şarj kesici %70 aktif edildi." else "Şarj limiti kapatıldı (%100 izinli)."
                        agentBadge = "POWER"
                    }
                )

                GpuRadialGaugeCard(
                    modifier = Modifier.weight(1f).fillMaxHeight(),
                    title = "MT6893 · MALI",
                    valueText = "${snap.cpuPct.toInt()}%",
                    subText = "${"%.1f".format(snap.socTempC)}°C · ${snap.ramUsedMb / 1000f}".take(16) + "G RAM",
                    progress = (snap.cpuPct / 100f).coerceIn(0.05f, 1f),
                    gpuTime = gpuTime,
                    startCol = HudCyan,
                    endCol = if (snap.socTempC > 62f) HudCrimson else HudAmber,
                    onClick = {
                        agentReply = "SoC: ${"%.1f".format(snap.socTempC)}°C · GPU ${snap.gpuFreqMhz} MHz · RAM ${snap.ramUsedMb}/${snap.ramTotalMb} MB"
                        agentBadge = "TELEMETRY"
                    }
                )
            }

            Spacer(Modifier.height(10.dp))

            // CENTER AI AGENT COMMAND CAPSULE
            AgentHudCapsule(
                input = agentInput,
                onInputChange = { agentInput = it },
                reply = agentReply,
                badge = agentBadge,
                onSend = {
                    val cmd = agentInput
                    agentInput = ""
                    scope.launch {
                        val res = agent.handleCommand(cmd, snap, apps)
                        agentReply = res.text
                        res.actionBadge?.let { agentBadge = it }
                    }
                },
                onQuickCmd = { cmd ->
                    scope.launch {
                        val res = agent.handleCommand(cmd, snap, apps)
                        agentReply = res.text
                        res.actionBadge?.let { agentBadge = it }
                    }
                }
            )

            Spacer(Modifier.height(10.dp))

            // DYNAMIC HORIZONTAL COCKPIT WIDGET DECK (Swipeable Modules)
            DynamicWidgetDeck(
                snap = snap,
                context = context,
                onToggleLimit = {
                    val next = !snap.chargeLimitEnabled
                    telemetry.setChargeLimitEnabled(next)
                    snap = telemetry.readSnapshot()
                }
            )

            Spacer(Modifier.height(10.dp))

            // BOTTOM GLASS DOCK + APP DRAWER TRIGGER
            BottomCockpitDock(
                apps = apps,
                context = context,
                onOpenDrawer = { showDrawer = true }
            )
        }

        // APP DRAWER OVERLAY
        AnimatedVisibility(
            visible = showDrawer,
            enter = fadeIn(),
            exit = fadeOut()
        ) {
            AppDrawerOverlay(
                apps = apps,
                filter = drawerFilter,
                onFilterChange = { drawerFilter = it },
                onLaunch = { app ->
                    showDrawer = false
                    context.startActivity(app.launchIntent)
                },
                onClose = { showDrawer = false }
            )
        }

        // AGENT LLM ENDPOINT SETTINGS DIALOG
        if (showAgentConfig) {
            AgentConfigDialog(
                agent = agent,
                onDismiss = { showAgentConfig = false }
            )
        }
    }
}

@Composable
private fun TopHudBar(
    timeStr: String,
    dateStr: String,
    snap: TelemetrySnapshot,
    onSettingsClick: () -> Unit,
) {
    Surface(
        color = HudGlass,
        shape = RoundedCornerShape(16.dp),
        border = BorderStroke(1.dp, HudCyan.copy(alpha = 0.25f)),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Column {
                Text(
                    text = timeStr,
                    color = HudText,
                    fontSize = 26.sp,
                    fontWeight = FontWeight.Light,
                    fontFamily = FontFamily.Monospace,
                    letterSpacing = 1.5.sp
                )
                Text(
                    text = dateStr,
                    color = HudCyan,
                    fontSize = 11.sp,
                    fontWeight = FontWeight.SemiBold,
                    letterSpacing = 1.8.sp
                )
            }

            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                HudMiniChip(
                    icon = Icons.Rounded.Wifi,
                    text = if (snap.wifiConnected) "${snap.wifiRssiDbm}dBm" else "OFF",
                    tint = if (snap.wifiConnected) HudEmerald else HudMuted
                )
                HudMiniChip(
                    icon = Icons.Rounded.Thermostat,
                    text = "${snap.socTempC.toInt()}°C",
                    tint = if (snap.socTempC > 62f) HudCrimson else HudAmber
                )
                IconButton(onClick = onSettingsClick, modifier = Modifier.size(32.dp)) {
                    Icon(Icons.Rounded.Tune, contentDescription = "Agent Config", tint = HudCyan, modifier = Modifier.size(18.dp))
                }
            }
        }
    }
}

@Composable
private fun HudMiniChip(icon: ImageVector, text: String, tint: Color) {
    Row(
        modifier = Modifier
            .clip(RoundedCornerShape(10.dp))
            .background(Color(0xFF0E1828))
            .border(1.dp, tint.copy(alpha = 0.35f), RoundedCornerShape(10.dp))
            .padding(horizontal = 8.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(13.dp))
        Text(text, color = tint, fontSize = 11.sp, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun GpuRadialGaugeCard(
    modifier: Modifier,
    title: String,
    valueText: String,
    subText: String,
    progress: Float,
    gpuTime: Float,
    startCol: Color,
    endCol: Color,
    onClick: () -> Unit,
) {
    val ringShader = remember { RuntimeShader(HudShaders.RADIAL_GAUGE_AGSL) }
    Surface(
        color = HudGlass,
        shape = RoundedCornerShape(20.dp),
        border = BorderStroke(1.dp, startCol.copy(alpha = 0.32f)),
        modifier = modifier.clickable(onClick = onClick)
    ) {
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Canvas(modifier = Modifier.fillMaxSize().padding(6.dp)) {
                ringShader.setFloatUniform("uSize", size.width, size.height)
                ringShader.setFloatUniform("uProgress", progress.coerceIn(0f, 1f))
                ringShader.setFloatUniform("uTime", gpuTime)
                ringShader.setFloatUniform("uStartColor", startCol.red, startCol.green, startCol.blue)
                ringShader.setFloatUniform("uEndColor", endCol.red, endCol.green, endCol.blue)
                drawRect(brush = ShaderBrush(ringShader))
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Text(title, color = HudMuted, fontSize = 9.5.sp, letterSpacing = 1.6.sp, fontWeight = FontWeight.Bold)
                Text(
                    valueText,
                    color = HudText,
                    fontSize = 27.sp,
                    fontWeight = FontWeight.SemiBold,
                    fontFamily = FontFamily.Monospace
                )
                Text(
                    subText,
                    color = startCol,
                    fontSize = 10.sp,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.padding(horizontal = 10.dp)
                )
            }
        }
    }
}

@Composable
private fun AgentHudCapsule(
    input: String,
    onInputChange: (String) -> Unit,
    reply: String,
    badge: String,
    onSend: () -> Unit,
    onQuickCmd: (String) -> Unit,
) {
    Surface(
        color = HudGlass,
        shape = RoundedCornerShape(18.dp),
        border = BorderStroke(1.dp, HudCyan.copy(alpha = 0.38f)),
        modifier = Modifier.fillMaxWidth()
    ) {
        Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(6.dp))
                        .background(HudCyan.copy(alpha = 0.16f))
                        .border(1.dp, HudCyan.copy(alpha = 0.45f), RoundedCornerShape(6.dp))
                        .padding(horizontal = 7.dp, vertical = 2.dp)
                ) {
                    Text(badge, color = HudCyan, fontSize = 10.sp, fontFamily = FontFamily.Monospace, fontWeight = FontWeight.Bold)
                }
                Text(
                    text = reply,
                    color = HudText,
                    fontSize = 12.5.sp,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f)
                )
            }

            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(Color(0xFF060B14))
                    .border(1.dp, Color(0xFF1B2B42), RoundedCornerShape(12.dp))
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(Icons.Rounded.AutoAwesome, contentDescription = null, tint = HudCyan, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Box(modifier = Modifier.weight(1f)) {
                    if (input.isEmpty()) {
                        Text("Agent komutu yaz ('şarjı 70 yap', 'ayarlar', 'durum')...", color = HudMuted, fontSize = 12.5.sp)
                    }
                    BasicTextField(
                        value = input,
                        onValueChange = onInputChange,
                        singleLine = true,
                        textStyle = TextStyle(color = HudText, fontSize = 13.sp),
                        cursorBrush = SolidColor(HudCyan),
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                        keyboardActions = KeyboardActions(onSend = { onSend() }),
                        modifier = Modifier.fillMaxWidth()
                    )
                }
                IconButton(onClick = onSend, modifier = Modifier.size(28.dp)) {
                    Icon(Icons.Rounded.ArrowForward, contentDescription = "Send", tint = HudCyan, modifier = Modifier.size(18.dp))
                }
            }

            LazyRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                val quick = listOf(
                    Triple(Icons.Rounded.Bolt, "%70 Limit", "şarjı 70 yap"),
                    Triple(Icons.Rounded.Analytics, "Durum", "sistem durumu"),
                    Triple(Icons.Rounded.Settings, "Ayarlar", "ayarlar"),
                    Triple(Icons.Rounded.Wifi, "Wi-Fi", "wifi"),
                    Triple(Icons.Rounded.Public, "Tarayıcı", "tarayıcı aç")
                )
                items(quick) { (ico, label, cmd) ->
                    Surface(
                        color = Color(0xFF0E1726),
                        shape = RoundedCornerShape(8.dp),
                        border = BorderStroke(1.dp, Color(0xFF21344F)),
                        modifier = Modifier.clickable { onQuickCmd(cmd) }
                    ) {
                        Row(
                            modifier = Modifier.padding(horizontal = 9.dp, vertical = 5.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(4.dp)
                        ) {
                            Icon(ico, contentDescription = null, tint = HudCyan, modifier = Modifier.size(13.dp))
                            Text(label, color = HudText, fontSize = 11.sp)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun DynamicWidgetDeck(
    snap: TelemetrySnapshot,
    context: Context,
    onToggleLimit: () -> Unit,
) {
    LazyRow(
        horizontalArrangement = Arrangement.spacedBy(10.dp),
        modifier = Modifier.fillMaxWidth().height(112.dp)
    ) {
        // Widget 1: 8-Core CPU Spark Bars (GPU Canvas)
        item {
            Surface(
                color = HudGlass,
                shape = RoundedCornerShape(16.dp),
                border = BorderStroke(1.dp, Color(0xFF1D3048)),
                modifier = Modifier.width(210.dp).fillMaxHeight()
            ) {
                Column(modifier = Modifier.padding(11.dp), verticalArrangement = Arrangement.SpaceBetween) {
                    Text("8-CORE TELEMETRY", color = HudCyan, fontSize = 10.sp, letterSpacing = 1.4.sp, fontWeight = FontWeight.Bold)
                    Canvas(modifier = Modifier.fillMaxWidth().height(54.dp)) {
                        val count = snap.coreLoads.size.coerceAtLeast(1)
                        val gap = 6.dp.toPx()
                        val barW = (size.width - gap * (count - 1)) / count
                        snap.coreLoads.forEachIndexed { idx, pct ->
                            val x = idx * (barW + gap)
                            val frac = (pct / 100f).coerceIn(0.06f, 1f)
                            val barH = size.height * frac
                            drawRect(color = Color(0xFF111C2D), topLeft = Offset(x, 0f), size = Size(barW, size.height))
                            drawRect(
                                brush = Brush.verticalGradient(listOf(if (pct > 75f) HudAmber else HudCyan, Color(0xFF005B7F))),
                                topLeft = Offset(x, size.height - barH),
                                size = Size(barW, barH)
                            )
                        }
                    }
                    Text("RAM ${snap.ramUsedMb}/${snap.ramTotalMb} MB", color = HudMuted, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                }
            }
        }

        // Widget 2: Power & Charge Guard Module
        item {
            Surface(
                color = HudGlass,
                shape = RoundedCornerShape(16.dp),
                border = BorderStroke(1.dp, (if (snap.chargeLimitEnabled) HudEmerald else HudAmber).copy(alpha = 0.45f)),
                modifier = Modifier.width(190.dp).fillMaxHeight().clickable(onClick = onToggleLimit)
            ) {
                Column(modifier = Modifier.padding(11.dp), verticalArrangement = Arrangement.SpaceBetween) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                        Text("BATARYA KORUMA", color = HudAmber, fontSize = 10.sp, letterSpacing = 1.2.sp, fontWeight = FontWeight.Bold)
                        Icon(Icons.Rounded.BatteryChargingFull, contentDescription = null, tint = if (snap.chargeLimitEnabled) HudEmerald else HudMuted, modifier = Modifier.size(16.dp))
                    }
                    Text(
                        if (snap.chargeLimitEnabled) "%70 KESİCİ AKTİF" else "SINIR KAPALI (%100)",
                        color = if (snap.chargeLimitEnabled) HudEmerald else HudText,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Text("Durum: ${if (snap.chargeCutoffActive) "Şarj Durduruldu" else if (snap.charging) "Şarj Oluyor" else "Pil Modu"}", color = HudMuted, fontSize = 10.5.sp)
                }
            }
        }

        // Widget 3: Quick Cockpit Switches
        item {
            Surface(
                color = HudGlass,
                shape = RoundedCornerShape(16.dp),
                border = BorderStroke(1.dp, Color(0xFF1D3048)),
                modifier = Modifier.width(175.dp).fillMaxHeight()
            ) {
                Column(modifier = Modifier.padding(11.dp), verticalArrangement = Arrangement.SpaceBetween) {
                    Text("HIZLI ARAÇLAR", color = HudCyan, fontSize = 10.sp, letterSpacing = 1.2.sp, fontWeight = FontWeight.Bold)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        QuickMiniIcon(Icons.Rounded.Settings) {
                            context.startActivity(Intent(Settings.ACTION_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                        }
                        QuickMiniIcon(Icons.Rounded.Wifi) {
                            context.startActivity(Intent(Settings.Panel.ACTION_WIFI).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                        }
                        QuickMiniIcon(Icons.Rounded.Brightness6) {
                            context.startActivity(Intent(Settings.ACTION_DISPLAY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                        }
                    }
                    Text("120Hz · Mali-G77", color = HudMuted, fontSize = 10.sp, fontFamily = FontFamily.Monospace)
                }
            }
        }
    }
}

@Composable
private fun QuickMiniIcon(icon: ImageVector, onClick: () -> Unit) {
    Box(
        modifier = Modifier
            .size(38.dp)
            .clip(RoundedCornerShape(10.dp))
            .background(Color(0xFF0E1828))
            .border(1.dp, HudCyan.copy(alpha = 0.3f), RoundedCornerShape(10.dp))
            .clickable(onClick = onClick),
        contentAlignment = Alignment.Center
    ) {
        Icon(icon, contentDescription = null, tint = HudText, modifier = Modifier.size(19.dp))
    }
}

@Composable
private fun rememberAppIcon(pkg: String): ImageBitmap? {
    val ctx = LocalContext.current
    return remember(pkg) {
        try {
            val d = ctx.packageManager.getApplicationIcon(pkg)
            val bmp = if (d is BitmapDrawable && d.bitmap != null) {
                d.bitmap
            } else {
                val b = Bitmap.createBitmap(96, 96, Bitmap.Config.ARGB_8888)
                val c = AndroidCanvas(b)
                d.setBounds(0, 0, c.width, c.height)
                d.draw(c)
                b
            }
            bmp.asImageBitmap()
        } catch (_: Throwable) {
            null
        }
    }
}

@Composable
private fun BottomCockpitDock(
    apps: List<AppEntry>,
    context: Context,
    onOpenDrawer: () -> Unit,
) {
    Surface(
        color = HudGlass,
        shape = RoundedCornerShape(20.dp),
        border = BorderStroke(1.dp, HudCyan.copy(alpha = 0.25f)),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 9.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceAround
        ) {
            val dockApps = apps.take(4)
            dockApps.forEach { app ->
                val iconBmp = rememberAppIcon(app.packageName)
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    modifier = Modifier
                        .clip(RoundedCornerShape(12.dp))
                        .clickable { context.startActivity(app.launchIntent) }
                        .padding(horizontal = 8.dp, vertical = 4.dp)
                ) {
                    Box(
                        modifier = Modifier
                            .size(38.dp)
                            .clip(CircleShape)
                            .background(Color(0xFF101C2E))
                            .border(1.dp, HudCyan.copy(alpha = 0.4f), CircleShape),
                        contentAlignment = Alignment.Center
                    ) {
                        if (iconBmp != null) {
                            Image(bitmap = iconBmp, contentDescription = app.label, modifier = Modifier.size(26.dp).clip(CircleShape))
                        } else {
                            Text(app.label.take(2).uppercase(), color = HudCyan, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                    Spacer(Modifier.height(3.dp))
                    Text(app.label, color = HudText, fontSize = 10.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.widthIn(max = 58.dp))
                }
            }

            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier
                    .clip(RoundedCornerShape(12.dp))
                    .clickable(onClick = onOpenDrawer)
                    .padding(horizontal = 10.dp, vertical = 4.dp)
            ) {
                Box(
                    modifier = Modifier
                        .size(36.dp)
                        .clip(CircleShape)
                        .background(HudCyan.copy(alpha = 0.18f))
                        .border(1.dp, HudCyan, CircleShape),
                    contentAlignment = Alignment.Center
                ) {
                    Icon(Icons.Rounded.Apps, contentDescription = "Apps", tint = HudCyan, modifier = Modifier.size(20.dp))
                }
                Spacer(Modifier.height(3.dp))
                Text("Uygulamalar", color = HudCyan, fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun AppDrawerOverlay(
    apps: List<AppEntry>,
    filter: String,
    onFilterChange: (String) -> Unit,
    onLaunch: (AppEntry) -> Unit,
    onClose: () -> Unit,
) {
    val filtered = remember(apps, filter) {
        if (filter.isBlank()) apps else apps.filter { it.label.contains(filter, ignoreCase = true) }
    }
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xEB04070D))
            .statusBarsPadding()
            .navigationBarsPadding()
            .padding(16.dp)
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Text("AGATE UYGULAMALAR", color = HudCyan, fontSize = 15.sp, letterSpacing = 2.sp, fontWeight = FontWeight.Bold)
                IconButton(onClick = onClose) {
                    Icon(Icons.Rounded.Close, contentDescription = "Close", tint = HudText)
                }
            }

            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(12.dp))
                    .background(Color(0xFF0C1422))
                    .border(1.dp, HudCyan.copy(alpha = 0.35f), RoundedCornerShape(12.dp))
                    .padding(horizontal = 12.dp, vertical = 9.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(Icons.Rounded.Search, contentDescription = null, tint = HudCyan, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Box(modifier = Modifier.weight(1f)) {
                    if (filter.isEmpty()) Text("Uygulama ara...", color = HudMuted, fontSize = 13.sp)
                    BasicTextField(
                        value = filter,
                        onValueChange = onFilterChange,
                        singleLine = true,
                        textStyle = TextStyle(color = HudText, fontSize = 13.5.sp),
                        cursorBrush = SolidColor(HudCyan),
                        modifier = Modifier.fillMaxWidth()
                    )
                }
            }

            LazyVerticalGrid(
                columns = GridCells.Fixed(4),
                verticalArrangement = Arrangement.spacedBy(14.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                modifier = Modifier.weight(1f)
            ) {
                items(filtered) { app ->
                    val iconBmp = rememberAppIcon(app.packageName)
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        modifier = Modifier
                            .clip(RoundedCornerShape(14.dp))
                            .clickable { onLaunch(app) }
                            .padding(vertical = 8.dp, horizontal = 4.dp)
                    ) {
                        Box(
                            modifier = Modifier
                                .size(50.dp)
                                .clip(RoundedCornerShape(14.dp))
                                .background(Color(0xFF0E1929))
                                .border(1.dp, HudCyan.copy(alpha = 0.35f), RoundedCornerShape(14.dp)),
                            contentAlignment = Alignment.Center
                        ) {
                            if (iconBmp != null) {
                                Image(bitmap = iconBmp, contentDescription = app.label, modifier = Modifier.size(34.dp).clip(RoundedCornerShape(9.dp)))
                            } else {
                                Text(app.label.take(2).uppercase(), color = HudCyan, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                            }
                        }
                        Spacer(Modifier.height(6.dp))
                        Text(app.label, color = HudText, fontSize = 11.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AgentConfigDialog(agent: HudAgentEngine, onDismiss: () -> Unit) {
    var ep by remember { mutableStateOf(agent.llmEndpoint) }
    var model by remember { mutableStateOf(agent.llmModel) }
    var key by remember { mutableStateOf(agent.llmApiKey) }

    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Color(0xFF0A111D),
        titleContentColor = HudCyan,
        textContentColor = HudText,
        title = { Text("Agate AI Agent Ayarları") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("Yerel Ollama / OpenAI uyumlu sunucu adresi (boş bırakılırsa yerleşik offline komut motoru çalışır):", fontSize = 12.sp, color = HudMuted)
                OutlinedTextField(value = ep, onValueChange = { ep = it }, label = { Text("Endpoint URL (ör. http://192.168.2.x:11434)") }, singleLine = true)
                OutlinedTextField(value = model, onValueChange = { model = it }, label = { Text("Model") }, singleLine = true)
                OutlinedTextField(value = key, onValueChange = { key = it }, label = { Text("API Key (opsiyonel)") }, singleLine = true)
            }
        },
        confirmButton = {
            TextButton(onClick = {
                agent.llmEndpoint = ep
                agent.llmModel = model
                agent.llmApiKey = key
                onDismiss()
            }) { Text("Kaydet", color = HudCyan) }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("İptal", color = HudMuted) }
        }
    )
}
