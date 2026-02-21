package com.elliot.bamboonowbar

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/**
 * Receives BOOT_COMPLETED broadcast.
 *
 * In FCM mode: Nothing to do! Firebase handles push delivery automatically.
 * The server sends pushes, and Android delivers them without any app code running.
 *
 * This receiver is kept for potential future use or fallback to MQTT mode.
 */
class BootReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "BootReceiver"
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED ||
            intent.action == "android.intent.action.QUICKBOOT_POWERON" ||
            intent.action == "com.htc.intent.action.QUICKBOOT_POWERON") {

            Log.d(TAG, "Boot completed")

            // In FCM mode, nothing to start!
            // Firebase automatically handles push delivery.
            // The BambuFCMService will be started by Firebase when a push arrives.
            Log.d(TAG, "FCM mode active - no startup needed. Server handles everything.")
        }
    }
}
