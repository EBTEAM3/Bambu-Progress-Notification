import SwiftUI
import WidgetKit

/// Expanded Dynamic Island trailing view — temperatures when preparing, percentage/status otherwise.
struct ExpandedTrailingView: View {
    let state: PrinterAttributes.ContentState

    var body: some View {
        switch state.status {
        case .preparing:
            HStack {
                Spacer()
                CompactTemperatureView(lines: state.compactTemperatureLines)
                Spacer()
            }
        case .printing, .idle, .completed, .cancelled, .paused, .issue:
            HStack {
                Spacer()

                Text(state.trailingText)
                    .font(.headline)
                    .fontWeight(.bold)
                    .padding(.vertical, 2)
                    .monospacedDigit()
                    .foregroundColor(state.accentColor)

                Spacer()
            }
        }
    }
}
