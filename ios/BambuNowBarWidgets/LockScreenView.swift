import SwiftUI
import WidgetKit

struct LockScreenView: View {
    let state: PrinterAttributes.ContentState
    let attributes: PrinterAttributes

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Top row: icon + job name + state badge
            HStack {
                Image(systemName: state.iconName)
                    .foregroundColor(state.accentColor)
                Text(state.displayTitle)
                    .font(.headline)
                    .lineLimit(1)
                Spacer()
                Text(state.stateLabel)
                    .font(.caption)
                    .fontWeight(.medium)
                    .foregroundColor(state.accentColor)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(state.accentColor.opacity(0.2))
                    .clipShape(Capsule())
            }

            // Progress bar
            switch state.status {
            case .preparing:
                ProgressView()
                    .progressViewStyle(.linear)
                    .tint(.blue)
            case .paused:
                ProgressView(value: Double(state.progress), total: 100)
                    .tint(.yellow)
            case .issue:
                ProgressView(value: Double(state.progress), total: 100)
                    .tint(.red)
            case .printing, .completed, .cancelled, .idle:
                ProgressView(value: Double(state.progress), total: 100)
                    .tint(state.accentColor)
            }

            // Bottom row
            HStack(alignment: .top) {
                switch state.status {
                case .preparing:
                    if let stage = state.prepareStageLabel {
                        Label(stage, systemImage: "gearshape.2")
                            .font(.caption)
                            .foregroundColor(.orange)
                    }
                    Spacer()
                    CompactTemperatureView(lines: state.compactTemperatureLines)
                case .paused, .issue:
                    if let stage = state.prepareStageLabel {
                        Label(stage, systemImage: state.iconName)
                            .font(.caption)
                            .foregroundColor(state.accentColor)
                    }
                    Spacer()
                    if let layers = state.layerInfo {
                        Label("Layer \(layers)", systemImage: "square.stack.3d.up")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    Text("\(state.progress)%")
                        .font(.title2)
                        .fontWeight(.bold)
                        .foregroundColor(state.accentColor)
                case .completed:
                    if let layers = state.layerInfo {
                        Label("Layer \(layers)", systemImage: "square.stack.3d.up")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                    Text("Print complete!")
                        .font(.caption)
                        .foregroundColor(.green)
                case .cancelled:
                    if let layers = state.layerInfo {
                        Label("Layer \(layers)", systemImage: "square.stack.3d.up")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                    Text("Print cancelled")
                        .font(.caption)
                        .foregroundColor(.red)
                case .printing, .idle:
                    if let layers = state.layerInfo {
                        Label("Layer \(layers)", systemImage: "square.stack.3d.up")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                    Text("\(state.formattedTime) remaining")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text("\(state.progress)%")
                        .font(.title2)
                        .fontWeight(.bold)
                        .foregroundColor(state.accentColor)
                }
            }

            // Temperature row (shown for printing, paused, and issue states)
            if [.printing, .idle, .paused, .issue].contains(state.status) {
                CompactTemperatureView(lines: state.compactTemperatureLines, layout: .horizontal)
            }
        }
        .padding()
        .activityBackgroundTint(Color.black.opacity(0.6))
    }
}
