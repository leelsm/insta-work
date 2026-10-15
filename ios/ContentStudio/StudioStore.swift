import Foundation
import UIKit
import ImageIO

struct BundledStudioFont: Decodable, Identifiable {
    let id: String
    let name: String
    let note: String
    let filename: String
}

@MainActor final class StudioStore: ObservableObject {
    @Published private(set) var projects: [StudioProject] = []

    let root: URL
    let assets: URL
    let exports: URL
    private let index: URL

    init(root: URL? = nil) {
        let base = root ?? FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("ContentStudio", isDirectory: true)
        self.root = base
        self.assets = base.appendingPathComponent("assets", isDirectory: true)
        self.exports = base.appendingPathComponent("exports", isDirectory: true)
        self.index = base.appendingPathComponent("projects.json")
        try? FileManager.default.createDirectory(at: assets, withIntermediateDirectories: true)
        try? FileManager.default.createDirectory(at: exports, withIntermediateDirectories: true)
        load()
        if loadIssue == nil { sweepOrphans() }
    }

    /// Set when projects.json could not be fully read. Projects that failed to decode
    /// are kept in a projects.corrupt-<timestamp>.json copy.
    @Published private(set) var loadIssue: String?
    /// True when the original index could not be read or backed up; saving would
    /// overwrite projects that are still on disk, so persist() is disabled.
    private(set) var persistBlocked = false

    private struct LossyProject: Decodable {
        let value: StudioProject?
        init(from decoder: Decoder) throws { value = try? StudioProject(from: decoder) }
    }

    private func load() {
        guard FileManager.default.fileExists(atPath: index.path) else { return }
        let data: Data
        do { data = try Data(contentsOf: index) } catch {
            persistBlocked = true
            loadIssue = "프로젝트 목록을 읽지 못했습니다. 기존 파일을 보호하기 위해 변경 내용을 저장하지 않아요. 앱을 다시 실행해 주세요."
            return
        }
        guard let rows = try? JSONDecoder().decode([LossyProject].self, from: data) else {
            persistBlocked = !backupIndex(data)
            loadIssue = persistBlocked ? "프로젝트 목록이 손상되어 읽지 못했습니다. 기존 파일을 보호하기 위해 변경 내용을 저장하지 않아요." :
                "프로젝트 목록이 손상되어 읽지 못했습니다. 원본은 projects.corrupt 파일로 보관했어요."
            return
        }
        projects = rows.compactMap(\.value)
        let failed = rows.count - projects.count
        if failed > 0 {
            persistBlocked = !backupIndex(data)
            loadIssue = persistBlocked ? "프로젝트 \(failed)개를 읽지 못했습니다. 기존 파일을 보호하기 위해 변경 내용을 저장하지 않아요." :
                "프로젝트 \(failed)개를 읽지 못했습니다. 원본은 projects.corrupt 파일로 보관했어요."
        }
    }

    private func backupIndex(_ data: Data) -> Bool {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX"); formatter.dateFormat = "yyyyMMdd-HHmmss"
        let backup = root.appendingPathComponent("projects.corrupt-\(formatter.string(from: Date())).json")
        return (try? data.write(to: backup, options: .withoutOverwriting)) != nil
            || FileManager.default.contentsEqual(atPath: backup.path, andPath: index.path)
    }

    /// File names (assets and exports) still used by saved projects.
    private func referencedFiles(excluding id: String? = nil) -> Set<String> {
        var names = Set<String>()
        for project in projects where project.id != id {
            names.formUnion(project.scenes.map(\.photoID))
            names.insert(project.musicAssetID); names.insert(project.fontAssetID)
            if !project.lastVideo.isEmpty {
                names.insert(project.lastVideo)
                names.insert(VideoRenderer.thumbnailURL(for: exports.appendingPathComponent(project.lastVideo)).lastPathComponent)
            }
        }
        names.remove("")
        return names
    }

    private func removeFiles(_ names: Set<String>, in folder: URL) {
        for name in names where !name.isEmpty && !name.contains("/") && !name.contains("\\") {
            try? FileManager.default.removeItem(at: folder.appendingPathComponent(name))
        }
    }

    private func removeVideo(_ name: String) {
        guard !name.isEmpty, !referencedFiles().contains(name) else { return }
        let video = exports.appendingPathComponent(name)
        removeFiles([name, VideoRenderer.thumbnailURL(for: video).lastPathComponent], in: exports)
    }

    /// Removes assets/exports that no saved project references. Files changed in the
    /// last hour are kept so photos of a draft that is still being created survive.
    private func sweepOrphans() {
        let used = referencedFiles()
        let cutoff = Date().addingTimeInterval(-3600)
        for folder in [assets, exports] {
            guard let files = try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: [.contentModificationDateKey]) else { continue }
            for file in files where !used.contains(file.lastPathComponent) {
                let modified = (try? file.resourceValues(forKeys: [.contentModificationDateKey]))?.contentModificationDate ?? .distantFuture
                if modified < cutoff { try? FileManager.default.removeItem(at: file) }
            }
        }
    }

    func draft(kind: String) -> StudioProject {
        var project = StudioProject()
        project.kind = kind
        project.title = kind == "daily" ? "나의 일상 영상" : "새 카드 영상"
        project.subtitleY = kind == "daily" ? 0.76 : 0.79
        if kind == "news" { project.scenes = [StudioScene(title: "첫 번째 카드")] }
        return project
    }

    func create(kind: String) -> StudioProject {
        let project = draft(kind: kind)
        save(project)
        return project
    }

    func save(_ project: StudioProject) {
        var copy = project
        copy.normalizeThumbnail()
        copy.updatedAt = Date()
        var previousVideo = ""
        if let index = projects.firstIndex(where: { $0.id == copy.id }) { previousVideo = projects[index].lastVideo; projects[index] = copy }
        else { projects.insert(copy, at: 0) }
        persist()
        // A re-render or an edit that invalidates the MP4 leaves the old file unreachable.
        if !persistBlocked && previousVideo != copy.lastVideo { removeVideo(previousVideo) }
    }

    func delete(_ project: StudioProject) {
        guard let stored = projects.first(where: { $0.id == project.id }) else { return }
        let others = referencedFiles(excluding: project.id)
        projects.removeAll { $0.id == project.id }
        persist()
        guard !persistBlocked else { return }
        let ownAssets = Set(stored.scenes.map(\.photoID) + project.scenes.map(\.photoID) + [stored.musicAssetID, stored.fontAssetID, project.musicAssetID, project.fontAssetID])
        removeFiles(ownAssets.subtracting(others), in: assets)
        for video in Set([stored.lastVideo, project.lastVideo]) where !video.isEmpty && !others.contains(video) {
            removeFiles([video, VideoRenderer.thumbnailURL(for: exports.appendingPathComponent(video)).lastPathComponent], in: exports)
        }
    }

    private func persist() {
        guard !persistBlocked, let data = try? JSONEncoder().encode(projects) else { return }
        try? data.write(to: index, options: .atomic)
    }

    func assetURL(_ id: String) -> URL? {
        guard !id.isEmpty, !id.contains("/"), !id.contains("\\") else { return nil }
        let url = assets.appendingPathComponent(id)
        return FileManager.default.fileExists(atPath: url.path) ? url : nil
    }

    func image(_ id: String) -> UIImage? {
        guard let url = assetURL(id) else { return nil }
        return UIImage(contentsOfFile: url.path)
    }

    var bundledFonts: [BundledStudioFont] {
        guard let url = Bundle.main.url(forResource: "catalog", withExtension: "json", subdirectory: "fonts"),
              let data = try? Data(contentsOf: url),
              let fonts = try? JSONDecoder().decode([BundledStudioFont].self, from: data) else { return [] }
        return fonts
    }

    func importBundledFont(_ font: BundledStudioFont) throws -> String {
        guard let source = Bundle.main.resourceURL?.appendingPathComponent("fonts/" + font.filename),
              FileManager.default.fileExists(atPath: source.path) else {
            throw StudioError.invalidFile("기본 제공 폰트를 찾지 못했습니다.")
        }
        let name = font.id + "." + source.pathExtension
        let target = assets.appendingPathComponent(name)
        if !FileManager.default.fileExists(atPath: target.path) {
            try FileManager.default.copyItem(at: source, to: target)
        }
        return name
    }

    func importPhoto(_ data: Data) throws -> String {
        try registerPhoto(Self.preparePhoto(data))
    }

    /// Saves an already prepared JPEG (see preparePhoto) as a new asset.
    func registerPhoto(_ jpeg: Data) throws -> String {
        let name = UUID().uuidString + ".jpg"
        try jpeg.write(to: assets.appendingPathComponent(name), options: .atomic)
        return name
    }

    /// Downscales and JPEG-encodes a picked photo. Safe to call off the main actor.
    nonisolated static func preparePhoto(_ data: Data) throws -> Data {
        // Decode a thumbnail directly rather than loading a 48 MP original into memory.
        let sourceOptions = [kCGImageSourceShouldCache: false] as CFDictionary
        let options = [kCGImageSourceCreateThumbnailFromImageAlways: true,
                       kCGImageSourceCreateThumbnailWithTransform: true,
                       kCGImageSourceThumbnailMaxPixelSize: 1920,
                       kCGImageSourceShouldCacheImmediately: true] as CFDictionary
        guard let source = CGImageSourceCreateWithData(data as CFData, sourceOptions),
              let thumbnail = CGImageSourceCreateThumbnailAtIndex(source, 0, options),
              let jpeg = UIImage(cgImage: thumbnail).jpegData(compressionQuality: 0.82) else {
            throw StudioError.invalidFile("사진을 읽을 수 없습니다. 다른 사진을 선택해주세요.")
        }
        return jpeg
    }

    func importFile(_ source: URL, allowed: Set<String>, maxBytes: Int) throws -> String {
        let access = source.startAccessingSecurityScopedResource()
        defer { if access { source.stopAccessingSecurityScopedResource() } }
        let ext = source.pathExtension.lowercased()
        guard allowed.contains(ext) else { throw StudioError.invalidFile("지원하지 않는 파일 형식입니다.") }
        let data = try Data(contentsOf: source)
        guard data.count <= maxBytes else { throw StudioError.invalidFile("파일 크기 제한을 넘었습니다.") }
        let name = UUID().uuidString + "." + ext
        try data.write(to: assets.appendingPathComponent(name), options: .atomic)
        return name
    }

    func exportTransfer(_ project: StudioProject) throws -> URL {
        guard !project.scenes.isEmpty,
              project.sources.allSatisfy({ !$0.title.trimmingCharacters(in: .whitespaces).isEmpty &&
                                             !$0.text.trimmingCharacters(in: .whitespaces).isEmpty }) else {
            throw StudioError.invalidFile("장면과 근거 자료의 제목·본문을 확인하세요.")
        }
        let ids = Set(project.scenes.map(\.photoID) + [project.musicAssetID, project.fontAssetID])
        var encoded: [String: String] = [:]
        for id in ids where !id.isEmpty {
            guard let url = assetURL(id), let data = try? Data(contentsOf: url) else { throw StudioError.invalidFile("프로젝트의 첨부 파일이 없습니다: \(id)") }
            encoded[id] = data.base64EncodedString()
        }
        var normalized = project; normalized.normalizeThumbnail(); normalized.normalizeText()
        let transfer = TransferFile(project: normalized, assets: encoded)
        let url = exports.appendingPathComponent(Self.transferFileName(normalized.title) + "-" + project.id.prefix(8) + ".studio")
        // Only the latest .studio file is offered for sharing; drop earlier ones.
        if let old = try? FileManager.default.contentsOfDirectory(at: exports, includingPropertiesForKeys: nil) {
            for file in old where file.pathExtension == "studio" && file != url { try? FileManager.default.removeItem(at: file) }
        }
        do { try JSONEncoder().encode(transfer).write(to: url, options: .atomic) }
        catch { throw StudioError.invalidFile("프로젝트 파일을 만들지 못했습니다. 저장 공간을 확인한 뒤 다시 시도해 주세요.") }
        return url
    }

    /// The first 40 characters of the title with characters that are unsafe in file names replaced.
    nonisolated static func transferFileName(_ title: String) -> String {
        let unsafe = Set("/:\\?%*|\"<>")
        let name = String(title.prefix(40).map { unsafe.contains($0) || $0.isNewline || $0.unicodeScalars.contains { $0.properties.generalCategory == .control } ? "-" : $0 })
            .trimmingCharacters(in: .whitespaces)
        return name.isEmpty || name.allSatisfy({ $0 == "." }) ? "project" : name
    }

    func importTransfer(_ source: URL) throws -> StudioProject {
        let access = source.startAccessingSecurityScopedResource()
        defer { if access { source.stopAccessingSecurityScopedResource() } }
        let data = try Data(contentsOf: source)
        guard data.count <= 250_000_000 else { throw StudioError.invalidFile("프로젝트 파일은 250MB 이하여야 합니다.") }
        let transfer = try JSONDecoder().decode(TransferFile.self, from: data)
        guard transfer.format == "content-studio-transfer", transfer.version == 1 else {
            throw StudioError.invalidFile("지원하지 않는 프로젝트 파일입니다.")
        }
        var project = transfer.project
        guard project.isDaily else { throw StudioError.invalidFile("카드뉴스는 PC 버전 Content Studio에서 편집해주세요. iPhone에서는 일상 영상 프로젝트를 가져올 수 있어요.") }
        guard (1...10).contains(project.scenes.count), project.duration <= 180,
              project.scenes.allSatisfy({ !$0.photoID.isEmpty && (2...30).contains($0.duration) &&
                  ["cover", "contain"].contains($0.photoFit) && (0...1).contains($0.positionX) && (0...1).contains($0.positionY) }),
              (24...96).contains(project.effectiveSubtitleSize),
              ["still", "zoom", "zoom-out", "pan-left", "pan-right"].contains(project.effectiveMotion),
              ["cut", "fade"].contains(project.effectiveTransition), (0...1).contains(project.musicVolume),
              (0...30).contains(project.effectiveMusicOffset) else {
            throw StudioError.invalidFile("사진·장면 길이·영상 설정을 확인해주세요. 사진은 1~10장, 영상은 180초까지 가져올 수 있어요.")
        }
        var replacements: [String: String] = [:]
        for (name, base64) in transfer.assets {
            let ext = URL(fileURLWithPath: name).pathExtension.lowercased()
            guard !name.contains("/"), !name.contains("\\"), ["jpg", "jpeg", "png", "mp3", "m4a", "wav", "ttf", "otf"].contains(ext),
                  let bytes = Data(base64Encoded: base64), bytes.count <= 25_000_000 else {
                throw StudioError.invalidFile("프로젝트 첨부 파일이 올바르지 않습니다.")
            }
            let newName = UUID().uuidString + "." + ext
            try bytes.write(to: assets.appendingPathComponent(newName), options: .atomic)
            replacements[name] = newName
        }
        for scene in project.scenes { if !scene.photoID.isEmpty && replacements[scene.photoID] == nil { throw StudioError.invalidFile("사진 파일이 빠졌습니다.") } }
        project.scenes = project.scenes.map { scene in
            var updated = scene
            updated.photoID = replacements[scene.photoID] ?? scene.photoID
            return updated
        }
        if !project.musicAssetID.isEmpty { guard let id = replacements[project.musicAssetID] else { throw StudioError.invalidFile("음악 파일이 빠졌습니다.") }; project.musicAssetID = id }
        if !project.fontAssetID.isEmpty { guard let id = replacements[project.fontAssetID] else { throw StudioError.invalidFile("폰트 파일이 빠졌습니다.") }; project.fontAssetID = id }
        project.id = UUID().uuidString
        project.lastVideo = ""
        save(project)
        return project
    }
}
