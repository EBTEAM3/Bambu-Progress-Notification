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
            if state.isStarting {
                ProgressView()
                    .progressViewStyle(.linear)
                    .tint(.blue)
            } else {
                ProgressView(value: Double(state.progress), total: 100)
                    .tint(state.accentColor)
            }

            // Bottom row: layer info + time remaining + percentage
            HStack {
                if let layers = state.layerInfo, !state.isStarting {
                    Label("Layer \(layers)", systemImage: "square.stack.3d.up")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                Spacer()
                if state.isStarting {
                    Text(state.temperatureInfo ?? "Preparing printer...")
                        .font(.caption)
                        .foregroundColor(.secondary)
                } else if state.isCompleted {
                    Text("Print complete!")
                        .font(.caption)
                        .foregroundColor(.green)
                } else if state.isCancelled {
                    Text("Print cancelled")
                        .font(.caption)
                        .foregroundColor(.red)
                } else {
                    Text("\(state.formattedTime) remaining")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text("\(state.progress)%")
                        .font(.title2)
                        .fontWeight(.bold)
                        .foregroundColor(state.accentColor)
                }
            }
        }
        .padding()
        .activityBackgroundTint(Color.black.opacity(0.6))
    }
}
