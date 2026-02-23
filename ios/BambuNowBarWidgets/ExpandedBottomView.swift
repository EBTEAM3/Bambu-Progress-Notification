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

            // Progress bar
            if state.isStarting {
                ProgressView()
                    .progressViewStyle(.linear)
                    .tint(.orange)
                Text(state.temperatureInfo ?? "Preparing printer...")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            } else if state.isCompleted {
                ProgressView(value: 1.0, total: 1.0)
                    .tint(.green)
                Text("Print complete!")
                    .font(.caption2)
                    .foregroundColor(.green)
            } else if state.isCancelled {
                ProgressView(value: Double(state.progress), total: 100)
                    .tint(.red)
                Text("Print cancelled")
                    .font(.caption2)
                    .foregroundColor(.red)
            } else {
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
            }
        }
        .padding(.horizontal, 4)
    }
}
