import ActivityKit
import Foundation

/// Defines the data model for the 3D printer Live Activity.
/// Shared between the main app target and the widget extension target.
struct PrinterAttributes: ActivityAttributes {
    // Static data — set once when the Live Activity starts
    var printerName: String

    /// Dynamic content state — updated via ActivityKit push notifications.
    /// Field names are camelCase to match the APNs JSON payload keys exactly.
    struct ContentState: Codable, Hashable {
        var progress: Int           // 0-100
        var remainingMinutes: Int   // ETA in minutes
        var jobName: String         // print job name (can be empty)
        var layerNum: Int           // current layer number
        var totalLayers: Int        // total layer count
        var state: String           // "starting", "printing", "completed", "cancelled", "idle"
    }
}

// MARK: - Convenience

extension PrinterAttributes.ContentState {
    var isStarting: Bool { state == "starting" }
    var isPrinting: Bool { state == "printing" }
    var isCompleted: Bool { state == "completed" }
    var isCancelled: Bool { state == "cancelled" }
    var isIdle: Bool { state == "idle" }

    var formattedTime: String {
        guard remainingMinutes > 0 else { return "<1m" }
        let hours = remainingMinutes / 60
        let mins = remainingMinutes % 60
        if hours > 0 {
            return "\(hours)h \(mins)m"
        }
        return "\(mins)m"
    }

    var layerInfo: String? {
        guard totalLayers > 0 else { return nil }
        return "\(layerNum)/\(totalLayers)"
    }

    var displayTitle: String {
        jobName.isEmpty ? "3D Print" : jobName
    }

    var stateLabel: String {
        switch state {
        case "starting": return "Starting"
        case "printing": return "Printing"
        case "completed": return "Complete"
        case "cancelled": return "Cancelled"
        case "idle": return "Idle"
        default: return state.capitalized
        }
    }
}

// MARK: - Preview Mock Data

extension PrinterAttributes.ContentState {
    static let mockPrinting = PrinterAttributes.ContentState(
        progress: 42,
        remainingMinutes: 83,
        jobName: "Benchy",
        layerNum: 150,
        totalLayers: 300,
        state: "printing"
    )

    static let mockStarting = PrinterAttributes.ContentState(
        progress: 0,
        remainingMinutes: 240,
        jobName: "Phone Stand",
        layerNum: 0,
        totalLayers: 500,
        state: "starting"
    )

    static let mockCompleted = PrinterAttributes.ContentState(
        progress: 100,
        remainingMinutes: 0,
        jobName: "Benchy",
        layerNum: 300,
        totalLayers: 300,
        state: "completed"
    )

    static let mockCancelled = PrinterAttributes.ContentState(
        progress: 37,
        remainingMinutes: 0,
        jobName: "Phone Case",
        layerNum: 111,
        totalLayers: 300,
        state: "cancelled"
    )
}

extension PrinterAttributes {
    static let preview = PrinterAttributes(printerName: "Bambu Lab P1S")
}
