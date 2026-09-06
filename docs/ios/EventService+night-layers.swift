// Paste into Features/NYCInFocus after the native map-feed decode.
// Tonight aux chips already exist on SecondaryChipBar. Replace
// `overlayMessage = "Coming next: …"` with NightLayerService.fetch.
// Use the publishable key only. Never service_role.

import Foundation
import CoreLocation

struct NativeNightLayer: Decodable, Identifiable {
    let id: String
    let label: String
    let chipLabel: String
    let emoji: String
    let layer: String
    let url: URL
    let featureCount: Int?

    enum CodingKeys: String, CodingKey {
        case id, label, emoji, layer, url
        case chipLabel = "chip_label"
        case featureCount = "feature_count"
    }
}

struct NativeChipRows: Decodable {
    let night: [NativeNightLayer]
}

struct NightLayerFeatureCollection: Decodable {
    let features: [NightLayerFeature]
}

struct NightLayerFeature: Decodable, Identifiable {
    var id: String { title + String(latitude) + String(longitude) }
    let title: String
    let latitude: Double
    let longitude: Double

    enum CodingKeys: String, CodingKey {
        case properties, geometry
    }

    enum PropertiesKeys: String, CodingKey {
        case title, name
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let props = try container.nestedContainer(keyedBy: PropertiesKeys.self, forKey: .properties)
        title = try props.decodeIfPresent(String.self, forKey: .title)
            ?? props.decodeIfPresent(String.self, forKey: .name)
            ?? "Location"
        let geometry = try container.decode(NightLayerPoint.self, forKey: .geometry)
        longitude = geometry.coordinates[0]
        latitude = geometry.coordinates[1]
    }
}

private struct NightLayerPoint: Decodable {
    let coordinates: [Double]
}

enum NightLayerService {
    static func fetch(_ layer: NativeNightLayer) async throws -> [NightLayerFeature] {
        let request = EventService.authorizedRequest(url: layer.url)
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw EventServiceError.invalidResponse
        }
        return try JSONDecoder().decode(NightLayerFeatureCollection.self, from: data).features
    }
}
