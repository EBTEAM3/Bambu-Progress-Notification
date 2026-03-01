import SwiftUI
import WidgetKit

/// Compact Dynamic Island leading view — shows contextual info based on printer status.
struct CompactLeadingView: View {
    let state: PrinterAttributes.ContentState

    var body: some View {
        switch state.status {
        case .completed, .cancelled, .paused, .issue:
            Image(systemName: state.iconName)
                .font(.body)
                .foregroundColor(state.accentColor)
        case .preparing:
            Text(state.compactLeadingTemp)
                .font(.caption)
                .fontWeight(.bold)
                .monospacedDigit()
                .foregroundColor(state.accentColor)
        case .printing, .idle:
            if state.totalLayers > 0 {
                ViewThatFits {
                    Text("\(state.layerNum)/\(state.totalLayers)")
                        .font(.caption)
                        .fontWeight(.bold)
                        .monospacedDigit()
                        .foregroundColor(state.accentColor)
                    VStack(alignment: .trailing, spacing: 0) {
                        Text("\(state.layerNum)/")
                        Text("\(state.totalLayers)")
                    }
                    .font(.caption2)
                    .fontWeight(.bold)
                    .monospacedDigit()
                    .foregroundColor(state.accentColor)
                }
            } else {
                Text(state.compactLeadingTemp)
                    .font(.caption)
                    .fontWeight(.bold)
                    .monospacedDigit()
                    .foregroundColor(state.accentColor)
            }
        }
    }
}
