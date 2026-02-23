import SwiftUI
import WidgetKit

struct MinimalView: View {
    let state: PrinterAttributes.ContentState

    var body: some View {
        if state.isCompleted {
            Image(systemName: "checkmark.circle.fill")
                .foregroundColor(.green)
        } else if state.isCancelled {
            Image(systemName: "xmark.circle.fill")
                .foregroundColor(.red)
        } else if state.isStarting {
            ProgressView()
                .progressViewStyle(.circular)
        } else {
            Text("\(state.progress)%")
                .font(.caption)
                .fontWeight(.bold)
                .monospacedDigit()
        }
    }
}
