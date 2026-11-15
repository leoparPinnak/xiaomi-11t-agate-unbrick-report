package com.agate.hud.ui

/**
 * Pure GPU-rendered AGSL (Android Graphics Shading Language) fragment shaders
 * executed directly on the Mali-G77 MC9 GPU via android.graphics.RuntimeShader.
 * Zero static PNG/bitmap background or gauge assets.
 */
object HudShaders {

    /**
     * Automotive Head-Up Display / i-Cockpit 3D perspective horizon grid + flowing plasma aurora.
     */
    const val COCKPIT_BACKGROUND_AGSL = """
        uniform float2 uResolution;
        uniform float  uTime;
        uniform float  uCpuLoad;
        uniform float  uAccentMix;

        float hash21(float2 p) {
            p = fract(p * float2(123.34, 456.21));
            p += dot(p, p + 45.32);
            return fract(p.x * p.y);
        }

        float noise(float2 p) {
            float2 i = floor(p);
            float2 f = fract(p);
            f = f * f * (3.0 - 2.0 * f);
            float a = hash21(i);
            float b = hash21(i + float2(1.0, 0.0));
            float c = hash21(i + float2(0.0, 1.0));
            float d = hash21(i + float2(1.0, 1.0));
            return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
        }

        float fbm(float2 p) {
            float v = 0.0;
            float a = 0.5;
            for (int i = 0; i < 4; i++) {
                v += a * noise(p);
                p = p * 2.03 + float2(1.7, 9.2);
                a *= 0.5;
            }
            return v;
        }

        half4 main(float2 fragCoord) {
            float2 uv = fragCoord / uResolution;
            float aspect = uResolution.x / max(uResolution.y, 1.0);
            float2 p = float2((uv.x - 0.5) * aspect, uv.y - 0.5);

            // Deep obsidian cockpit base
            float3 col = float3(0.014, 0.024, 0.044);

            // Upper & lower atmospheric energy ribbons (GPU fBm)
            float n1 = fbm(float2(p.x * 1.9 + uTime * 0.08, p.y * 2.4 - uTime * 0.05));
            float n2 = fbm(float2(p.x * 3.1 - uTime * 0.11, p.y * 3.2 + uTime * 0.07));
            float3 cyan = float3(0.0, 0.898, 1.0);
            float3 amber = float3(1.0, 0.62, 0.11);
            float3 glowCol = mix(cyan, amber, clamp(uAccentMix, 0.0, 1.0));

            float band = exp(-abs(p.y + 0.12 + (n1 - 0.5) * 0.18) * 9.5);
            col += glowCol * band * (0.14 + 0.12 * uCpuLoad);
            col += cyan * pow(n2, 2.2) * 0.075;

            // Perspective 3D HUD floor grid in lower half
            float horizonY = 0.56;
            if (uv.y > horizonY) {
                float depth = max(uv.y - horizonY, 0.008);
                float z = 0.24 / depth;
                float gx = (uv.x - 0.5) * aspect * z * 2.1;
                float gz = z + uTime * (0.55 + uCpuLoad * 0.8);

                float lx = abs(fract(gx) - 0.5);
                float lz = abs(fract(gz) - 0.5);
                float lineX = smoothstep(0.035, 0.0, lx);
                float lineZ = smoothstep(0.045, 0.0, lz);
                float grid = max(lineX, lineZ);

                float fade = smoothstep(horizonY, horizonY + 0.09, uv.y) * smoothstep(1.02, 0.62, uv.y);
                col += glowCol * grid * fade * 0.26;
            }

            // Crisp horizon telemetry line + subtle scan pulse
            float horizonGlow = exp(-abs(uv.y - horizonY) * 140.0);
            col += glowCol * horizonGlow * 0.42;

            float scanY = fract(uTime * 0.14);
            float scanPulse = exp(-abs(uv.y - scanY) * 95.0);
            col += cyan * scanPulse * 0.04;

            // Radial vignette for OLED contrast
            float vig = 1.0 - dot(p * float2(0.85, 1.05), p * float2(0.85, 1.05)) * 0.55;
            col *= clamp(vig, 0.35, 1.0);

            return half4(half3(col), 1.0);
        }
    """

    /**
     * Radial GPU HUD Arc Gauge with tick marks, neon bloom, and smooth value sweep.
     */
    const val RADIAL_GAUGE_AGSL = """
        uniform float2 uSize;
        uniform float  uProgress;
        uniform float  uTime;
        uniform float3 uStartColor;
        uniform float3 uEndColor;

        half4 main(float2 fragCoord) {
            float2 uv = (fragCoord - uSize * 0.5) / min(uSize.x, uSize.y);
            float r = length(uv);
            float angle = atan(uv.y, uv.x); // -PI..PI

            // Rotate so 0 is bottom-left (135 deg) sweeping clockwise 270 deg
            float deg = degrees(angle);
            float shifted = mod(deg - 135.0 + 360.0, 360.0);
            float sweep = 270.0;

            float inArc = step(shifted, sweep);
            float norm = shifted / sweep;

            // Main arc track
            float trackDist = abs(r - 0.39);
            float track = smoothstep(0.032, 0.018, trackDist) * inArc;

            // Active progress fill + smooth leading edge
            float progMask = smoothstep(uProgress + 0.015, uProgress - 0.015, norm) * inArc;
            float activeCore = smoothstep(0.024, 0.008, trackDist) * progMask;
            float activeGlow = exp(-trackDist * 42.0) * progMask * 0.65;

            // Leading head spark
            float headDist = length(float2(norm - uProgress, trackDist * 2.5));
            float headSpark = exp(-headDist * 22.0) * step(0.02, uProgress);

            // Outer precision tick ring
            float tickAngle = fract(shifted / 9.0);
            float tickMask = smoothstep(0.18, 0.06, abs(tickAngle - 0.5)) * inArc;
            float tickRing = smoothstep(0.018, 0.006, abs(r - 0.455)) * tickMask;

            float3 barCol = mix(uStartColor, uEndColor, clamp(norm, 0.0, 1.0));
            float3 col = float3(0.0);
            col += float3(0.10, 0.16, 0.24) * track * 0.75;
            col += barCol * (activeCore * 1.15 + activeGlow);
            col += float3(0.92, 0.98, 1.0) * headSpark * 0.85;
            col += mix(float3(0.2, 0.3, 0.4), barCol, progMask) * tickRing * 0.65;

            float alpha = clamp(track * 0.45 + activeCore + activeGlow + headSpark + tickRing * 0.55, 0.0, 1.0);
            return half4(half3(col), half(alpha));
        }
    """
}
