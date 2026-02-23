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
                    HStack(spacing: 6) {
                        Image(systemName: context.state.iconName)
                            .foregroundColor(context.state.accentColor)
                            .padding(.leading, 2)
                            .padding(.top, 2)
                        Text(context.state.displayTitle)
                            .font(.headline)
                            .lineLimit(1)
                    }
                }

                DynamicIslandExpandedRegion(.trailing) {
                    Text(context.state.trailingText)
                        .font(.title3)
                        .fontWeight(.bold)
                        .monospacedDigit()
                        .foregroundColor(context.state.accentColor)
                        .padding(.trailing, 2)
                }

                DynamicIslandExpandedRegion(.bottom) {
                    ExpandedBottomView(state: context.state)
                        .padding(.horizontal, 2)
                }
            } compactLeading: {
                Image(systemName: context.state.iconName)
                    .font(.body)
                    .foregroundColor(context.state.accentColor)
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
