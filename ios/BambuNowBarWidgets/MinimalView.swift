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
