import BackgroundTasks
import UIKit
import os

class AppDelegate: NSObject, UIApplicationDelegate {
    private let logger = Logger(subsystem: "com.elliot.bamboonowbar", category: "AppDelegate")

    static let backgroundTaskIdentifier = "com.elliot.bamboonowbar.tokenRefresh"

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        registerBackgroundTask()
        return true
    }

    // MARK: - BGTaskScheduler

    private func registerBackgroundTask() {
        let success = BGTaskScheduler.shared.register(
            forTaskWithIdentifier: Self.backgroundTaskIdentifier,
            using: nil
        ) { [weak self] task in
            guard let bgTask = task as? BGAppRefreshTask else { return }
            self?.handleAppRefresh(bgTask)
        }
        if success {
            logger.info("Background task registered")
        } else {
            logger.error("Failed to register background task")
        }
    }

    private func handleAppRefresh(_ task: BGAppRefreshTask) {
        logger.info("Background app refresh triggered")

        scheduleAppRefresh()

        let tokenManager = TokenManager()

        task.expirationHandler = { [self] in
            logger.warning("Background task expired before completing")
            task.setTaskCompleted(success: false)
        }

        Task { @MainActor in
            await tokenManager.refreshTokensInBackground()
            task.setTaskCompleted(success: true)
            logger.info("Background token refresh completed")
        }
    }

    func scheduleAppRefresh() {
        let request = BGAppRefreshTaskRequest(identifier: Self.backgroundTaskIdentifier)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 60 * 60)

        do {
            try BGTaskScheduler.shared.submit(request)
            logger.info("Scheduled next background refresh")
        } catch {
            logger.error("Failed to schedule background refresh: \(error.localizedDescription)")
        }
    }
}
