package com.elliot.bamboonowbar

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Binder
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import org.eclipse.paho.client.mqttv3.*
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence
import org.json.JSONObject
import java.security.SecureRandom
import java.security.cert.X509Certificate
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/**
 * Service that maintains MQTT connection to Bambu Labs Cloud.
 */
class BambuMqttService : Service() {

    companion object {
        private const val TAG = "BambuMqttService"

        private const val SERVICE_CHANNEL_ID = "bambu_service_channel"
        private const val SERVICE_NOTIFICATION_ID = 1000

        // Bambu Cloud MQTT Configuration
        // NOTE: This service is unused in FCM mode. Credentials removed for security.
        // If using direct MQTT mode, fill these in with your own values.
        private const val MQTT_SERVER = "ssl://us.mqtt.bambulab.com:8883"
        private const val USER_ID = "YOUR_USER_ID"
        private const val ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"
        private const val PRINTER_SERIAL = "YOUR_PRINTER_SERIAL"

        const val ACTION_CONNECTION_STATE = "com.elliot.bamboonowbar.CONNECTION_STATE"
        const val EXTRA_IS_CONNECTED = "is_connected"
        const val EXTRA_ERROR_MESSAGE = "error_message"

        const val ACTION_PRINT_STATE = "com.elliot.bamboonowbar.PRINT_STATE"
        const val EXTRA_PROGRESS = "progress"
        const val EXTRA_TIME_REMAINING = "time_remaining"
        const val EXTRA_JOB_NAME = "job_name"
        const val EXTRA_GCODE_STATE = "gcode_state"

        const val ACTION_START = "com.elliot.bamboonowbar.START_SERVICE"
        const val ACTION_STOP = "com.elliot.bamboonowbar.STOP_SERVICE"
        const val ACTION_START_BATTERY_EFFICIENT = "com.elliot.bamboonowbar.START_BATTERY_EFFICIENT"

        private const val KEEP_ALIVE_INTERVAL = 300  // 5 minutes (battery saving)
        private const val CONNECTION_TIMEOUT = 30

        // SharedPreferences keys for persisting state
        private const val PREF_COMPLETED_JOB_NAME = "completed_job_name"
        private const val PREF_FINAL_NOTIFICATION_POSTED = "final_notification_posted"
    }

    private var mqttClient: MqttAsyncClient? = null
    private var liveUpdateManager: LiveUpdateManager? = null
    private val binder = LocalBinder()
    private var wakeLock: PowerManager.WakeLock? = null
    private var isServiceRunning = false

    // Connection state management
    private var isConnectedState = false
    private var connectingInProgress = false
    private val handler = Handler(Looper.getMainLooper())

    // Debounce UI updates - only update every 30 seconds when printing (battery saving)
    private var lastUiBroadcast = 0L
    private var pendingUiUpdate: Runnable? = null
    private val UI_DEBOUNCE_MS = 30_000L  // 30 seconds between UI updates

    // Debounce notification updates - only update every 2 minutes (battery saving)
    private var lastNotificationUpdate = 0L
    private val NOTIFICATION_DEBOUNCE_MS = 120_000L  // 2 minutes between notification updates

    // Current printer state
    private var currentState = PrinterState()
    private var lastKnownGcodeState = "UNKNOWN"

    // Track if actively printing (for keeping service alive)
    private var isActivelyPrinting = false
    private var printingWakeLock: PowerManager.WakeLock? = null

    // SharedPreferences for persisting state across service/app restarts
    private val prefs by lazy {
        getSharedPreferences("bambu_print_state", Context.MODE_PRIVATE)
    }

    data class PrinterState(
        var gcodeState: String = "UNKNOWN",
        var progress: Int = 0,
        var remainingTimeSeconds: Int = 0,
        var jobName: String = "",
        var layerNum: Int = 0,
        var totalLayers: Int = 0,
        var nozzleTemp: Float = 0f,
        var bedTemp: Float = 0f
    )

    inner class LocalBinder : Binder() {
        fun getService(): BambuMqttService = this@BambuMqttService
    }

    override fun onBind(intent: Intent?): IBinder = binder

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "Service created")
        createServiceNotificationChannel()
        liveUpdateManager = LiveUpdateManager(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.d(TAG, "Service onStartCommand: ${intent?.action}")

        when (intent?.action) {
            ACTION_STOP -> {
                Log.d(TAG, "Stopping service and all background processes...")
                isServiceRunning = false
                isConnectedState = false
                isActivelyPrinting = false

                // Cancel ALL background work - full stop
                PrinterCheckWorker.cancel(this)

                // Release all wake locks
                releasePrintingWakeLock()
                releaseWakeLock()

                // Don't broadcast - the UI already knows we're stopping
                // Disconnect asynchronously to prevent blocking
                Thread {
                    disconnectAndCleanup()
                }.start()

                // Cancel any notifications
                liveUpdateManager?.cancelNotification()

                stopForeground(STOP_FOREGROUND_REMOVE)
                stopSelf()
                Log.d(TAG, "Service fully stopped - no background processes running")
                return START_NOT_STICKY
            }
            ACTION_START_BATTERY_EFFICIENT -> {
                // Battery efficient mode: use WorkManager for periodic checks
                // Only start persistent service when printer is actually printing
                Log.d(TAG, "Starting in battery-efficient mode (WorkManager)")
                PrinterCheckWorker.schedule(this)
                // Do one immediate check
                PrinterCheckWorker.checkNow(this)
                // Don't keep this service running - let WorkManager handle it
                stopSelf()
                return START_NOT_STICKY
            }
            else -> {
                if (!isServiceRunning) {
                    isServiceRunning = true
                    // Keep foreground notification to prevent Android from killing the service
                    // This is required for persistent background operation
                    startForeground(SERVICE_NOTIFICATION_ID, createServiceNotification("Connecting..."))
                }
                ensureConnected()
            }
        }

        return START_STICKY
    }

    fun isRunning(): Boolean = isServiceRunning

    override fun onDestroy() {
        super.onDestroy()
        handler.removeCallbacksAndMessages(null)
        releaseWakeLock()
        releasePrintingWakeLock()
        isActivelyPrinting = false
        // Run disconnect in background to avoid ANR (waitForCompletion blocks for up to 5 seconds)
        Thread {
            disconnectAndCleanup()
        }.start()
        liveUpdateManager?.cancelNotification()
        Log.d(TAG, "Service destroyed")
    }

    private fun createServiceNotificationChannel() {
        val notificationManager = getSystemService(NotificationManager::class.java)

        // Delete old channel if it exists (to apply new IMPORTANCE_NONE setting)
        notificationManager.deleteNotificationChannel(SERVICE_CHANNEL_ID)

        val channel = NotificationChannel(
            SERVICE_CHANNEL_ID,
            "Background Service",
            NotificationManager.IMPORTANCE_NONE  // IMPORTANCE_NONE hides notification completely
        ).apply {
            description = "Required for background operation - can be hidden"
            setShowBadge(false)
            enableVibration(false)
            setSound(null, null)
            lockscreenVisibility = Notification.VISIBILITY_SECRET
        }
        notificationManager.createNotificationChannel(channel)
        Log.d(TAG, "Service notification channel created with IMPORTANCE_NONE")
    }

    private fun createServiceNotification(status: String = "Monitoring printer"): Notification {
        val launchIntent = Intent(this, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            this, 0, launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, SERVICE_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_printer)
            .setContentTitle("Bambu Now Bar")
            .setContentText(status)
            .setOngoing(true)
            .setShowWhen(false)
            .setPriority(NotificationCompat.PRIORITY_MIN)
            .setContentIntent(pendingIntent)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .build()
    }

    private fun updateServiceNotification(status: String) {
        if (isServiceRunning) {
            val notification = createServiceNotification(status)
            val notificationManager = getSystemService(NotificationManager::class.java)
            notificationManager.notify(SERVICE_NOTIFICATION_ID, notification)
        }
    }

    private fun acquireWakeLock() {
        if (wakeLock == null) {
            val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
            wakeLock = powerManager.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK,
                "BambuNowBar:MqttWakeLock"
            ).apply {
                setReferenceCounted(false)
            }
        }
        wakeLock?.acquire(10 * 1000L)
    }

    private fun releaseWakeLock() {
        try {
            wakeLock?.let { if (it.isHeld) it.release() }
        } catch (e: Exception) {
            Log.w(TAG, "Error releasing wake lock: ${e.message}")
        }
    }

    /**
     * Acquire a long-term wake lock for active printing.
     * This keeps the CPU awake to ensure we receive MQTT updates.
     */
    private fun acquirePrintingWakeLock() {
        if (printingWakeLock == null) {
            val powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
            printingWakeLock = powerManager.newWakeLock(
                PowerManager.PARTIAL_WAKE_LOCK,
                "BambuNowBar:PrintingWakeLock"
            ).apply {
                setReferenceCounted(false)
            }
        }
        if (printingWakeLock?.isHeld != true) {
            // Acquire for up to 12 hours (long print jobs)
            printingWakeLock?.acquire(12 * 60 * 60 * 1000L)
            Log.d(TAG, "Acquired printing wake lock for active print")
        }
    }

    private fun releasePrintingWakeLock() {
        try {
            printingWakeLock?.let {
                if (it.isHeld) {
                    it.release()
                    Log.d(TAG, "Released printing wake lock")
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "Error releasing printing wake lock: ${e.message}")
        }
    }

    /**
     * Called when printing state changes - manages wake locks and service persistence.
     * Also handles switching to battery-efficient mode when printing finishes.
     */
    private fun updatePrintingState(isPrinting: Boolean) {
        if (isPrinting && !isActivelyPrinting) {
            // Started printing
            isActivelyPrinting = true
            acquirePrintingWakeLock()
            updateServiceNotification("Printing in progress...")
            Log.d(TAG, "Printing started - service locked")
        } else if (!isPrinting && isActivelyPrinting) {
            // Stopped printing - switch to battery efficient mode
            isActivelyPrinting = false
            releasePrintingWakeLock()

            // After a short delay, stop persistent service and use WorkManager instead
            handler.postDelayed({
                if (!isActivelyPrinting && isServiceRunning) {
                    Log.d(TAG, "Printing finished - switching to battery-efficient mode")
                    switchToIdleMode()
                }
            }, 30_000)  // Wait 30 seconds to ensure print is really done

            updateServiceNotification("Print finished")
            Log.d(TAG, "Printing stopped - will switch to idle mode in 30s")
        }
    }

    /**
     * Switch to battery-efficient WorkManager polling mode.
     * Stops the persistent MQTT connection and lets WorkManager check periodically.
     */
    private fun switchToIdleMode() {
        Log.d(TAG, "Switching to idle mode (WorkManager)")

        // Schedule periodic checks
        PrinterCheckWorker.schedule(this)

        // Disconnect and stop this service
        isServiceRunning = false
        Thread {
            disconnectAndCleanup()
        }.start()

        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    /**
     * Ensures we have a connection. Only creates client once.
     */
    @Synchronized
    private fun ensureConnected() {
        // Already connected
        if (mqttClient?.isConnected == true) {
            Log.d(TAG, "Already connected")
            updateConnectionState(true)
            return
        }

        // Connection attempt in progress
        if (connectingInProgress) {
            Log.d(TAG, "Connection already in progress")
            return
        }

        // Client exists but disconnected - Paho auto-reconnect will handle it
        if (mqttClient != null) {
            Log.d(TAG, "Client exists, waiting for auto-reconnect")
            return
        }

        // No client - create one
        connectingInProgress = true
        Log.d(TAG, "Creating new MQTT client...")

        try {
            // Unique client ID for this device
            val clientId = "android_${USER_ID}_${System.currentTimeMillis() % 10000}"

            mqttClient = MqttAsyncClient(MQTT_SERVER, clientId, MemoryPersistence())

            val options = MqttConnectOptions().apply {
                userName = "u_$USER_ID"
                password = ACCESS_TOKEN.toCharArray()
                isCleanSession = true
                connectionTimeout = CONNECTION_TIMEOUT
                keepAliveInterval = KEEP_ALIVE_INTERVAL
                isAutomaticReconnect = true  // Paho handles reconnection
                maxInflight = 10
                socketFactory = createTrustAllSocketFactory()
            }

            mqttClient?.setCallback(object : MqttCallbackExtended {
                override fun connectComplete(reconnect: Boolean, serverURI: String?) {
                    Log.i(TAG, "MQTT connected (reconnect: $reconnect)")
                    connectingInProgress = false
                    updateConnectionState(true)
                    updateServiceNotification("Connected to printer")
                    subscribeToReports()
                    requestPushAll()
                }

                override fun connectionLost(cause: Throwable?) {
                    Log.w(TAG, "MQTT connection lost: ${cause?.message}")
                    connectingInProgress = false
                    // Only update state if service is still running (not being stopped)
                    if (isServiceRunning) {
                        updateConnectionState(false, "Reconnecting...")
                        updateServiceNotification("Reconnecting...")
                    }
                    // Don't broadcast disconnect immediately - auto-reconnect will kick in
                }

                override fun messageArrived(topic: String?, message: MqttMessage?) {
                    acquireWakeLock()
                    try {
                        message?.let { handleMessage(it) }
                    } finally {
                        releaseWakeLock()
                    }
                }

                override fun deliveryComplete(token: IMqttDeliveryToken?) {}
            })

            Log.d(TAG, "Connecting to $MQTT_SERVER...")
            mqttClient?.connect(options, null, object : IMqttActionListener {
                override fun onSuccess(asyncActionToken: IMqttToken?) {
                    Log.d(TAG, "Connect initiated successfully")
                }

                override fun onFailure(asyncActionToken: IMqttToken?, exception: Throwable?) {
                    Log.e(TAG, "Connect failed: ${exception?.message}")
                    connectingInProgress = false
                    updateConnectionState(false, exception?.message)
                }
            })

        } catch (e: Exception) {
            Log.e(TAG, "Connection error: ${e.message}", e)
            connectingInProgress = false
            updateConnectionState(false, e.message)
        }
    }

    private fun createTrustAllSocketFactory(): javax.net.ssl.SSLSocketFactory {
        val trustAllCerts = arrayOf<TrustManager>(object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<X509Certificate>?, authType: String?) {}
            override fun checkServerTrusted(chain: Array<X509Certificate>?, authType: String?) {}
            override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
        })

        val sslContext = SSLContext.getInstance("TLS")
        sslContext.init(null, trustAllCerts, SecureRandom())
        return sslContext.socketFactory
    }

    private fun subscribeToReports() {
        val topic = "device/$PRINTER_SERIAL/report"
        try {
            mqttClient?.subscribe(topic, 1)
            Log.d(TAG, "Subscribed to: $topic")
        } catch (e: Exception) {
            Log.e(TAG, "Subscribe error: ${e.message}")
        }
    }

    private fun requestPushAll() {
        val topic = "device/$PRINTER_SERIAL/request"
        val payload = """{"pushing": {"sequence_id": "0", "command": "pushall"}}"""
        try {
            mqttClient?.publish(topic, MqttMessage(payload.toByteArray()))
            Log.d(TAG, "Sent pushall request")
        } catch (e: Exception) {
            Log.e(TAG, "Publish error: ${e.message}")
        }
    }

    private fun handleMessage(message: MqttMessage) {
        try {
            if (message.payload.size > 100 * 1024) {
                Log.w(TAG, "Message too large, ignoring")
                return
            }

            val json = JSONObject(String(message.payload))

            if (json.has("print")) {
                val printData = json.getJSONObject("print")

                // Only update fields that are present in this message
                if (printData.has("gcode_state")) {
                    val state = printData.optString("gcode_state", "")
                    if (state.isNotEmpty() && state.length <= 50) {
                        currentState.gcodeState = state
                    }
                }
                if (printData.has("mc_percent")) {
                    val percent = printData.optInt("mc_percent", -1)
                    if (percent in 0..100) {
                        currentState.progress = percent
                    }
                }
                if (printData.has("mc_remaining_time")) {
                    // mc_remaining_time is in MINUTES from Bambu API
                    val timeMinutes = printData.optInt("mc_remaining_time", -1)
                    Log.d(TAG, "mc_remaining_time raw value: $timeMinutes minutes")
                    if (timeMinutes >= 0 && timeMinutes <= 60 * 24 * 7) {
                        // Convert to seconds for internal storage
                        currentState.remainingTimeSeconds = timeMinutes * 60
                        Log.d(TAG, "Time remaining: $timeMinutes min = ${currentState.remainingTimeSeconds} sec")
                    }
                }
                if (printData.has("subtask_name")) {
                    val name = printData.optString("subtask_name", "")
                    if (name.length <= 200) {
                        currentState.jobName = name
                    }
                }
                if (printData.has("layer_num")) {
                    currentState.layerNum = printData.optInt("layer_num", 0).coerceIn(0, 100000)
                }
                if (printData.has("total_layer_num")) {
                    currentState.totalLayers = printData.optInt("total_layer_num", 0).coerceIn(0, 100000)
                }
                if (printData.has("nozzle_temper")) {
                    val temp = printData.optDouble("nozzle_temper", Double.NaN)
                    if (!temp.isNaN() && temp in -50.0..500.0) {
                        currentState.nozzleTemp = temp.toFloat()
                    }
                }
                if (printData.has("bed_temper")) {
                    val temp = printData.optDouble("bed_temper", Double.NaN)
                    if (!temp.isNaN() && temp in -50.0..200.0) {
                        currentState.bedTemp = temp.toFloat()
                    }
                }

                onPrinterStateUpdated()
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error parsing message: ${e.message}")
        }
    }

    private fun onPrinterStateUpdated() {
        val timeStr = formatTimeRemaining(currentState.remainingTimeSeconds)
        Log.v(TAG, "State: ${currentState.gcodeState}, Progress: ${currentState.progress}%, Layer: ${currentState.layerNum}/${currentState.totalLayers}, Time: $timeStr")

        // Broadcast to UI (debounced)
        broadcastPrintState()

        // Handle Live notification
        val isPrinting = currentState.gcodeState in listOf("RUNNING", "PRINTING", "PREPARE")
        val isFinished = currentState.gcodeState in listOf("FINISH", "COMPLETED")
        val isCancelled = currentState.gcodeState in listOf("CANCELLED", "FAILED", "IDLE") && lastKnownGcodeState in listOf("RUNNING", "PRINTING", "PREPARE")

        // Determine if we're in "starting" phase (preparing, homing, leveling, heating)
        // Layer 0 means actual printing hasn't started yet
        val isStarting = isPrinting && (currentState.layerNum == 0 || currentState.gcodeState == "PREPARE")

        // Update printing state for wake lock management
        updatePrintingState(isPrinting)

        // Battery optimization: debounce notification updates (every 2 minutes)
        val now = System.currentTimeMillis()
        val shouldUpdateNotification = (now - lastNotificationUpdate >= NOTIFICATION_DEBOUNCE_MS) ||
                isFinished || isCancelled ||  // Always update for final states
                (isPrinting && lastKnownGcodeState !in listOf("RUNNING", "PRINTING", "PREPARE"))  // Just started printing

        if (!shouldUpdateNotification && isPrinting) {
            Log.v(TAG, "Skipping notification update (battery saving) - next in ${(NOTIFICATION_DEBOUNCE_MS - (now - lastNotificationUpdate)) / 1000}s")
            lastKnownGcodeState = currentState.gcodeState
            return
        }
        lastNotificationUpdate = now

        // Check if we've already posted a final notification for this job (persisted across restarts)
        val completedJobName = prefs.getString(PREF_COMPLETED_JOB_NAME, null)
        val hasFinalNotificationBeenPosted = prefs.getBoolean(PREF_FINAL_NOTIFICATION_POSTED, false)
        val currentJobName = currentState.jobName.ifEmpty { "unknown" }

        if (isPrinting) {
            // Clear the completed job flag when a new print starts
            if (hasFinalNotificationBeenPosted) {
                prefs.edit()
                    .putBoolean(PREF_FINAL_NOTIFICATION_POSTED, false)
                    .putString(PREF_COMPLETED_JOB_NAME, null)
                    .apply()
                Log.d(TAG, "New print started - cleared completion flag")
            }

            val timeRemaining = formatTimeRemaining(currentState.remainingTimeSeconds)
            liveUpdateManager?.postLiveUpdate(
                progress = currentState.progress,
                timeRemaining = timeRemaining,
                jobName = currentState.jobName.ifEmpty { null },
                layerInfo = if (currentState.totalLayers > 0 && !isStarting) {
                    "${currentState.layerNum}/${currentState.totalLayers}"
                } else null,
                isStarting = isStarting
            )
        } else if (isFinished && !hasFinalNotificationBeenPosted) {
            // Print completed - post completion notification (stays until user dismisses)
            // Save to prefs so we don't show it again after service restart
            prefs.edit()
                .putBoolean(PREF_FINAL_NOTIFICATION_POSTED, true)
                .putString(PREF_COMPLETED_JOB_NAME, currentJobName)
                .apply()
            liveUpdateManager?.postCompletionNotification(currentState.jobName.ifEmpty { null })
            Log.d(TAG, "Print completed - posted final notification for: $currentJobName")
        } else if (isFinished && hasFinalNotificationBeenPosted && completedJobName == currentJobName) {
            // Already posted completion notification for this job - don't post again
            Log.d(TAG, "Skipping completion notification - already posted for: $completedJobName")
        } else if (isCancelled && !hasFinalNotificationBeenPosted) {
            // Print was cancelled - post cancellation notification (stays until user dismisses)
            prefs.edit()
                .putBoolean(PREF_FINAL_NOTIFICATION_POSTED, true)
                .putString(PREF_COMPLETED_JOB_NAME, currentJobName)
                .apply()
            liveUpdateManager?.postCancellationNotification(currentState.jobName.ifEmpty { null })
            Log.d(TAG, "Print cancelled - posted final notification for: $currentJobName")
        }
        // Note: We no longer auto-cancel notifications - user must swipe to dismiss

        lastKnownGcodeState = currentState.gcodeState
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

    /**
     * Update internal connection state and debounce UI broadcasts
     */
    private fun updateConnectionState(connected: Boolean, error: String? = null) {
        isConnectedState = connected

        // Cancel any pending update
        pendingUiUpdate?.let { handler.removeCallbacks(it) }

        val now = System.currentTimeMillis()
        val timeSinceLastBroadcast = now - lastUiBroadcast

        // If we just broadcast recently, delay this update
        if (timeSinceLastBroadcast < 3000) {
            pendingUiUpdate = Runnable {
                broadcastConnectionStateNow(connected, error)
            }
            handler.postDelayed(pendingUiUpdate!!, 3000 - timeSinceLastBroadcast)
        } else {
            broadcastConnectionStateNow(connected, error)
        }
    }

    private fun broadcastConnectionStateNow(connected: Boolean, error: String? = null) {
        lastUiBroadcast = System.currentTimeMillis()

        val intent = Intent(ACTION_CONNECTION_STATE).apply {
            putExtra(EXTRA_IS_CONNECTED, connected)
            error?.let { putExtra(EXTRA_ERROR_MESSAGE, it) }
            setPackage(packageName)
        }
        sendBroadcast(intent)
    }

    private fun broadcastPrintState() {
        val intent = Intent(ACTION_PRINT_STATE).apply {
            putExtra(EXTRA_PROGRESS, currentState.progress)
            putExtra(EXTRA_TIME_REMAINING, formatTimeRemaining(currentState.remainingTimeSeconds))
            putExtra(EXTRA_JOB_NAME, currentState.jobName)
            putExtra(EXTRA_GCODE_STATE, currentState.gcodeState)
            setPackage(packageName)
        }
        sendBroadcast(intent)
    }

    @Synchronized
    private fun disconnectAndCleanup() {
        try {
            mqttClient?.setCallback(null)  // Remove callback first
            if (mqttClient?.isConnected == true) {
                mqttClient?.disconnect()?.waitForCompletion(5000)
            }
            mqttClient?.close()
        } catch (e: Exception) {
            Log.e(TAG, "Disconnect error: ${e.message}")
        } finally {
            mqttClient = null
            connectingInProgress = false
        }
        Log.d(TAG, "Disconnected and cleaned up")
    }

    fun isConnected(): Boolean = isConnectedState

    fun getCurrentState(): PrinterState = currentState
}
