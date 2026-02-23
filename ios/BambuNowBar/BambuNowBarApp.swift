import FirebaseCore
import SwiftUI

@main
struct BambuNowBarApp: App {
    init() {
        FirebaseApp.configure()
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
