import SwiftUI
import WidgetKit

struct ExpandedBottomView: View {
    let state: PrinterAttributes.ContentState

    var body: some View {
        VStack(spacing: 10) {
            // Icon + job name
            HStack(spacing: 6) {
                Image(systemName: state.iconName)
                    .foregroundColor(state.accentColor)
                Text(state.displayTitle)
                    .font(.headline)
                    .lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            // Progress bar + details
            switch state.status {
            case .preparing:
                ProgressView()
                    .progressViewStyle(.linear)
                    .tint(.orange)
                HStack {
                    if let stage = state.prepareStageLabel {
                        HStack(spacing: 4) {
                            Image(systemName: "gearshape.2")
                                .font(.caption2)
                                .foregroundColor(.orange)
                            Text(stage)
                                .font(.caption2)
                                .foregroundColor(.orange)
                        }
                    } else {
                        Text("Preparing printer...")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                    Text("\(state.formattedTime) remaining")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            case .paused, .issue:
                ProgressView(value: Double(state.progress), total: 100)
                    .tint(state.accentColor)
                HStack {
                    if let stage = state.prepareStageLabel {
                        HStack(spacing: 4) {
                            Image(systemName: state.iconName)
                                .font(.caption2)
                                .foregroundColor(state.accentColor)
                            Text(stage)
                                .font(.caption2)
                                .foregroundColor(state.accentColor)
                        }
                    } else {
                        Text(state.stateLabel)
                            .font(.caption2)
                            .foregroundColor(state.accentColor)
                    }
                    Spacer()
                    if let layers = state.layerInfo {
                        Text("Layer \(layers)")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                }
                CompactTemperatureView(lines: state.compactTemperatureLines, layout: .horizontal)
            case .completed:
                ProgressView(value: 1.0, total: 1.0)
                    .tint(.green)
                Text("Print complete!")
                    .font(.caption2)
                    .foregroundColor(.green)
            case .cancelled:
                ProgressView(value: Double(state.progress), total: 100)
                    .tint(.red)
                Text("Print cancelled")
                    .font(.caption2)
                    .foregroundColor(.red)
            case .printing, .idle:
                ProgressView(value: Double(state.progress), total: 100)
                    .tint(.blue)
                HStack {
                    if let layers = state.layerInfo {
                        Text("Layer \(layers)")
                            .font(.caption2)
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                    Text("\(state.formattedTime) remaining")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                CompactTemperatureView(lines: state.compactTemperatureLines, layout: .horizontal)
            }
        }
        .padding(.horizontal, 4)
    }
}
