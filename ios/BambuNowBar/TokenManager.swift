import ActivityKit
import Foundation
import FirebaseFirestore
import UIKit
import os

/// Manages push token lifecycle and Firestore sync for Live Activity push notifications.
@MainActor
@Observable
final class TokenManager {
    private let logger = Logger(subsystem: "com.elliot.bamboonowbar", category: "TokenManager")
    private let db = Firestore.firestore()
    private let deviceId: String

    var pushToStartToken: String = ""
    var activityPushToken: String = ""
    var isSynced: Bool = false
    var activitiesEnabled: Bool = false
    var statusMessage: String = "Initializing..."

    init() {
        // Stable device ID persisted across app launches
        if let existing = UserDefaults.standard.string(forKey: "deviceId") {
            self.deviceId = existing
        } else {
            let newId = UUID().uuidString
            UserDefaults.standard.set(newId, forKey: "deviceId")
            self.deviceId = newId
        }
    }

    /// Start observing push tokens and sync to Firestore.
    func startObserving() {
        activitiesEnabled = ActivityAuthorizationInfo().areActivitiesEnabled

        // Register for remote notifications — required for push tokens
        UIApplication.shared.registerForRemoteNotifications()

        // Verify Firestore connection immediately
        Task { await verifyFirestoreConnection() }

        // Start observing push tokens
        Task { await observePushToStartToken() }
        Task { await observeActivityUpdates() }

        statusMessage = activitiesEnabled
            ? "Waiting for push-to-start token..."
            : "Live Activities disabled in Settings"
    }

    // MARK: - Firestore Connection Verification

    private func verifyFirestoreConnection() async {
        do {
            // Write a minimal document to verify Firestore is reachable
            try await db.collection("bambu_tokens").document(deviceId).setData([
                "platform": "ios",
                "updatedAt": FieldValue.serverTimestamp(),
            ], merge: true)
            isSynced = true
            statusMessage = "Firestore connected. Waiting for push-to-start token..."
            logger.info("Firestore connection verified")
        } catch {
            isSynced = false
            statusMessage = "Firestore error: \(error.localizedDescription)"
            logger.error("Firestore verification failed: \(error.localizedDescription)")
        }
    }

    // MARK: - Push-to-Start Token

    private func observePushToStartToken() async {
        for await tokenData in Activity<PrinterAttributes>.pushToStartTokenUpdates {
            let token = tokenData.map { String(format: "%02x", $0) }.joined()
            logger.info("Push-to-start token: \(token)")
            pushToStartToken = token
            statusMessage = "Token received, syncing..."
            await syncTokensToFirestore()
        }
    }

    // MARK: - Activity Updates

    private func observeActivityUpdates() async {
        for await activity in Activity<PrinterAttributes>.activityUpdates {
            logger.info("New activity: \(activity.id)")
            Task { await observeActivityPushToken(activity) }
        }
    }

    private func observeActivityPushToken(_ activity: Activity<PrinterAttributes>) async {
        for await tokenData in activity.pushTokenUpdates {
            let token = tokenData.map { String(format: "%02x", $0) }.joined()
            logger.info("Activity push token: \(token)")
            activityPushToken = token
            await syncTokensToFirestore()
        }
    }

    // MARK: - Firestore Sync

    private func syncTokensToFirestore() async {
        var data: [String: Any] = [
            "updatedAt": FieldValue.serverTimestamp(),
            "platform": "ios",
        ]

        if !pushToStartToken.isEmpty {
            data["pushToStartToken"] = pushToStartToken
        }
        if !activityPushToken.isEmpty {
            data["activityPushToken"] = activityPushToken
        }

        do {
            try await db.collection("bambu_tokens").document(deviceId).setData(data, merge: true)
            isSynced = true
            statusMessage = "Token synced to Firestore"
            logger.info("Tokens synced to Firestore")
        } catch {
            isSynced = false
            statusMessage = "Sync failed: \(error.localizedDescription)"
            logger.error("Firestore sync failed: \(error.localizedDescription)")
        }
    }

    // MARK: - Clipboard

    func copyPushToStartToken() {
        UIPasteboard.general.string = pushToStartToken
    }
}
