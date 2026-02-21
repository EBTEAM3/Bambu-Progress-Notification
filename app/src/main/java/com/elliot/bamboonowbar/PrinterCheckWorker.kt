package com.elliot.bamboonowbar

import android.content.Context
import android.util.Log
import androidx.work.*
import org.eclipse.paho.client.mqttv3.*
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence
import org.json.JSONObject
import java.security.SecureRandom
import java.security.cert.X509Certificate
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import javax.net.ssl.TrustManager
import javax.net.ssl.X509TrustManager

/**
 * Battery-efficient WorkManager worker that periodically checks printer status.
 * Only used when printer is idle - when printing starts, the persistent service takes over.
 */
class PrinterCheckWorker(
    context: Context,
    workerParams: WorkerParameters
) : Worker(context, workerParams) {

    companion object {
        private const val TAG = "PrinterCheckWorker"
        const val WORK_NAME = "printer_check_work"

        // Bambu Cloud MQTT Configuration (same as service)
        // NOTE: This worker is unused in FCM mode. Credentials removed for security.
        private const val MQTT_SERVER = "ssl://us.mqtt.bambulab.com:8883"
        private const val USER_ID = "YOUR_USER_ID"
        private const val ACCESS_TOKEN = "YOUR_ACCESS_TOKEN"
        private const val PRINTER_SERIAL = "YOUR_PRINTER_SERIAL"

        /**
         * Schedule periodic printer checks (every 15 minutes - Android minimum)
         */
        fun schedule(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val request = PeriodicWorkRequestBuilder<PrinterCheckWorker>(
                15, TimeUnit.MINUTES  // Minimum allowed by Android
            )
                .setConstraints(constraints)
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 1, TimeUnit.MINUTES)
                .build()

            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                request
            )
            Log.d(TAG, "Scheduled periodic printer check (every 15 min)")
        }

        /**
         * Cancel all periodic checks
         */
        fun cancel(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
            Log.d(TAG, "Cancelled periodic printer checks")
        }

        /**
         * Do a one-time immediate check
         */
        fun checkNow(context: Context) {
            val request = OneTimeWorkRequestBuilder<PrinterCheckWorker>()
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .build()

            WorkManager.getInstance(context).enqueue(request)
            Log.d(TAG, "Queued immediate printer check")
        }
    }

    override fun doWork(): Result {
        Log.d(TAG, "Starting printer check...")

        var client: MqttAsyncClient? = null
        val latch = CountDownLatch(1)
        var isPrinting = false
        var printState = ""

        try {
            val clientId = "android_check_${System.currentTimeMillis()}"
            client = MqttAsyncClient(MQTT_SERVER, clientId, MemoryPersistence())

            val options = MqttConnectOptions().apply {
                userName = USER_ID
                password = ACCESS_TOKEN.toCharArray()
                isCleanSession = true
                connectionTimeout = 10
                keepAliveInterval = 30
                socketFactory = createTrustAllSocketFactory()
                isAutomaticReconnect = false  // Don't reconnect - this is a quick check
            }

            client.setCallback(object : MqttCallback {
                override fun connectionLost(cause: Throwable?) {
                    Log.w(TAG, "Connection lost during check: ${cause?.message}")
                    latch.countDown()
                }

                override fun messageArrived(topic: String?, message: MqttMessage?) {
                    try {
                        message?.let {
                            val json = JSONObject(String(it.payload))
                            if (json.has("print")) {
                                val printData = json.getJSONObject("print")
                                if (printData.has("gcode_state")) {
                                    printState = printData.optString("gcode_state", "")
                                    isPrinting = printState in listOf("RUNNING", "PRINTING", "PREPARE")
                                    Log.d(TAG, "Printer state: $printState, isPrinting: $isPrinting")
                                }
                            }
                        }
                    } catch (e: Exception) {
                        Log.e(TAG, "Error parsing message: ${e.message}")
                    }
                    latch.countDown()
                }

                override fun deliveryComplete(token: IMqttDeliveryToken?) {}
            })

            // Connect
            client.connect(options).waitForCompletion(10000)

            if (client.isConnected) {
                // Subscribe and request status
                val topic = "device/$PRINTER_SERIAL/report"
                client.subscribe(topic, 1).waitForCompletion(5000)

                // Request current state
                val requestTopic = "device/$PRINTER_SERIAL/request"
                val payload = """{"pushing": {"sequence_id": "0", "command": "pushall"}}"""
                client.publish(requestTopic, MqttMessage(payload.toByteArray()))

                // Wait for response (max 15 seconds)
                latch.await(15, TimeUnit.SECONDS)

                // Disconnect
                try {
                    client.disconnect().waitForCompletion(3000)
                    client.close()
                } catch (e: Exception) {
                    Log.w(TAG, "Disconnect error: ${e.message}")
                }
            }

        } catch (e: Exception) {
            Log.e(TAG, "Check failed: ${e.message}")
            return Result.retry()
        } finally {
            try {
                client?.close()
            } catch (e: Exception) { }
        }

        // If printer is printing, start the full service
        if (isPrinting) {
            Log.d(TAG, "Printer is printing! Starting full service...")
            startFullService()
        } else {
            Log.d(TAG, "Printer is idle ($printState). Next check in 15 min.")
        }

        return Result.success()
    }

    private fun startFullService() {
        val intent = android.content.Intent(applicationContext, BambuMqttService::class.java).apply {
            action = BambuMqttService.ACTION_START
        }
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            applicationContext.startForegroundService(intent)
        } else {
            applicationContext.startService(intent)
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
}
