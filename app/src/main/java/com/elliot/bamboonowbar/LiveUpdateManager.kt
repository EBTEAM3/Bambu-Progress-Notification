package com.elliot.bamboonowbar

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.Icon
import android.os.Build
import android.os.Bundle
import android.util.Log
import androidx.annotation.RequiresApi
import androidx.core.app.NotificationCompat

/**
 * Manages Live Update notifications for Samsung Now Bar on One UI 8 / Android 16.
 *
 * Three display locations:
 * 1. Status bar chip (top corner) - Shows just percentage
 * 2. Lock screen Now Bar (bottom) - Animated progress bar with dot, percentage left, time right, job name above
 * 3. Notification panel (expanded) - Full details with thicker animated bar, centered
 *
 * Requirements for Live Update promotion:
 * - Permission: POST_PROMOTED_NOTIFICATIONS
 * - setOngoing(true)
 * - setContentTitle() must be set
 * - NO custom RemoteViews
 * - NOT a group summary
 * - NOT colorized
 * - Channel importance != IMPORTANCE_MIN
 */
class LiveUpdateManager(private val context: Context) {

    companion object {
        private const val TAG = "LiveUpdateManager"

        const val CHANNEL_ID = "bambu_live_updates"
        const val CHANNEL_NAME = "Live Print Progress"
        const val CHANNEL_DESCRIPTION = "Shows 3D print progress as Live Update in Now Bar"

        const val NOTIFICATION_ID = 1001

        // Bambu Handy app package name
        const val BAMBOO_PACKAGE = "com.bambulab.bambuhandyapp"

        // Blue color scheme
        private const val ACCENT_COLOR = "#2196F3"  // Material Blue
        private const val ACCENT_DARK = "#1976D2"   // Darker blue
        private const val PROGRESS_GRAY = "#424242"

        // Extra for requesting promoted ongoing notification (Android 16)
        private const val EXTRA_REQUEST_PROMOTED_ONGOING = "android.requestPromotedOngoing"

        // Samsung One UI specific extras for Live Notifications / Now Bar
        private const val SAMSUNG_STYLE = "android.ongoingActivityNoti.style"
        private const val SAMSUNG_PRIMARY_INFO = "android.ongoingActivityNoti.primaryInfo"
        private const val SAMSUNG_SECONDARY_INFO = "android.ongoingActivityNoti.secondaryInfo"
        private const val SAMSUNG_CHIP_BG_COLOR = "android.ongoingActivityNoti.chipBgColor"
        private const val SAMSUNG_CHIP_ICON = "android.ongoingActivityNoti.chipIcon"
        private const val SAMSUNG_CHIP_EXPANDED_TEXT = "android.ongoingActivityNoti.chipExpandedText"
        private const val SAMSUNG_ACTION_TYPE = "android.ongoingActivityNoti.actionType"
        private const val SAMSUNG_ACTION_PRIMARY_SET = "android.ongoingActivityNoti.actionPrimarySet"
        private const val SAMSUNG_NOWBAR_PRIMARY = "android.ongoingActivityNoti.nowbarPrimaryInfo"
        private const val SAMSUNG_NOWBAR_SECONDARY = "android.ongoingActivityNoti.nowbarSecondaryInfo"
        private const val SAMSUNG_PROGRESS = "android.ongoingActivityNoti.progress"
        private const val SAMSUNG_PROGRESS_MAX = "android.ongoingActivityNoti.progressMax"
        private const val SAMSUNG_PROGRESS_INDETERMINATE = "android.ongoingActivityNoti.progressIndeterminate"
        private const val SAMSUNG_SHOW_PROGRESS = "android.ongoingActivityNoti.showProgress"
    }

    private val notificationManager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

    // Track last update to implement debouncing
    private var lastUpdateTime = 0L
    private var lastProgress = -1
    private val updateDebounceMs = 500L

    init {
        createNotificationChannel()
    }

    private fun createNotificationChannel() {
        notificationManager.deleteNotificationChannel("bambu_print_progress")

        val channel = NotificationChannel(
            CHANNEL_ID,
            CHANNEL_NAME,
            NotificationManager.IMPORTANCE_HIGH
        ).apply {
            description = CHANNEL_DESCRIPTION
            enableVibration(false)
            setSound(null, null)
            lockscreenVisibility = Notification.VISIBILITY_PUBLIC
            setShowBadge(true)
        }

        notificationManager.createNotificationChannel(channel)
        Log.d(TAG, "Notification channel created: $CHANNEL_ID with IMPORTANCE_HIGH")
    }

    /**
     * Posts or updates the Live Update notification.
     *
     * @param progress Print progress 0-100
     * @param timeRemaining Formatted time remaining string (e.g., "2h 15m")
     * @param jobName Name of the print job
     * @param layerInfo Optional layer info string (e.g., "150/300")
     * @param isStarting True if printer is preparing (homing, leveling, heating) - shows "Starting..." instead of percentage
     */
    fun postLiveUpdate(progress: Int, timeRemaining: String, jobName: String? = null, layerInfo: String? = null, isStarting: Boolean = false) {
        val now = System.currentTimeMillis()
        val progressDelta = kotlin.math.abs(progress - lastProgress)

        // Debounce unless significant progress change
        if (now - lastUpdateTime < updateDebounceMs && progressDelta < 1) {
            Log.v(TAG, "Debouncing update - too rapid")
            return
        }
        lastUpdateTime = now
        lastProgress = progress

        val isCompleted = progress >= 100

        val notification = if (Build.VERSION.SDK_INT >= 36) {
            buildProgressStyleNotification(progress, timeRemaining, jobName, layerInfo, isCompleted, isStarting)
        } else {
            buildCompatNotification(progress, timeRemaining, jobName, layerInfo, isCompleted, isStarting)
        }

        notificationManager.notify(NOTIFICATION_ID, notification)
        Log.d(TAG, "Posted Live Update: $progress%, time: $timeRemaining, job: $jobName")
    }

    /**
     * Builds a Live Update notification using Android 16's ProgressStyle.
     *
     * Display locations:
     * 1. Status bar chip: Shows percentage from chipExpandedText
     * 2. Now Bar (lock screen): Shows progress bar with nowbarPrimaryInfo/nowbarSecondaryInfo
     * 3. Notification panel: Shows full notification with title, text, and progress bar
     */
    @RequiresApi(36)
    private fun buildProgressStyleNotification(
        progress: Int,
        timeRemaining: String,
        jobName: String?,
        layerInfo: String?,
        isCompleted: Boolean,
        isStarting: Boolean = false
    ): Notification {
        // Content for different display locations
        val title = jobName?.takeIf { it.isNotEmpty() } ?: "3D Print"

        // Status bar chip: Show "Starting..." or percentage
        val chipText = if (isStarting) "Starting..." else "$progress%"

        // Now Bar / Lock screen: Show "Starting..." or percentage with time
        val nowBarPrimary = title
        val nowBarSecondary = if (isStarting) {
            "Starting..."
        } else {
            "$progress%    $timeRemaining"
        }

        // Notification panel: Full info
        val panelText = buildString {
            if (isStarting) {
                append("Starting... Preparing printer")
            } else {
                append("$progress%")
                if (timeRemaining.isNotEmpty() && !isCompleted) {
                    append(" • $timeRemaining remaining")
                }
                layerInfo?.let { append(" • Layer $it") }
            }
        }

        // Progress value on 0-1000 scale for precision
        // When starting, show a small animated segment to indicate activity
        val progressValue = if (isStarting) 50 else progress * 10

        // Create ProgressStyle with tracker icon
        val trackerIcon = Icon.createWithResource(context, R.drawable.printer_3d_nozzle)
        Log.d(TAG, "Setting tracker icon: $trackerIcon for progress: $progressValue")

        val progressStyle = Notification.ProgressStyle()
            .setStyledByProgress(true)
            .setProgress(progressValue)
            .setProgressTrackerIcon(trackerIcon)
            .setProgressStartIcon(Icon.createWithResource(context, R.drawable.ic_printer))
            .setProgressEndIcon(Icon.createWithResource(context, R.drawable.ic_printer))

        // Add progress segments for visual bar
        val segments = mutableListOf<Notification.ProgressStyle.Segment>()

        if (isStarting) {
            // Show pulsing/starting indicator - small blue segment
            segments.add(
                Notification.ProgressStyle.Segment(50)
                    .setColor(Color.parseColor(ACCENT_COLOR))
            )
            segments.add(
                Notification.ProgressStyle.Segment(950)
                    .setColor(Color.parseColor(PROGRESS_GRAY))
            )
        } else {
            // Normal progress display
            // Completed segment (blue)
            if (progressValue > 0) {
                segments.add(
                    Notification.ProgressStyle.Segment(progressValue)
                        .setColor(Color.parseColor(ACCENT_COLOR))
                )
            }

            // Remaining segment (dark gray)
            if (progressValue < 1000) {
                segments.add(
                    Notification.ProgressStyle.Segment(1000 - progressValue)
                        .setColor(Color.parseColor(PROGRESS_GRAY))
                )
            }
        }

        if (segments.isNotEmpty()) {
            progressStyle.setProgressSegments(segments)
        }

        // Calculate ETA for when field
        val etaMillis = parseTimeRemainingToMillis(timeRemaining)

        // Build Samsung/Android extras
        val extras = buildExtrasBundle(progress, timeRemaining, title, chipText, nowBarPrimary, nowBarSecondary, isCompleted, isStarting)

        // Large icon for notification (higher res vehicle/printer image)
        val largeIcon = Icon.createWithResource(context, R.drawable.printer_3d_nozzle)

        return Notification.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_printer)
            .setLargeIcon(largeIcon)
            .setContentTitle(title)
            .setContentText(panelText)
            .setStyle(progressStyle)
            .setOngoing(!isCompleted)
            .setOnlyAlertOnce(true)
            .setCategory(Notification.CATEGORY_PROGRESS)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .setContentIntent(getLaunchIntent())
            .setAutoCancel(isCompleted)
            .setColorized(false)
            .setWhen(System.currentTimeMillis() + etaMillis)
            .setShowWhen(!isCompleted)
            .setUsesChronometer(false)
            .setFlag(Notification.FLAG_ONGOING_EVENT, !isCompleted)
            .addExtras(extras)
            .build()
    }

    /**
     * Fallback notification for pre-Android 16 devices.
     */
    private fun buildCompatNotification(
        progress: Int,
        timeRemaining: String,
        jobName: String?,
        layerInfo: String?,
        isCompleted: Boolean,
        isStarting: Boolean = false
    ): Notification {
        val title = jobName?.takeIf { it.isNotEmpty() } ?: "3D Print Progress"

        val contentText = buildString {
            if (isStarting) {
                append("Starting... Preparing printer")
            } else {
                append("$progress%")
                if (timeRemaining.isNotEmpty() && !isCompleted) {
                    append(" • $timeRemaining remaining")
                }
                layerInfo?.let { append(" • Layer $it") }
            }
        }

        val etaMillis = parseTimeRemainingToMillis(timeRemaining)

        val chipText = if (isStarting) "Starting..." else "$progress%"
        val nowBarPrimary = title
        val nowBarSecondary = if (isStarting) "Starting..." else "$progress%    $timeRemaining"
        val displayProgress = if (isStarting) 5 else progress  // Show small progress when starting

        val extras = buildExtrasBundle(displayProgress, timeRemaining, title, chipText, nowBarPrimary, nowBarSecondary, isCompleted)

        return NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_printer)
            .setContentTitle(title)
            .setContentText(contentText)
            .setProgress(100, displayProgress, isStarting)  // Indeterminate when starting
            .setOngoing(!isCompleted)
            .setOnlyAlertOnce(true)
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(getLaunchIntent())
            .setAutoCancel(isCompleted)
            .setColorized(false)
            .setWhen(System.currentTimeMillis() + etaMillis)
            .setShowWhen(!isCompleted)
            .setUsesChronometer(false)
            .addExtras(extras)
            .build()
    }

    /**
     * Builds the extras bundle for Android 16 Live Updates and Samsung Now Bar.
     */
    private fun buildExtrasBundle(
        progress: Int,
        timeRemaining: String,
        title: String,
        chipText: String,
        nowBarPrimary: String,
        nowBarSecondary: String,
        isCompleted: Boolean,
        isStarting: Boolean = false
    ): Bundle {
        return Bundle().apply {
            // Android 16 Live Update promotion
            putBoolean(EXTRA_REQUEST_PROMOTED_ONGOING, true)

            // Samsung One UI Live Notification style (1 = standard style with progress)
            putInt(SAMSUNG_STYLE, 1)

            // Primary and secondary info for notification
            putString(SAMSUNG_PRIMARY_INFO, title)
            val secondaryInfo = if (isStarting) "Starting... Preparing printer" else "$progress% • $timeRemaining"
            putString(SAMSUNG_SECONDARY_INFO, secondaryInfo)

            // Status bar chip configuration - just shows percentage
            putInt(SAMSUNG_CHIP_BG_COLOR, Color.parseColor(ACCENT_COLOR))
            putParcelable(SAMSUNG_CHIP_ICON, Icon.createWithResource(context, R.drawable.ic_printer))
            putString(SAMSUNG_CHIP_EXPANDED_TEXT, chipText)

            // Action configuration
            putInt(SAMSUNG_ACTION_TYPE, 1)
            putInt(SAMSUNG_ACTION_PRIMARY_SET, 0)

            // Now Bar specific info (lock screen display)
            putString(SAMSUNG_NOWBAR_PRIMARY, nowBarPrimary)
            putString(SAMSUNG_NOWBAR_SECONDARY, nowBarSecondary)

            // Progress info for Samsung
            // Don't show progress bar when starting - only show when actual printing begins
            putBoolean(SAMSUNG_SHOW_PROGRESS, !isStarting)
            putBoolean(SAMSUNG_PROGRESS_INDETERMINATE, isStarting)
            putInt(SAMSUNG_PROGRESS, if (isStarting) 0 else progress)
            putInt(SAMSUNG_PROGRESS_MAX, 100)
        }
    }

    private fun parseTimeRemainingToMillis(timeRemaining: String): Long {
        var totalMinutes = 0L

        val hourMatch = Regex("""(\d+)h""").find(timeRemaining)
        val minMatch = Regex("""(\d+)m""").find(timeRemaining)

        hourMatch?.let { totalMinutes += it.groupValues[1].toLong() * 60 }
        minMatch?.let { totalMinutes += it.groupValues[1].toLong() }

        return totalMinutes * 60 * 1000
    }

    private fun getLaunchIntent(): PendingIntent {
        val launchIntent = context.packageManager.getLaunchIntentForPackage(BAMBOO_PACKAGE)
            ?: Intent().apply {
                setClassName(context.packageName, "${context.packageName}.MainActivity")
            }

        launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)

        return PendingIntent.getActivity(
            context,
            0,
            launchIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }

    fun cancelNotification() {
        notificationManager.cancel(NOTIFICATION_ID)
        lastProgress = -1
        Log.d(TAG, "Cancelled Live Update notification")
    }

    /**
     * Posts a completion notification that stays until user swipes it away.
     */
    fun postCompletionNotification(jobName: String? = null) {
        val title = jobName?.takeIf { it.isNotEmpty() } ?: "3D Print"

        val notification = if (Build.VERSION.SDK_INT >= 36) {
            buildFinalNotificationApi36(title, "Print Complete!", isCompleted = true)
        } else {
            buildFinalNotificationCompat(title, "Print Complete!", isCompleted = true)
        }

        notificationManager.notify(NOTIFICATION_ID, notification)
        Log.d(TAG, "Posted completion notification - stays until user dismisses")
    }

    /**
     * Posts a cancellation notification that stays until user swipes it away.
     */
    fun postCancellationNotification(jobName: String? = null) {
        val title = jobName?.takeIf { it.isNotEmpty() } ?: "3D Print"

        val notification = if (Build.VERSION.SDK_INT >= 36) {
            buildFinalNotificationApi36(title, "Print Cancelled", isCompleted = false)
        } else {
            buildFinalNotificationCompat(title, "Print Cancelled", isCompleted = false)
        }

        notificationManager.notify(NOTIFICATION_ID, notification)
        Log.d(TAG, "Posted cancellation notification - stays until user dismisses")
    }

    /**
     * Builds a final notification (completed or cancelled) that stays until user dismisses.
     * Not ongoing, not auto-cancel on tap, user must swipe to dismiss.
     */
    @RequiresApi(36)
    private fun buildFinalNotificationApi36(title: String, statusText: String, isCompleted: Boolean): Notification {
        val chipText = if (isCompleted) "Done!" else "Cancelled"
        val progressValue = if (isCompleted) 1000 else 0
        val segmentColor = if (isCompleted) Color.parseColor(ACCENT_COLOR) else Color.parseColor(PROGRESS_GRAY)

        val trackerIcon = Icon.createWithResource(context, R.drawable.printer_3d_nozzle)

        val progressStyle = Notification.ProgressStyle()
            .setStyledByProgress(true)
            .setProgress(progressValue)
            .setProgressTrackerIcon(trackerIcon)
            .setProgressStartIcon(Icon.createWithResource(context, R.drawable.ic_printer))
            .setProgressEndIcon(Icon.createWithResource(context, R.drawable.ic_printer))
            .setProgressSegments(listOf(
                Notification.ProgressStyle.Segment(1000).setColor(segmentColor)
            ))

        val extras = Bundle().apply {
            putBoolean(EXTRA_REQUEST_PROMOTED_ONGOING, false)  // Not ongoing - can be dismissed
            putInt(SAMSUNG_STYLE, 1)
            putString(SAMSUNG_PRIMARY_INFO, title)
            putString(SAMSUNG_SECONDARY_INFO, statusText)
            putInt(SAMSUNG_CHIP_BG_COLOR, Color.parseColor(ACCENT_COLOR))
            putParcelable(SAMSUNG_CHIP_ICON, Icon.createWithResource(context, R.drawable.ic_printer))
            putString(SAMSUNG_CHIP_EXPANDED_TEXT, chipText)
            putString(SAMSUNG_NOWBAR_PRIMARY, title)
            putString(SAMSUNG_NOWBAR_SECONDARY, statusText)
            putBoolean(SAMSUNG_SHOW_PROGRESS, false)
            putInt(SAMSUNG_PROGRESS, if (isCompleted) 100 else 0)
            putInt(SAMSUNG_PROGRESS_MAX, 100)
        }

        val largeIcon = Icon.createWithResource(context, R.drawable.printer_3d_nozzle)

        return Notification.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_printer)
            .setLargeIcon(largeIcon)
            .setContentTitle(title)
            .setContentText(statusText)
            .setStyle(progressStyle)
            .setOngoing(false)           // NOT ongoing - user can swipe away
            .setOnlyAlertOnce(true)
            .setCategory(Notification.CATEGORY_STATUS)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .setContentIntent(getLaunchIntent())
            .setAutoCancel(false)        // Don't auto-cancel on tap - only swipe dismisses
            .setColorized(false)
            .addExtras(extras)
            .build()
    }

    /**
     * Builds a final notification (completed or cancelled) for pre-API 36.
     */
    private fun buildFinalNotificationCompat(title: String, statusText: String, isCompleted: Boolean): Notification {
        val chipText = if (isCompleted) "Done!" else "Cancelled"

        val extras = Bundle().apply {
            putBoolean(EXTRA_REQUEST_PROMOTED_ONGOING, false)
            putInt(SAMSUNG_STYLE, 1)
            putString(SAMSUNG_PRIMARY_INFO, title)
            putString(SAMSUNG_SECONDARY_INFO, statusText)
            putInt(SAMSUNG_CHIP_BG_COLOR, Color.parseColor(ACCENT_COLOR))
            putString(SAMSUNG_CHIP_EXPANDED_TEXT, chipText)
            putString(SAMSUNG_NOWBAR_PRIMARY, title)
            putString(SAMSUNG_NOWBAR_SECONDARY, statusText)
            putBoolean(SAMSUNG_SHOW_PROGRESS, false)
            putInt(SAMSUNG_PROGRESS, if (isCompleted) 100 else 0)
            putInt(SAMSUNG_PROGRESS_MAX, 100)
        }

        return NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_printer)
            .setContentTitle(title)
            .setContentText(statusText)
            .setProgress(0, 0, false)    // Hide progress bar
            .setOngoing(false)           // NOT ongoing - user can swipe away
            .setOnlyAlertOnce(true)
            .setCategory(NotificationCompat.CATEGORY_STATUS)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(getLaunchIntent())
            .setAutoCancel(false)        // Don't auto-cancel on tap
            .setColorized(false)
            .addExtras(extras)
            .build()
    }

    fun isLiveUpdateSupported(): Boolean = Build.VERSION.SDK_INT >= 36

    fun canPostPromotedNotifications(): Boolean {
        return if (Build.VERSION.SDK_INT >= 36) {
            try {
                val method = notificationManager.javaClass.getMethod("canPostPromotedNotifications")
                method.invoke(notificationManager) as? Boolean ?: false
            } catch (e: Exception) {
                Log.w(TAG, "canPostPromotedNotifications check failed: ${e.message}")
                false
            }
        } else {
            false
        }
    }

    fun postTestNotification(progress: Int = 45, timeRemaining: String = "2h 15m") {
        Log.d(TAG, "Test notification - SDK: ${Build.VERSION.SDK_INT}, API 36+: ${Build.VERSION.SDK_INT >= 36}")
        postLiveUpdate(progress, timeRemaining, "Test Print Job", "150/300")
        Log.d(TAG, "Posted test notification (canPostPromoted: ${canPostPromotedNotifications()})")
    }

    /**
     * Posts a simple notification when server connects.
     * This is a regular notification (not a live update) that auto-dismisses on tap.
     */
    fun postServerConnectedNotification() {
        val notification = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_printer)
            .setContentTitle("Server Connected")
            .setContentText("Bambu FCM Bridge is running and monitoring your printer")
            .setOngoing(false)
            .setAutoCancel(true)
            .setCategory(NotificationCompat.CATEGORY_STATUS)
            .setVisibility(NotificationCompat.VISIBILITY_PUBLIC)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setContentIntent(getLaunchIntent())
            .build()

        // Use a different notification ID so it doesn't conflict with print progress
        notificationManager.notify(NOTIFICATION_ID + 1, notification)
        Log.d(TAG, "Posted server connected notification")
    }
}
