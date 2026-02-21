package com.elliot.bamboonowbar

import android.util.Log
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

/**
 * Firebase Cloud Messaging service.
 * Receives push notifications from the Linux server and displays Live Updates.
 *
 * NO MQTT connection on the phone - all data comes via FCM push.
 * This is extremely battery efficient.
 */
class BambuFCMService : FirebaseMessagingService() {

    companion object {
        private const val TAG = "BambuFCMService"
    }

    private var liveUpdateManager: LiveUpdateManager? = null

    override fun onCreate() {
        super.onCreate()
        liveUpdateManager = LiveUpdateManager(this)
    }

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        // Log the token - user needs to copy this to the server script
        Log.d(TAG, "=" .repeat(50))
        Log.d(TAG, "FCM Token (copy this to your server):")
        Log.d(TAG, token)
        Log.d(TAG, "=" .repeat(50))

        // Save token locally
        getSharedPreferences("fcm_prefs", MODE_PRIVATE)
            .edit()
            .putString("fcm_token", token)
            .apply()
    }

    override fun onMessageReceived(message: RemoteMessage) {
        super.onMessageReceived(message)
        Log.d(TAG, "FCM message received from: ${message.from}")

        val data = message.data
        if (data.isEmpty()) {
            Log.w(TAG, "Empty data payload")
            return
        }

        val type = data["type"] ?: "unknown"
        val gcodeState = data["gcode_state"] ?: "UNKNOWN"
        val progress = data["progress"]?.toIntOrNull() ?: 0
        val remainingMinutes = data["remaining_minutes"]?.toIntOrNull() ?: 0
        val jobName = data["job_name"] ?: ""
        val layerNum = data["layer_num"]?.toIntOrNull() ?: 0
        val totalLayers = data["total_layers"]?.toIntOrNull() ?: 0

        Log.d(TAG, "Type: $type, State: $gcodeState, Progress: $progress%")

        // Format time remaining
        val timeRemaining = formatTimeRemaining(remainingMinutes * 60)

        // Handle based on notification type
        when (type) {
            "startup" -> {
                Log.d(TAG, "Server startup notification received")

                // Show notification
                liveUpdateManager?.postServerConnectedNotification()

                // Save server status to SharedPreferences (UI checks this on resume)
                getSharedPreferences("fcm_prefs", MODE_PRIVATE)
                    .edit()
                    .putBoolean("server_active", true)
                    .putLong("server_connected_time", System.currentTimeMillis())
                    .apply()
            }

            "starting" -> {
                liveUpdateManager?.postLiveUpdate(
                    progress = 0,
                    timeRemaining = timeRemaining,
                    jobName = jobName.ifEmpty { null },
                    layerInfo = null,
                    isStarting = true
                )
            }

            "progress" -> {
                val isStarting = layerNum == 0 || gcodeState == "PREPARE"
                liveUpdateManager?.postLiveUpdate(
                    progress = progress,
                    timeRemaining = timeRemaining,
                    jobName = jobName.ifEmpty { null },
                    layerInfo = if (totalLayers > 0 && !isStarting) "$layerNum/$totalLayers" else null,
                    isStarting = isStarting
                )
            }

            "completed" -> {
                liveUpdateManager?.postCompletionNotification(jobName.ifEmpty { null })
            }

            "cancelled" -> {
                liveUpdateManager?.postCancellationNotification(jobName.ifEmpty { null })
            }

            "idle" -> {
                // Printer is idle - cancel any active notification
                Log.d(TAG, "Printer idle - cancelling notification")
                liveUpdateManager?.cancelNotification()
            }

            else -> {
                Log.w(TAG, "Unknown notification type: $type")
            }
        }
    }

    private fun formatTimeRemaining(seconds: Int): String {
        val hours = seconds / 3600
        val minutes = (seconds % 3600) / 60
        return when {
            hours > 0 && minutes > 0 -> "${hours}h ${minutes}m"
            hours > 0 -> "${hours}h"
            minutes > 0 -> "${minutes}m"
            else -> "<1m"
        }
    }
}
