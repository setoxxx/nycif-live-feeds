// NYCInFocus HomeView patches. This repo cannot open that PR.
// Apply on setoxxx/NYCInFocus Features/NYCInFocus/Features/Home/HomeView.swift

// 1) Tonight must call mode=tonight, not mode=now.
//    Current main (SHA 966c651) has:
//      EventService.fetchMapEvents(mode: mode == .tonight ? .now : mode)
//    Replace with:
            let result = try await EventService.fetchMapEvents(
                mode: mode
            )

// 2) Tonight aux chips must load night-layer pins through the native feed.
//    Current main only sets overlayMessage = "Coming next: …"
//    Replace onTonightAux and add loadLayer:

                        onTonightAux: { chip in
                            Task { await loadNightLayer(chip) }
                        }

    @MainActor
    private func loadNightLayer(_ chip: SecondaryChip) async {
        let layer: String
        switch chip {
        case .fivePM: layer = "5pm"
        case .dispensaries: layer = "dispensary"
        case .liquor: layer = "liquor"
        }
        isLoadingEvents = true
        eventLoadError = nil
        do {
            // Must be mode=layer&layer=dispensary|liquor|5pm (not date=).
            let result = try await EventService.fetchNightLayer(layer)
            events = result.events
        } catch {
            eventLoadError = error.localizedDescription
        }
        isLoadingEvents = false
    }

// Preferred EventService addition (do not use service_role):
//
// static func fetchNightLayer(_ layer: String) async throws -> EventLoadResult {
//     var components = URLComponents(url: SupabaseService.nativeMapFeedURL, resolvingAgainstBaseURL: false)!
//     components.queryItems = [
//         URLQueryItem(name: "mode", value: "layer"),
//         URLQueryItem(name: "layer", value: layer),
//     ]
//     let request = authorizedRequest(url: components.url!)
//     ...
// }
