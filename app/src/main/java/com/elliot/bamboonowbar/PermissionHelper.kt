package com.elliot.bamboonowbar

import android.os.Build

/**
 * Helper class for device info and compatibility checks.
 */
object PermissionHelper {

    /**
     * Checks if the device supports Live Updates / Now Bar.
     * Android 16 (API 36) is required for ProgressStyle notifications.
     */
    fun isLiveUpdateSupported(): Boolean {
        return Build.VERSION.SDK_INT >= 36
    }

    /**
     * Returns device info string for debugging.
     */
    fun getDeviceInfo(): String {
        return buildString {
            append("Manufacturer: ${Build.MANUFACTURER}\n")
            append("Model: ${Build.MODEL}\n")
            append("Android: ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})\n")
            append("Live Updates: ${if (isLiveUpdateSupported()) "Supported" else "Not supported"}")
        }
    }
}
