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

// Missing or null fields fall back to defaults so one old/partial record does not
// make the whole projects.json unreadable. Wrong types still throw.
extension StudioScene {
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let d = StudioScene()
        id = try c.decodeIfPresent(String.self, forKey: .id) ?? d.id
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? d.title
        body = try c.decodeIfPresent(String.self, forKey: .body) ?? d.body
        narration = try c.decodeIfPresent(String.self, forKey: .narration) ?? d.narration
        duration = try c.decodeIfPresent(Double.self, forKey: .duration) ?? d.duration
        photoID = try c.decodeIfPresent(String.self, forKey: .photoID) ?? d.photoID
        sourceIDs = try c.decodeIfPresent([Int].self, forKey: .sourceIDs) ?? d.sourceIDs
        imageAuthor = try c.decodeIfPresent(String.self, forKey: .imageAuthor)
        imageLicense = try c.decodeIfPresent(String.self, forKey: .imageLicense)
        imagePageURL = try c.decodeIfPresent(String.self, forKey: .imagePageURL)
        imageLicenseURL = try c.decodeIfPresent(String.self, forKey: .imageLicenseURL)
        imageCredit = try c.decodeIfPresent(String.self, forKey: .imageCredit)
        imageSearchQuery = try c.decodeIfPresent(String.self, forKey: .imageSearchQuery)
        photoFit = try c.decodeIfPresent(String.self, forKey: .photoFit) ?? d.photoFit
        positionX = try c.decodeIfPresent(Double.self, forKey: .positionX) ?? d.positionX
        positionY = try c.decodeIfPresent(Double.self, forKey: .positionY) ?? d.positionY
    }
}

struct StudioSource: Codable, Hashable {
    var title = ""
    var text = ""
    var url = ""
    var rights = ""
}

extension StudioSource {
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        text = try c.decodeIfPresent(String.self, forKey: .text) ?? ""
        url = try c.decodeIfPresent(String.self, forKey: .url) ?? ""
        rights = try c.decodeIfPresent(String.self, forKey: .rights) ?? ""
    }
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

    enum CodingKeys: String, CodingKey { case id, title, kind, scenes, sources, caption, template, brand, subtitleX, subtitleY, subtitleStyle, fontAssetID, fontName, subtitleSize, motion, transition, musicID, musicAssetID, musicName, musicVolume, musicOffset, mood, description, tone, createdAt, updatedAt, lastVideo, renderLayoutVersion, thumbnailSceneID }

    // Length limits shared with the PC version's import validation (Python code points).
    static let titleLimit = 150, captionLimit = 2200, sceneTitleLimit = 90, narrationLimit = 160
    static func limited(_ text: String, _ limit: Int) -> String {
        var scalars = 0
        var result = ""
        for character in text {
            scalars += character.unicodeScalars.count
            if scalars > limit { break }
            result.append(character)
        }
        return result
    }
    var defaultTitle: String { isDaily ? "나의 일상 영상" : "새 카드 영상" }
    /// Clamps text to the PC version's limits and replaces a blank title.
    mutating func normalizeText() {
        let trimmed = Self.limited(title, Self.titleLimit).trimmingCharacters(in: .whitespacesAndNewlines)
        title = trimmed.isEmpty ? defaultTitle : trimmed
        caption = Self.limited(caption, Self.captionLimit)
        for index in scenes.indices {
            scenes[index].title = Self.limited(scenes[index].title, Self.sceneTitleLimit)
            scenes[index].narration = Self.limited(scenes[index].narration, Self.narrationLimit)
        }
    }

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

extension StudioProject {
    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let d = StudioProject()
        id = try c.decodeIfPresent(String.self, forKey: .id) ?? d.id
        title = try c.decodeIfPresent(String.self, forKey: .title) ?? d.title
        kind = try c.decodeIfPresent(String.self, forKey: .kind) ?? d.kind
        scenes = try c.decodeIfPresent([StudioScene].self, forKey: .scenes) ?? d.scenes
        sources = try c.decodeIfPresent([StudioSource].self, forKey: .sources) ?? d.sources
        caption = try c.decodeIfPresent(String.self, forKey: .caption) ?? d.caption
        template = try c.decodeIfPresent(String.self, forKey: .template) ?? d.template
        brand = try c.decodeIfPresent(String.self, forKey: .brand) ?? d.brand
        subtitleX = try c.decodeIfPresent(Double.self, forKey: .subtitleX) ?? d.subtitleX
        subtitleY = try c.decodeIfPresent(Double.self, forKey: .subtitleY) ?? d.subtitleY
        subtitleStyle = try c.decodeIfPresent(String.self, forKey: .subtitleStyle) ?? d.subtitleStyle
        fontAssetID = try c.decodeIfPresent(String.self, forKey: .fontAssetID) ?? d.fontAssetID
        fontName = try c.decodeIfPresent(String.self, forKey: .fontName) ?? d.fontName
        subtitleSize = try c.decodeIfPresent(Double.self, forKey: .subtitleSize)
        motion = try c.decodeIfPresent(String.self, forKey: .motion)
        transition = try c.decodeIfPresent(String.self, forKey: .transition)
        musicID = try c.decodeIfPresent(String.self, forKey: .musicID) ?? d.musicID
        musicAssetID = try c.decodeIfPresent(String.self, forKey: .musicAssetID) ?? d.musicAssetID
        musicName = try c.decodeIfPresent(String.self, forKey: .musicName) ?? d.musicName
        musicVolume = try c.decodeIfPresent(Double.self, forKey: .musicVolume) ?? d.musicVolume
        musicOffset = try c.decodeIfPresent(Double.self, forKey: .musicOffset)
        mood = try c.decodeIfPresent(String.self, forKey: .mood)
        description = try c.decodeIfPresent(String.self, forKey: .description)
        tone = try c.decodeIfPresent(String.self, forKey: .tone)
        createdAt = try c.decodeIfPresent(Date.self, forKey: .createdAt) ?? d.createdAt
        updatedAt = try c.decodeIfPresent(Date.self, forKey: .updatedAt) ?? d.updatedAt
        lastVideo = try c.decodeIfPresent(String.self, forKey: .lastVideo) ?? d.lastVideo
        renderLayoutVersion = try c.decodeIfPresent(Int.self, forKey: .renderLayoutVersion)
        thumbnailSceneID = try c.decodeIfPresent(String.self, forKey: .thumbnailSceneID)
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
