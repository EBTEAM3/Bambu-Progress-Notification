import ActivityKit
import SwiftUI
import WidgetKit

struct PrinterActivityLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: PrinterAttributes.self) { context in
            // Lock Screen / Banner presentation
            LockScreenView(state: context.state, attributes: context.attributes)
        } dynamicIsland: { context in
            DynamicIsland {
                // Expanded presentation
                DynamicIslandExpandedRegion(.leading) {
                    HStack(spacing: 6) {
                        Image(systemName: iconName(for: context.state))
                            .foregroundColor(stateAccentColor(for: context.state))
                        Text(context.state.displayTitle)
                            .font(.caption)
                            .lineLimit(1)
                    }
                }

                DynamicIslandExpandedRegion(.trailing) {
                    Text(trailingText(for: context.state))
                        .font(.title2)
                        .fontWeight(.bold)
                        .foregroundColor(stateAccentColor(for: context.state))
                }

                DynamicIslandExpandedRegion(.bottom) {
                    expandedBottom(state: context.state)
                }
            } compactLeading: {
                Image(systemName: iconName(for: context.state))
                    .foregroundColor(stateAccentColor(for: context.state))
            } compactTrailing: {
                Text(compactTrailingText(for: context.state))
                    .font(.caption2)
                    .fontWeight(.bold)
                    .foregroundColor(stateAccentColor(for: context.state))
            } minimal: {
                minimalView(state: context.state)
            }
        }
    }
}

// MARK: - Lock Screen View

private struct LockScreenView: View {
    let state: PrinterAttributes.ContentState
    let attributes: PrinterAttributes

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Top row: icon + job name + state badge
            HStack {
                Image(systemName: iconName(for: state))
                    .foregroundColor(stateAccentColor(for: state))
                Text(state.displayTitle)
                    .font(.headline)
                    .lineLimit(1)
                Spacer()
                Text(state.stateLabel)
                    .font(.caption)
                    .fontWeight(.medium)
                    .foregroundColor(stateAccentColor(for: state))
                    .padding(.horizontal, 8)
                    .padding(.vertical, 2)
                    .background(stateAccentColor(for: state).opacity(0.2))
                    .clipShape(Capsule())
            }

            // Progress bar
            if state.isStarting {
                ProgressView()
                    .progressViewStyle(.linear)
                    .tint(.blue)
            } else {
                ProgressView(value: Double(state.progress), total: 100)
                    .tint(stateAccentColor(for: state))
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
                    Text("Preparing printer...")
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
                        .foregroundColor(stateAccentColor(for: state))
                }
            }
        }
        .padding()
        .activityBackgroundTint(Color.black.opacity(0.6))
    }
}

// MARK: - Dynamic Island Expanded Bottom

@ViewBuilder
private func expandedBottom(state: PrinterAttributes.ContentState) -> some View {
    VStack(spacing: 6) {
        if state.isStarting {
            ProgressView()
                .progressViewStyle(.linear)
                .tint(.blue)
            Text("Preparing printer...")
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
}

// MARK: - Dynamic Island Minimal

@ViewBuilder
private func minimalView(state: PrinterAttributes.ContentState) -> some View {
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
            .font(.caption2)
            .fontWeight(.bold)
    }
}

// MARK: - Helpers

private func iconName(for state: PrinterAttributes.ContentState) -> String {
    switch state.state {
    case "completed": return "checkmark.circle.fill"
    case "cancelled": return "xmark.circle.fill"
    default: return "printer.fill"
    }
}

private func stateAccentColor(for state: PrinterAttributes.ContentState) -> Color {
    switch state.state {
    case "completed": return .green
    case "cancelled": return .red
    case "starting": return .orange
    default: return .blue
    }
}

private func trailingText(for state: PrinterAttributes.ContentState) -> String {
    switch state.state {
    case "completed": return "Done"
    case "cancelled": return "Stop"
    case "starting": return "..."
    default: return "\(state.progress)%"
    }
}

private func compactTrailingText(for state: PrinterAttributes.ContentState) -> String {
    switch state.state {
    case "completed": return "Done"
    case "cancelled": return "Stop"
    case "starting": return "..."
    default: return "\(state.progress)%"
    }
}

// MARK: - Previews

#Preview("Lock Screen — Printing", as: .content, using: PrinterAttributes.preview) {
    PrinterActivityLiveActivity()
} contentStates: {
    PrinterAttributes.ContentState.mockPrinting
}

#Preview("Lock Screen — Starting", as: .content, using: PrinterAttributes.preview) {
    PrinterActivityLiveActivity()
} contentStates: {
    PrinterAttributes.ContentState.mockStarting
}

#Preview("Lock Screen — Completed", as: .content, using: PrinterAttributes.preview) {
    PrinterActivityLiveActivity()
} contentStates: {
    PrinterAttributes.ContentState.mockCompleted
}

#Preview("Dynamic Island Compact", as: .dynamicIsland(.compact), using: PrinterAttributes.preview) {
    PrinterActivityLiveActivity()
} contentStates: {
    PrinterAttributes.ContentState.mockPrinting
}

#Preview("Dynamic Island Minimal", as: .dynamicIsland(.minimal), using: PrinterAttributes.preview) {
    PrinterActivityLiveActivity()
} contentStates: {
    PrinterAttributes.ContentState.mockPrinting
}

#Preview("Dynamic Island Expanded", as: .dynamicIsland(.expanded), using: PrinterAttributes.preview) {
    PrinterActivityLiveActivity()
} contentStates: {
    PrinterAttributes.ContentState.mockPrinting
}
