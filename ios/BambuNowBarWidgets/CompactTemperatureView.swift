import SwiftUI
import WidgetKit

/// Displays abbreviated temperatures as **N** 150/220°C · **B** 45/60°C · **C** 28°C
/// Supports vertical (stacked) and horizontal (inline) layouts.
struct CompactTemperatureView: View {
    let lines: [PrinterAttributes.ContentState.TempLine]
    var layout: Layout = .vertical

    enum Layout {
        case vertical
        case horizontal
    }

    var body: some View {
        switch layout {
        case .vertical:
            VStack(alignment: .trailing, spacing: 1) {
                ForEach(lines) { line in
                    tempEntry(line)
                }
            }
        case .horizontal:
            HStack(spacing: 8) {
                ForEach(lines) { line in
                    tempEntry(line)
                }
            }
        }
    }

    private func tempEntry(_ line: PrinterAttributes.ContentState.TempLine) -> some View {
        HStack(spacing: 2) {
            Text(line.label)
                .fontWeight(.bold)
            Text("\(line.text)°C")
        }
        .font(.caption2)
        .monospacedDigit()
        .foregroundColor(.secondary)
    }
}
