import SwiftUI
import WidgetKit

struct MinimalView: View {
    let state: PrinterAttributes.ContentState

    var body: some View {
        switch state.status {
        case .completed:
            Image(systemName: "checkmark.circle.fill")
                .foregroundColor(.green)
        case .cancelled:
            Image(systemName: "xmark.circle.fill")
                .foregroundColor(.red)
        case .paused:
            Image(systemName: "pause.circle.fill")
                .foregroundColor(.yellow)
        case .issue:
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundColor(.red)
        case .preparing:
            ProgressView()
                .progressViewStyle(.circular)
        case .printing, .idle:
            Text("\(state.progress)%")
                .font(.caption)
                .fontWeight(.bold)
                .monospacedDigit()
        }
    }
}
