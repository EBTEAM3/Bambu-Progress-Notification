import ActivityKit
import Foundation
import SwiftUI

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
        var nozzleTemp: Int?        // current nozzle temperature (°C)
        var bedTemp: Int?           // current bed temperature (°C)
        var nozzleTargetTemp: Int?  // target nozzle temperature (°C)
        var bedTargetTemp: Int?     // target bed temperature (°C)
        var chamberTemp: Int?       // current chamber temperature (°C)
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

    var temperatureInfo: String? {
        guard let nozzle = nozzleTemp, let bed = bedTemp else { return nil }
        let nozzleStr = if let target = nozzleTargetTemp, target > 0 {
            "\(nozzle)/\(target)°C"
        } else {
            "\(nozzle)°C"
        }
        let bedStr = if let target = bedTargetTemp, target > 0 {
            "\(bed)/\(target)°C"
        } else {
            "\(bed)°C"
        }
        var result = "Nozzle \(nozzleStr) · Bed \(bedStr)"
        if let chamber = chamberTemp, chamber > 0 {
            result += " · Chamber \(chamber)°C"
        }
        return result
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

// MARK: - UI Helpers

extension PrinterAttributes.ContentState {
    var iconName: String {
        switch state {
        case "completed": "checkmark.circle.fill"
        case "cancelled": "xmark.circle.fill"
        default: "printer.fill"
        }
    }

    var accentColor: Color {
        switch state {
        case "completed": .green
        case "cancelled": .red
        case "starting": .orange
        default: .blue
        }
    }

    var compactLeadingTemp: String {
        if let chamber = chamberTemp, chamber > 0 {
            return "\(chamber)°"
        }
        if let nozzle = nozzleTemp, nozzle > 0 {
            return "\(nozzle)°"
        }
        return "—"
    }

    var trailingText: String {
        switch state {
        case "completed": "Done"
        case "cancelled": "Stop"
        case "starting": "..."
        default: "\(progress)%"
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
        state: "printing",
        nozzleTemp: 220,
        bedTemp: 60,
        chamberTemp: 38
    )

    static let mockStarting = PrinterAttributes.ContentState(
        progress: 0,
        remainingMinutes: 240,
        jobName: "Phone Stand",
        layerNum: 0,
        totalLayers: 500,
        state: "starting",
        nozzleTemp: 150,
        bedTemp: 45,
        nozzleTargetTemp: 220,
        bedTargetTemp: 60,
        chamberTemp: 28
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
