import ActivityKit
import Foundation
import SwiftUI

// MARK: - Printer Status Enum

/// Type-safe representation of printer states. Raw values match the APNs JSON wire format.
enum PrinterStatus: String, Codable, Hashable {
    case preparing = "starting"
    case printing
    case paused
    case issue
    case completed
    case cancelled
    case idle
}

// MARK: - Activity Attributes

/// Defines the data model for the 3D printer Live Activity.
/// Shared between the main app target and the widget extension target.
struct PrinterAttributes: ActivityAttributes {
    // Static data — set once when the Live Activity starts
    var printerName: String

    /// Dynamic content state — updated via ActivityKit push notifications.
    /// Field names are camelCase to match the APNs JSON payload keys exactly.
    struct ContentState: Codable, Hashable {
        var progress: Int              // 0-100
        var remainingMinutes: Int      // ETA in minutes
        var jobName: String            // print job name (can be empty)
        var layerNum: Int              // current layer number
        var totalLayers: Int           // total layer count
        var status: PrinterStatus      // current printer state
        var prepareStage: String?      // stage description (e.g. "Auto bed leveling", "Nozzle clog")
        var stageCategory: String?     // "prepare", "calibrate", "paused", "filament", "issue"
        var nozzleTemp: Int?           // current nozzle temperature (°C)
        var bedTemp: Int?              // current bed temperature (°C)
        var nozzleTargetTemp: Int?     // target nozzle temperature (°C)
        var bedTargetTemp: Int?        // target bed temperature (°C)
        var chamberTemp: Int?          // current chamber temperature (°C)

        // Map Swift property `status` to JSON key `state` for APNs wire compatibility
        enum CodingKeys: String, CodingKey {
            case progress, remainingMinutes, jobName, layerNum, totalLayers
            case status = "state"
            case prepareStage, stageCategory
            case nozzleTemp, bedTemp, nozzleTargetTemp, bedTargetTemp, chamberTemp
        }
    }
}

// MARK: - Convenience

extension PrinterAttributes.ContentState {
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
        switch status {
        case .preparing:
            if stageCategory == "calibrate" { return "Calibrating" }
            return "Preparing"
        case .printing:  return "Printing"
        case .paused:
            if stageCategory == "filament" { return "Filament" }
            return "Paused"
        case .issue:     return "Issue"
        case .completed: return "Complete"
        case .cancelled: return "Cancelled"
        case .idle:      return "Idle"
        }
    }

    /// Human-readable stage description, shown for preparing/paused/issue states
    var prepareStageLabel: String? {
        guard [.preparing, .paused, .issue].contains(status),
              let stage = prepareStage, !stage.isEmpty else { return nil }
        return stage
    }
}

// MARK: - UI Helpers

extension PrinterAttributes.ContentState {
    var iconName: String {
        switch status {
        case .completed: "checkmark.circle.fill"
        case .cancelled: "xmark.circle.fill"
        case .paused:    "pause.circle.fill"
        case .issue:     "exclamationmark.triangle.fill"
        case .preparing, .printing, .idle: "printer.fill"
        }
    }

    var accentColor: Color {
        switch status {
        case .completed: .green
        case .cancelled: .red
        case .preparing: .orange
        case .paused:    .yellow
        case .issue:     .red
        case .printing, .idle: .blue
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

    /// Abbreviated temperature lines for compact display: "N 150/220", "B 45/60", "C 28"
    struct TempLine: Identifiable {
        let id: String   // "N", "B", "C"
        let label: String
        let text: String
    }

    var compactTemperatureLines: [TempLine] {
        var lines: [TempLine] = []
        if let nozzle = nozzleTemp {
            let text = if let target = nozzleTargetTemp, target > 0 {
                "\(nozzle)/\(target)"
            } else {
                "\(nozzle)"
            }
            lines.append(TempLine(id: "N", label: "N", text: text))
        }
        if let bed = bedTemp {
            let text = if let target = bedTargetTemp, target > 0 {
                "\(bed)/\(target)"
            } else {
                "\(bed)"
            }
            lines.append(TempLine(id: "B", label: "B", text: text))
        }
        if let chamber = chamberTemp, chamber > 0 {
            lines.append(TempLine(id: "C", label: "C", text: "\(chamber)"))
        }
        return lines
    }

    var trailingText: String {
        switch status {
        case .completed: "Done"
        case .cancelled: "Stop"
        case .preparing: "..."
        case .paused:    "\(progress)%"
        case .issue:     "!"
        case .printing, .idle: "\(progress)%"
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
        status: .printing,
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
        status: .preparing,
        prepareStage: "Auto bed leveling",
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
        status: .completed
    )

    static let mockCancelled = PrinterAttributes.ContentState(
        progress: 37,
        remainingMinutes: 0,
        jobName: "Phone Case",
        layerNum: 111,
        totalLayers: 300,
        status: .cancelled
    )

    static let mockPaused = PrinterAttributes.ContentState(
        progress: 42,
        remainingMinutes: 83,
        jobName: "Benchy",
        layerNum: 150,
        totalLayers: 300,
        status: .paused,
        prepareStage: "Changing filament",
        stageCategory: "filament",
        nozzleTemp: 220,
        bedTemp: 60,
        chamberTemp: 38
    )

    static let mockIssue = PrinterAttributes.ContentState(
        progress: 42,
        remainingMinutes: 83,
        jobName: "Benchy",
        layerNum: 150,
        totalLayers: 300,
        status: .issue,
        prepareStage: "Paused: nozzle clog",
        stageCategory: "issue",
        nozzleTemp: 220,
        bedTemp: 60,
        chamberTemp: 38
    )
}

extension PrinterAttributes {
    static let preview = PrinterAttributes(printerName: "Bambu Lab P1S")
}
