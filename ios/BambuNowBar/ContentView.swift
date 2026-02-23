import SwiftUI

struct ContentView: View {
    @State private var tokenManager = TokenManager()
    @State private var showCopied = false

    var body: some View {
        NavigationStack {
            List {
                // Status section
                Section {
                    HStack {
                        Label("Live Activities", systemImage: "circle.fill")
                            .foregroundColor(tokenManager.activitiesEnabled ? .green : .red)
                        Spacer()
                        Text(tokenManager.activitiesEnabled ? "Enabled" : "Disabled")
                            .foregroundColor(.secondary)
                    }

                    HStack {
                        Label("Firestore Sync", systemImage: "circle.fill")
                            .foregroundColor(tokenManager.isSynced ? .green : .orange)
                        Spacer()
                        Text(tokenManager.isSynced ? "Connected" : "Pending")
                            .foregroundColor(.secondary)
                    }
                } header: {
                    Text("Status")
                } footer: {
                    Text(tokenManager.statusMessage)
                }

                // Token section
                if !tokenManager.pushToStartToken.isEmpty {
                    Section {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(tokenManager.pushToStartToken)
                                .font(.system(.caption2, design: .monospaced))
                                .lineLimit(3)
                                .foregroundColor(.secondary)

                            Button {
                                tokenManager.copyPushToStartToken()
                                showCopied = true
                                DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                                    showCopied = false
                                }
                            } label: {
                                Label(
                                    showCopied ? "Copied!" : "Copy Token",
                                    systemImage: showCopied ? "checkmark" : "doc.on.doc"
                                )
                            }
                        }
                    } header: {
                        Text("Push-to-Start Token")
                    } footer: {
                        Text("This token is automatically synced to Firestore. Manual copy is only needed as a fallback.")
                    }
                }

                // Activity token section
                if !tokenManager.activityPushToken.isEmpty {
                    Section {
                        Text(tokenManager.activityPushToken)
                            .font(.system(.caption2, design: .monospaced))
                            .lineLimit(3)
                            .foregroundColor(.secondary)
                    } header: {
                        Text("Activity Push Token")
                    } footer: {
                        Text("Received after a Live Activity is started by the server.")
                    }
                }

                // Instructions section
                Section {
                    VStack(alignment: .leading, spacing: 12) {
                        InstructionRow(step: "1", text: "Set up Firebase and enable Firestore")
                        InstructionRow(step: "2", text: "Configure APNs key on your server")
                        InstructionRow(step: "3", text: "Tokens sync automatically via Firestore")
                        InstructionRow(step: "4", text: "Start a print — Live Activity appears!")
                    }
                    .padding(.vertical, 4)
                } header: {
                    Text("Setup")
                }
            }
            .navigationTitle("Bambu Now Bar")
            .task {
                tokenManager.startObserving()
            }
        }
    }
}

private struct InstructionRow: View {
    let step: String
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Text(step)
                .font(.caption)
                .fontWeight(.bold)
                .foregroundColor(.white)
                .frame(width: 22, height: 22)
                .background(Color.blue)
                .clipShape(Circle())
            Text(text)
                .font(.subheadline)
        }
    }
}

#Preview {
    ContentView()
}
