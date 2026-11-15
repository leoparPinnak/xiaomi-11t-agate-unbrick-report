package com.agate.hud.data

import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.wifi.WifiManager
import android.os.BatteryManager
import android.os.SystemProperties
import java.io.File
import kotlin.math.abs

data class TelemetrySnapshot(
    val cpuPct: Float = 0f,
    val coreLoads: List<Float> = List(8) { 0f },
    val ramUsedMb: Int = 0,
    val ramTotalMb: Int = 8192,
    val socTempC: Float = 35f,
    val batteryPct: Int = 50,
    val batteryMa: Int = 0,
    val batteryTempC: Float = 30f,
    val charging: Boolean = false,
    val chargeLimitEnabled: Boolean = true,
    val chargeCutoffActive: Boolean = false,
    val wifiConnected: Boolean = false,
    val wifiRssiDbm: Int = -99,
    val gpuFreqMhz: Int = 0,
)

class SystemTelemetry(private val context: Context) {

    private var prevTotals = LongArray(9)
    private var prevIdles = LongArray(9)

    fun readSnapshot(): TelemetrySnapshot {
        val (cpuPct, coreLoads) = readCpu()
        val (ramUsed, ramTot) = readMem()
        val socTemp = readSocTemp()
        val gpuMhz = readGpuFreq()

        // Battery info via Android BatteryManager + kernel sysfs fallback
        val bm = context.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        val intent = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val level = intent?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = intent?.getIntExtra(BatteryManager.EXTRA_SCALE, 100) ?: 100
        val pct = if (level >= 0 && scale > 0) (level * 100) / scale else 50
        val status = intent?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
        val isCharging = status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL
        val bTempTenths = intent?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 300) ?: 300
        val curUa = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CURRENT_NOW)
        val curMa = if (abs(curUa) > 10000) curUa / 1000 else curUa

        val susp = readSysInt("/sys/class/power_supply/battery/input_suspend", 0)
        val limitProp = SystemProperties.getBoolean("persist.agate.charge_limit", true)

        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val caps = cm.getNetworkCapabilities(cm.activeNetwork)
        val wifiOk = caps?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true
        val wm = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
        val rssi = wm?.connectionInfo?.rssi ?: -99

        return TelemetrySnapshot(
            cpuPct = cpuPct,
            coreLoads = coreLoads,
            ramUsedMb = ramUsed,
            ramTotalMb = ramTot,
            socTempC = socTemp,
            batteryPct = pct,
            batteryMa = curMa,
            batteryTempC = bTempTenths / 10f,
            charging = isCharging,
            chargeLimitEnabled = limitProp,
            chargeCutoffActive = (susp == 1),
            wifiConnected = wifiOk,
            wifiRssiDbm = rssi,
            gpuFreqMhz = gpuMhz,
        )
    }

    fun setChargeLimitEnabled(enabled: Boolean): Boolean {
        return try {
            SystemProperties.set("persist.agate.charge_limit", if (enabled) "true" else "false")
            if (!enabled) {
                File("/sys/class/power_supply/battery/input_suspend").writeText("0\n")
            }
            true
        } catch (_: Throwable) {
            false
        }
    }

    private fun readCpu(): Pair<Float, List<Float>> {
        val loads = MutableList(8) { 0f }
        var totalPct = 0f
        try {
            File("/proc/stat").forEachLine { line ->
                if (!line.startsWith("cpu")) return@forEachLine
                val parts = line.trim().split(Regex("\\s+"))
                val tag = parts[0]
                val idx = if (tag == "cpu") 0 else tag.removePrefix("cpu").toIntOrNull()?.plus(1) ?: return@forEachLine
                if (idx > 8 || parts.size < 5) return@forEachLine
                val u = parts[1].toLongOrNull() ?: 0L
                val n = parts[2].toLongOrNull() ?: 0L
                val s = parts[3].toLongOrNull() ?: 0L
                val id = parts[4].toLongOrNull() ?: 0L
                val io = parts.getOrNull(5)?.toLongOrNull() ?: 0L
                val irq = parts.getOrNull(6)?.toLongOrNull() ?: 0L
                val sirq = parts.getOrNull(7)?.toLongOrNull() ?: 0L
                val idle = id + io
                val tot = u + n + s + idle + irq + sirq
                val dt = tot - prevTotals[idx]
                val did = idle - prevIdles[idx]
                val pct = if (prevTotals[idx] > 0 && dt > 0) ((dt - did) * 100f / dt).coerceIn(0f, 100f) else 0f
                prevTotals[idx] = tot
                prevIdles[idx] = idle
                if (idx == 0) totalPct = pct else loads[idx - 1] = pct
            }
        } catch (_: Throwable) {}
        // Fallback when SELinux restricts /proc/stat: estimate load from per-core cpufreq scaling_cur_freq
        if (totalPct == 0f && loads.all { it == 0f }) {
            var sum = 0f
            var cnt = 0
            for (c in 0..7) {
                val cur = readSysInt("/sys/devices/system/cpu/cpu$c/cpufreq/scaling_cur_freq", -1)
                val max = readSysInt("/sys/devices/system/cpu/cpu$c/cpufreq/cpuinfo_max_freq", 2000000)
                if (cur > 0 && max > 0) {
                    val pct = (cur * 100f / max).coerceIn(4f, 100f)
                    loads[c] = pct
                    sum += pct
                    cnt++
                }
            }
            if (cnt > 0) totalPct = sum / cnt
        }
        return totalPct to loads
    }

    private fun readMem(): Pair<Int, Int> {
        var tot = 8192L
        var avail = 4096L
        try {
            File("/proc/meminfo").forEachLine { line ->
                when {
                    line.startsWith("MemTotal:") -> tot = line.split(Regex("\\s+"))[1].toLong() / 1024L
                    line.startsWith("MemAvailable:") -> avail = line.split(Regex("\\s+"))[1].toLong() / 1024L
                }
            }
        } catch (_: Throwable) {}
        return (tot - avail).toInt().coerceAtLeast(0) to tot.toInt()
    }

    private fun readSocTemp(): Float {
        var maxT = 34f
        for (z in 0..15) {
            val raw = readSysInt("/sys/class/thermal/thermal_zone$z/temp", -1)
            val c = when {
                raw in 1000..120000 -> raw / 1000f
                raw in 10..120 -> raw.toFloat()
                else -> -1f
            }
            if (c > maxT) maxT = c
        }
        return maxT
    }

    private fun readGpuFreq(): Int {
        return try {
            val txt = File("/proc/gpufreq/gpufreq_var_dump").readText()
            val m = Regex("freq:\\s*(\\d+)").find(txt)
            (m?.groupValues?.get(1)?.toIntOrNull() ?: 0) / 1000
        } catch (_: Throwable) {
            0
        }
    }

    private fun readSysInt(path: String, def: Int): Int {
        return try {
            File(path).readText().trim().toInt()
        } catch (_: Throwable) {
            def
        }
    }
}
