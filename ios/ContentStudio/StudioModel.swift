import Foundation

struct StudioScene: Codable, Identifiable, Hashable {
    var id = UUID().uuidString
    var title = "새 장면"
    var body = ""
    var narration = ""
    var duration = 4.0
    var photoID = ""
    var sourceIDs: [Int] = []
    var imageAuthor: String?
    var imageLicense: String?
    var imagePageURL: String?
    var imageLicenseURL: String?
    var imageCredit: String?
    var imageSearchQuery: String?
    var photoFit = "cover"
    var positionX = 0.5
    var positionY = 0.5

    enum CodingKeys: String, CodingKey { case id, title, body, narration, duration, photoID, sourceIDs, photoFit, positionX, positionY, imageCredit, imageSearchQuery, imageAuthor, imageLicense, imagePageURL, imageLicenseURL }

    init() {}
    init(title: String, photoID: String = "") { self.title = title; self.photoID = photoID }
}

struct StudioSource: Codable, Hashable {
    var title = ""
    var text = ""
    var url = ""
    var rights = ""
}

struct StudioProject: Codable, Identifiable, Hashable {
    var id = UUID().uuidString
    var title = "새 영상"
    var kind = "daily" // daily or news
    var scenes: [StudioScene] = []
    var sources: [StudioSource] = []
    var caption = ""
    var template = "ink"
    var brand = "STUDIO"
    var subtitleX = 0.5
    var subtitleY = 0.76
    var subtitleStyle = "box"
    var fontAssetID = ""
    var fontName = ""
    var subtitleSize: Double?
    var motion: String?
    var transition: String?
    var effectiveSubtitleSize: Double { subtitleSize ?? 50 }
    var effectiveMotion: String { motion ?? "zoom" }
    var effectiveTransition: String { transition ?? "fade" }
    var musicID = "slow-morning"
    var musicAssetID = ""
    var musicName = ""
    var musicVolume = 0.35
    var musicOffset: Double?
    var mood: String?
    var description: String?
    var tone: String?
    var effectiveMusicOffset: Double { musicOffset ?? 0 }
    var effectiveMood: String { mood ?? "일상" }
    var effectiveDescription: String { description ?? "" }
    var effectiveTone: String { tone ?? "담백하고 자연스럽게" }
    var createdAt = Date()
    var updatedAt = Date()
    var lastVideo = ""
    var renderLayoutVersion: Int?

    var duration: Double { scenes.reduce(0) { $0 + $1.duration } }
    var isDaily: Bool { kind == "daily" }
    var canRender: Bool { !scenes.isEmpty && duration <= 180 && duration > 0 }
}

struct TransferFile: Codable {
    var format = "content-studio-transfer"
    var version = 1
    var project: StudioProject
    var assets: [String: String] // base64 data keyed by local asset file name
}

enum StudioError: LocalizedError {
    case invalidFile(String)
    case render(String)
    var errorDescription: String? {
        switch self {
        case .invalidFile(let value), .render(let value): return value
        }
    }
}
