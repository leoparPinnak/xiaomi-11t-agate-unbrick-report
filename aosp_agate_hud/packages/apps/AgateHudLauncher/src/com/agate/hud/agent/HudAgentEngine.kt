package com.agate.hud.agent

import android.bluetooth.BluetoothAdapter
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.net.wifi.WifiManager
import android.provider.Settings
import com.agate.hud.data.SystemTelemetry
import com.agate.hud.data.TelemetrySnapshot
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale

data class AppEntry(
    val label: String,
    val packageName: String,
    val launchIntent: Intent,
)

data class AgentResponse(
    val text: String,
    val actionBadge: String? = null,
)

class HudAgentEngine(
    private val context: Context,
    private val telemetry: SystemTelemetry,
) {
    private val prefs = context.getSharedPreferences("agate_hud_agent", Context.MODE_PRIVATE)

    var llmEndpoint: String
        get() = prefs.getString("llm_endpoint", "") ?: ""
        set(v) = prefs.edit().putString("llm_endpoint", v.trim()).apply()

    var llmModel: String
        get() = prefs.getString("llm_model", "llama3.2") ?: "llama3.2"
        set(v) = prefs.edit().putString("llm_model", v.trim()).apply()

    var llmApiKey: String
        get() = prefs.getString("llm_key", "") ?: ""
        set(v) = prefs.edit().putString("llm_key", v.trim()).apply()

    fun loadLaunchableApps(): List<AppEntry> {
        val pm = context.packageManager
        val mainIntent = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        val resolved = pm.queryIntentActivities(mainIntent, PackageManager.ResolveInfoFlags.of(0L))
        return resolved
            .filter { it.activityInfo.packageName != context.packageName }
            .mapNotNull { ri ->
                val pkg = ri.activityInfo.packageName
                val li = pm.getLaunchIntentForPackage(pkg) ?: return@mapNotNull null
                li.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                AppEntry(
                    label = ri.loadLabel(pm).toString(),
                    packageName = pkg,
                    launchIntent = li,
                )
            }
            .sortedBy { it.label.lowercase(Locale.ROOT) }
    }

    suspend fun handleCommand(
        rawInput: String,
        snap: TelemetrySnapshot,
        apps: List<AppEntry>,
    ): AgentResponse = withContext(Dispatchers.IO) {
        val q = rawInput.trim()
        val low = q.lowercase(Locale("tr", "TR"))
        if (low.isEmpty()) return@withContext AgentResponse("Komut bekleniyor.")

        // 1. Charge limit commands
        if (low.contains("70") || low.contains("şarj limit") || low.contains("sarj limit") || low.contains("limiti")) {
            val turnOff = low.contains("kapat") || low.contains("100") || low.contains("iptal")
            val ok = telemetry.setChargeLimitEnabled(!turnOff)
            return@withContext if (!turnOff) {
                AgentResponse(
                    "Pil koruma modu devrede: %70'te şarj kesilir, %67'de devam eder." + if (!ok) " (Sistem izni beklemede)" else "",
                    "BAT LIMIT 70%"
                )
            } else {
                AgentResponse("Şarj limiti kapatıldı (%100'e kadar şarj izinli).", "BAT LIMIT OFF")
            }
        }

        // 2. Telemetry / system status
        if (low.contains("durum") || low.contains("analiz") || low.contains("sıcaklık") || low.contains("sicaklik") || low.contains("pil")) {
            return@withContext AgentResponse(
                "CPU %${snap.cpuPct.toInt()} · SoC ${"%.1f".format(snap.socTempC)}°C · RAM ${snap.ramUsedMb}/${snap.ramTotalMb} MB · Pil %${snap.batteryPct} (${snap.batteryMa} mA).",
                "TELEMETRY"
            )
        }

        // 3. Brightness control
        if (low.contains("parlak") || low.contains("ekran ış") || low.contains("ekran is")) {
            val num = Regex("\\d+").find(low)?.value?.toIntOrNull()
            val target = when {
                num != null -> (num.coerceIn(5, 100) * 255) / 100
                low.contains("düşür") || low.contains("azalt") || low.contains("kıs") -> 60
                else -> 220
            }
            return@withContext try {
                Settings.System.putInt(context.contentResolver, Settings.System.SCREEN_BRIGHTNESS_MODE, Settings.System.SCREEN_BRIGHTNESS_MODE_MANUAL)
                Settings.System.putInt(context.contentResolver, Settings.System.SCREEN_BRIGHTNESS, target)
                AgentResponse("Ekran parlaklığı ${(target * 100) / 255}% olarak ayarlandı.", "DISPLAY ${(target * 100) / 255}%")
            } catch (_: Throwable) {
                AgentResponse("Parlaklık için sistem yazma izni gerekiyor.", "PERM")
            }
        }

        // 4. Settings / Wi-Fi / Bluetooth quick actions
        if (low.contains("ayar") || low.contains("settings")) {
            val i = Intent(Settings.ACTION_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(i)
            return@withContext AgentResponse("Sistem Ayarları açılıyor.", "SETTINGS")
        }

        if (low.contains("wifi") || low.contains("wi-fi")) {
            val i = Intent(Settings.Panel.ACTION_WIFI).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(i)
            return@withContext AgentResponse("Wi-Fi hızlı paneli açıldı.", "WIFI")
        }

        // 5. Launch installed app by fuzzy name match
        val cleanQuery = low
            .replace("uygulamasını aç", "")
            .replace("uygulamasini ac", "")
            .replace("aç", "")
            .replace("ac", "")
            .trim()

        val aliases = mapOf(
            "tarayıcı" to listOf("browser", "chrome", "webview", "via"),
            "tarayici" to listOf("browser", "chrome", "webview", "via"),
            "galeri" to listOf("gallery", "photos", "foto"),
            "kamera" to listOf("camera"),
            "saat" to listOf("clock", "deskclock"),
            "mesaj" to listOf("messaging", "sms"),
            "telefon" to listOf("dialer", "phone"),
            "dosya" to listOf("files", "documentsui"),
        )
        val searchTerms = aliases[cleanQuery] ?: listOf(cleanQuery)
        val matched = apps.firstOrNull { app ->
            val lbl = app.label.lowercase(Locale.ROOT)
            val pkg = app.packageName.lowercase(Locale.ROOT)
            searchTerms.any { term -> term.isNotEmpty() && (lbl.contains(term) || pkg.contains(term)) }
        }
        if (matched != null) {
            context.startActivity(matched.launchIntent)
            return@withContext AgentResponse("${matched.label} başlatılıyor.", "LAUNCH")
        }

        // 6. Optional Web search
        if (low.startsWith("ara ") || low.contains("google")) {
            val term = q.removePrefix("ara").trim()
            val i = Intent(Intent.ACTION_VIEW, Uri.parse("https://www.google.com/search?q=" + Uri.encode(term))).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(i)
            return@withContext AgentResponse("Tarayıcıda aranıyor: $term", "WEB")
        }

        // 7. Optional Remote OpenAI-compatible / Ollama Endpoint
        val ep = llmEndpoint
        if (ep.isNotBlank()) {
            return@withContext callRemoteLlm(ep, q, snap)
        }

        AgentResponse(
            "Anlaşıldı: '$q'. Örnek komutlar: 'durum', 'şarjı 70 yap', 'parlaklık 40', 'ayarlar', '<uygulama> aç' veya Agent ayarlarından yerel LLM sunucusu bağlayabilirsin.",
            "HUD AGENT"
        )
    }

    private fun callRemoteLlm(endpoint: String, prompt: String, snap: TelemetrySnapshot): AgentResponse {
        return try {
            val url = URL(if (endpoint.endsWith("/chat/completions")) endpoint else "${endpoint.trimEnd('/')}/v1/chat/completions")
            val conn = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 4000
                readTimeout = 15000
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
                if (llmApiKey.isNotBlank()) setRequestProperty("Authorization", "Bearer $llmApiKey")
            }
            val sysPrompt = "Sen Xiaomi 11T Agate HUD kokpit yapay zeka asistanısın. Kısa ve net Türkçe cevap ver. " +
                "Sistem: CPU %${snap.cpuPct.toInt()}, SoC ${snap.socTempC}°C, Pil %${snap.batteryPct}, RAM ${snap.ramUsedMb}/${snap.ramTotalMb}MB."
            val body = JSONObject().apply {
                put("model", llmModel)
                put("messages", JSONArray().apply {
                    put(JSONObject().put("role", "system").put("content", sysPrompt))
                    put(JSONObject().put("role", "user").put("content", prompt))
                })
                put("max_tokens", 160)
            }
            conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val respStr = stream.bufferedReader().readText()
            val json = JSONObject(respStr)
            val reply = json.getJSONArray("choices").getJSONObject(0).getJSONObject("message").getString("content").trim()
            AgentResponse(reply, "LLM $llmModel")
        } catch (t: Throwable) {
            AgentResponse("Harici LLM bağlantı hatası: ${t.message}", "LLM ERR")
        }
    }
}
