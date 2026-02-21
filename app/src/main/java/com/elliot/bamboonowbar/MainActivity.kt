package com.elliot.bamboonowbar

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.util.Log
import android.view.View
import android.widget.SeekBar
import android.widget.Toast
import android.content.Intent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.elliot.bamboonowbar.databinding.ActivityMainBinding
import com.google.firebase.messaging.FirebaseMessaging

/**
 * Main activity for Bambu Now Bar.
 * FCM-only mode - receives push notifications from server.
 */
class MainActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "MainActivity"
    }

    private lateinit var binding: ActivityMainBinding
    private lateinit var liveUpdateManager: LiveUpdateManager

    // Permission request launcher
    private val notificationPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        Log.d(TAG, "POST_NOTIFICATIONS permission granted: $isGranted")
        updateNotificationPermissionStatus()
        if (isGranted) {
            Toast.makeText(this, "Notification permission granted!", Toast.LENGTH_SHORT).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        liveUpdateManager = LiveUpdateManager(this)

        setupUI()
        updateNotificationPermissionStatus()
        requestNotificationPermissionIfNeeded()

        // Get FCM token and display it
        getFCMToken()
    }

    private fun getFCMToken() {
        FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
            if (task.isSuccessful) {
                val token = task.result
                Log.d(TAG, "=" .repeat(50))
                Log.d(TAG, "FCM Token (copy to server):")
                Log.d(TAG, token)
                Log.d(TAG, "=" .repeat(50))

                // Save token
                getSharedPreferences("fcm_prefs", MODE_PRIVATE)
                    .edit()
                    .putString("fcm_token", token)
                    .apply()

                // Update UI
                runOnUiThread {
                    binding.tvConnectionStatus.text = "FCM Ready - Waiting for server"
                    binding.tvConnectionStatus.setTextColor(getColor(android.R.color.holo_green_dark))
                }
            } else {
                Log.e(TAG, "Failed to get FCM token", task.exception)
                runOnUiThread {
                    binding.tvConnectionStatus.text = "FCM Error - check logs"
                    binding.tvConnectionStatus.setTextColor(getColor(android.R.color.holo_red_dark))
                }
            }
        }
    }

    private fun showFCMToken() {
        val token = getSharedPreferences("fcm_prefs", MODE_PRIVATE)
            .getString("fcm_token", null)

        if (token != null) {
            // Copy to clipboard
            val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
            val clip = android.content.ClipData.newPlainText("FCM Token", token)
            clipboard.setPrimaryClip(clip)

            Toast.makeText(this, "FCM Token copied to clipboard!\nPaste into server script.", Toast.LENGTH_LONG).show()
            Log.d(TAG, "FCM Token copied: $token")
        } else {
            Toast.makeText(this, "FCM Token not ready yet. Try again.", Toast.LENGTH_SHORT).show()
            getFCMToken()
        }
    }

    private fun setupUI() {
        // Notification permission button
        binding.btnNotificationPermission.setOnClickListener {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                    != PackageManager.PERMISSION_GRANTED) {
                    notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
                } else {
                    openAppNotificationSettings()
                }
            } else {
                openAppNotificationSettings()
            }
        }

        // Connect button - copies FCM token
        binding.btnConnect.text = "Copy FCM Token"
        binding.btnConnect.setOnClickListener {
            showFCMToken()
        }

        // Developer Options button (for "Live notifications for all apps" toggle)
        binding.btnDevOptions.setOnClickListener {
            openDeveloperOptions()
        }

        // Battery optimization button - not needed for FCM but keep for reference
        binding.btnBatteryOptimization.setOnClickListener {
            Toast.makeText(this, "Not needed for FCM mode - server handles everything!", Toast.LENGTH_LONG).show()
        }

        // Test notification button
        binding.btnTestNotification.setOnClickListener {
            Log.d(TAG, "Test button clicked")
            val progress = binding.seekbarProgress.progress
            val timeRemaining = calculateTimeFromProgress(progress)
            liveUpdateManager.postTestNotification(progress, timeRemaining)
            Toast.makeText(this, "Test notification sent: $progress%", Toast.LENGTH_SHORT).show()
        }

        // Clear notification button
        binding.btnClearNotification.setOnClickListener {
            liveUpdateManager.cancelNotification()
            Toast.makeText(this, "Notification cleared", Toast.LENGTH_SHORT).show()
        }

        // Progress seekbar
        binding.seekbarProgress.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(seekBar: SeekBar?, progress: Int, fromUser: Boolean) {
                binding.tvProgressValue.text = "$progress%"
            }
            override fun onStartTrackingTouch(seekBar: SeekBar?) {}
            override fun onStopTrackingTouch(seekBar: SeekBar?) {}
        })

        binding.tvProgressValue.text = "${binding.seekbarProgress.progress}%"
        binding.tvDeviceInfo.text = PermissionHelper.getDeviceInfo()
        binding.cardTestSection.visibility = View.VISIBLE

        // Hide printer state section - will be shown when FCM data arrives
        binding.layoutPrinterState.visibility = View.GONE
    }

    private fun hasNotificationPermission(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) ==
                PackageManager.PERMISSION_GRANTED
        } else {
            true
        }
    }

    private fun requestNotificationPermissionIfNeeded() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
                notificationPermissionLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
        }
    }

    private fun updateNotificationPermissionStatus() {
        val isGranted = hasNotificationPermission()

        if (isGranted) {
            binding.tvNotificationPermissionStatus.text = "Granted"
            binding.tvNotificationPermissionStatus.setTextColor(
                ContextCompat.getColor(this, android.R.color.holo_blue_dark)
            )
            binding.btnNotificationPermission.text = "Settings"
        } else {
            binding.tvNotificationPermissionStatus.text = "Required"
            binding.tvNotificationPermissionStatus.setTextColor(
                ContextCompat.getColor(this, android.R.color.holo_red_dark)
            )
            binding.btnNotificationPermission.text = "Grant"
        }
    }

    private fun openAppNotificationSettings() {
        val intent = Intent().apply {
            action = Settings.ACTION_APP_NOTIFICATION_SETTINGS
            putExtra(Settings.EXTRA_APP_PACKAGE, packageName)
        }
        startActivity(intent)
    }

    private fun openDeveloperOptions() {
        try {
            val intent = Intent(Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS)
            startActivity(intent)
            Toast.makeText(
                this,
                "Look for 'Live notifications for all apps' toggle and enable it",
                Toast.LENGTH_LONG
            ).show()
        } catch (e: Exception) {
            Toast.makeText(
                this,
                "Developer Options not available. Enable it in Settings → About phone → Tap Build number 7 times",
                Toast.LENGTH_LONG
            ).show()
        }
    }

    private fun calculateTimeFromProgress(progress: Int): String {
        val totalMinutes = 240
        val remainingMinutes = ((100 - progress) * totalMinutes) / 100
        val hours = remainingMinutes / 60
        val minutes = remainingMinutes % 60

        return when {
            hours > 0 && minutes > 0 -> "${hours}h ${minutes}m"
            hours > 0 -> "${hours}h"
            minutes > 0 -> "${minutes}m"
            else -> "<1m"
        }
    }

    override fun onResume() {
        super.onResume()
        updateNotificationPermissionStatus()
        // Refresh FCM token
        getFCMToken()
        // Check server status from SharedPreferences
        checkServerStatus()
    }

    private fun checkServerStatus() {
        val prefs = getSharedPreferences("fcm_prefs", MODE_PRIVATE)
        val serverActive = prefs.getBoolean("server_active", false)
        val connectedTime = prefs.getLong("server_connected_time", 0)

        // Consider server "active" if connected within last 5 minutes
        val isRecent = System.currentTimeMillis() - connectedTime < 5 * 60 * 1000

        if (serverActive && isRecent) {
            binding.tvConnectionStatus.text = "Server Active"
            binding.tvConnectionStatus.setTextColor(getColor(android.R.color.holo_green_dark))
        }
    }
}
