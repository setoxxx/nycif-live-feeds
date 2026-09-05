// Paste into Features/NYCInFocus/Services/EventService.swift
// Add the two header lines and corridor fields. Do not point at GitHub JSON.

import Foundation
import CoreLocation

extension EventService {
    static let supabaseAnonKey = "REPLACE_WITH_SUPABASE_ANON_KEY"

    static func authorizedRequest(url: URL) -> URLRequest {
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue(supabaseAnonKey, forHTTPHeaderField: "apikey")
        request.setValue("Bearer \(supabaseAnonKey)", forHTTPHeaderField: "Authorization")
        return request
    }
}

struct NativeCorridorPoint: Decodable {
    let lat: Double?
    let lng: Double?
}

struct NativeCorridor: Decodable {
    let mainStreet: String?
    let fromStreet: String?
    let toStreet: String?
    let borough: String?
    let pointA: NativeCorridorPoint?
    let pointB: NativeCorridorPoint?
    let line: [[Double]]?

    enum CodingKeys: String, CodingKey {
        case mainStreet = "main_street"
        case fromStreet = "from_street"
        case toStreet = "to_street"
        case borough
        case pointA = "point_a"
        case pointB = "point_b"
        case line
    }
}

extension NativeMapEventRow {
    var canPlotPoint: Bool {
        mapped
            && certifiedPin
            && mapEligibilityState == "MAP_READY"
            && latitude.map { $0.isFinite } == true
            && longitude.map { $0.isFinite } == true
    }
}

func shouldPlotPoint(_ row: NativeMapEventRow) -> Bool {
    row.canPlotPoint
}
