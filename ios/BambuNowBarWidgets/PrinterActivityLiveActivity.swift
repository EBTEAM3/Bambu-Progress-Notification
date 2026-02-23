import ActivityKit
import SwiftUI
import WidgetKit

struct PrinterActivityLiveActivity: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: PrinterAttributes.self) { context in
            LockScreenView(state: context.state, attributes: context.attributes)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    HStack {
                        Spacer()

                        Text(context.state.stateLabel)
                            .font(.caption)
                            .fontWeight(.medium)
                            .foregroundColor(context.state.accentColor)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 2)
                            .background(context.state.accentColor.opacity(0.2))
                            .clipShape(Capsule())

                        Spacer()
                    }
                }

                DynamicIslandExpandedRegion(.trailing) {
                    HStack {
                        Spacer()

                        Text(context.state.trailingText)
                            .font(.headline)
                            .fontWeight(.bold)
                            .monospacedDigit()
                            .foregroundColor(context.state.accentColor)

                        Spacer()
                    }
                }

                DynamicIslandExpandedRegion(.bottom) {
                    ExpandedBottomView(state: context.state)
                }
            } compactLeading: {
                if context.state.isCompleted || context.state.isCancelled {
                    Image(systemName: context.state.iconName)
                        .font(.body)
                        .foregroundColor(context.state.accentColor)
                } else {
                    Text(context.state.compactLeadingTemp)
                        .font(.caption)
                        .fontWeight(.bold)
                        .monospacedDigit()
                        .foregroundColor(context.state.accentColor)
                }
            } compactTrailing: {
                Text(context.state.trailingText)
                    .font(.caption)
                    .fontWeight(.bold)
                    .monospacedDigit()
                    .foregroundColor(context.state.accentColor)
            } minimal: {
                MinimalView(state: context.state)
            }
        }
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

#Preview("Dynamic Island Compact — Printing", as: .dynamicIsland(.compact), using: PrinterAttributes.preview) {
    PrinterActivityLiveActivity()
} contentStates: {
    PrinterAttributes.ContentState.mockPrinting
}

#Preview("Dynamic Island Compact — Cancelled", as: .dynamicIsland(.compact), using: PrinterAttributes.preview) {
    PrinterActivityLiveActivity()
} contentStates: {
    PrinterAttributes.ContentState.mockCancelled
}

#Preview("Dynamic Island Minimal", as: .dynamicIsland(.minimal), using: PrinterAttributes.preview) {
    PrinterActivityLiveActivity()
} contentStates: {
    PrinterAttributes.ContentState.mockPrinting
}

#Preview("Dynamic Island Expanded Printing", as: .dynamicIsland(.expanded), using: PrinterAttributes.preview) {
    PrinterActivityLiveActivity()
} contentStates: {
    PrinterAttributes.ContentState.mockPrinting
}

#Preview("Dynamic Island Expanded Starting", as: .dynamicIsland(.expanded), using: PrinterAttributes.preview) {
    PrinterActivityLiveActivity()
} contentStates: {
    PrinterAttributes.ContentState.mockStarting
}
