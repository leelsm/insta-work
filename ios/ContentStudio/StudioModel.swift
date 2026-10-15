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
    var thumbnailSceneID: String?
    var thumbnailIndex: Int { scenes.firstIndex { $0.id == thumbnailSceneID } ?? 0 }
    mutating func normalizeThumbnail() {
        if let id = thumbnailSceneID, !scenes.contains(where: { $0.id == id }) { thumbnailSceneID = scenes.first?.id }
    }
    var thumbnailScene: StudioScene? { scenes.indices.contains(thumbnailIndex) ? scenes[thumbnailIndex] : nil }

    mutating func applySceneSubtitle(sceneID: String, text: String) throws {
        let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard isDaily, let index = scenes.firstIndex(where: { $0.id == sceneID }),
              !value.isEmpty, value.count <= 160 else {
            throw StudioError.invalidFile("AI 자막을 검증하지 못했습니다. 기존 자막은 유지됩니다.")
        }
        scenes[index].narration = value
    }

    var duration: Double { scenes.reduce(0) { $0 + $1.duration } }
    var isDaily: Bool { kind == "daily" }
    var canRender: Bool { !scenes.isEmpty && duration <= 180 && duration > 0 }
    var musicCredit: String { musicAssetID.isEmpty ? (MusicLibrary.tracks.first { $0.id == musicID }?.attribution ?? "") : "" }
    var postingCaption: String {
        let text = caption.trimmingCharacters(in: .whitespacesAndNewlines)
        return musicCredit.isEmpty || text.contains(musicCredit) ? text : [text, musicCredit].filter { !$0.isEmpty }.joined(separator: "\n\n")
    }
}

struct StudioMusic: Codable, Identifiable {
    let id: String
    let title: String
    let mood: String
    let filename: String
    let license: String
    let attribution: String
    let reference_url: String
}

enum MusicLibrary {
    private struct Catalog: Decodable {
        let tracks: [StudioMusic]
        let recommendations: [String: [String]]
    }
    private static let catalog: Catalog = {
        guard let url = Bundle.main.url(forResource: "catalog", withExtension: "json", subdirectory: "music"),
              let data = try? Data(contentsOf: url), let result = try? JSONDecoder().decode(Catalog.self, from: data) else {
            return Catalog(tracks: [], recommendations: [:])
        }
        return result
    }()
    static var tracks: [StudioMusic] { catalog.tracks }
    static let moods = ["일상", "여행", "카페", "음식", "운동", "산책", "감성", "정보 전달", "긴장감"]
    static func recommended(_ mood: String) -> [StudioMusic] {
        (catalog.recommendations[mood] ?? catalog.recommendations["일상"] ?? []).compactMap { id in tracks.first { $0.id == id } }
    }
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
