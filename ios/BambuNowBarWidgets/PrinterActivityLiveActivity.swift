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
                            .lineLimit(1)

                        Spacer()
                    }
                }

                DynamicIslandExpandedRegion(.trailing) {
                    ExpandedTrailingView(state: context.state)
                }

                DynamicIslandExpandedRegion(.bottom) {
                    ExpandedBottomView(state: context.state)
                        .padding(.bottom, 8)
                }
            } compactLeading: {
                CompactLeadingView(state: context.state)
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

#Preview(
    "Dynamic Island",
    as: .dynamicIsland(.expanded),
    using: PrinterAttributes.preview
) {
    PrinterActivityLiveActivity()
} contentStates: {
    PrinterAttributes.ContentState.mockPrinting
}
