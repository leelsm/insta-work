import SwiftUI
import AVFoundation
import UIKit

@main struct ContentStudioApp: App {
    #if DEBUG
    @StateObject private var store = StudioStore(root: MobileVerification.previewRoot)
    #else
    @StateObject private var store = StudioStore()
    #endif
    @StateObject private var ai = AISettings()

    var body: some Scene {
        WindowGroup {
            HomeView(store: store, ai: ai)
                .task {
                    #if DEBUG
                    if ProcessInfo.processInfo.arguments.contains("--verify-rendering") { await verifyRendering() }
                    if ProcessInfo.processInfo.arguments.contains("--repair-saved-videos") { await repairSavedVideos() }
                    if ProcessInfo.processInfo.arguments.contains("--verify-store") { await MobileVerification.verifyStore() }
                    #endif
                }
                .tint(.indigo)
        }
    }
    #if DEBUG
    @MainActor private func repairSavedVideos() async {
        var checks: [String: Bool] = [:]; var count = 0
        for original in store.projects.filter({ $0.isDaily && !$0.lastVideo.isEmpty && ($0.renderLayoutVersion ?? 0) < VideoRenderer.layoutVersion }) {
            do {
                let url = try await VideoRenderer.render(original, assets: store.assets, exports: store.exports) { _, _ in }
                let pixels = try await MobileVerification.decodedPhotoChecks(project: original, video: url, assets: store.assets)
                checks.merge(pixels) { _, new in new }
                guard pixels.values.allSatisfy({ $0 }), let latest = store.projects.first(where: { $0.id == original.id }), latest == original else {
                    checks["repair_preserves_current_edits"] = false
                    try? FileManager.default.removeItem(at: url); try? FileManager.default.removeItem(at: VideoRenderer.thumbnailURL(for: url))
                    continue
                }
                var repaired = latest; repaired.lastVideo = url.lastPathComponent; repaired.renderLayoutVersion = VideoRenderer.layoutVersion
                store.save(repaired); count += 1; checks["repair_preserves_current_edits"] = true
            } catch { checks["repair_completed"] = false }
        }
        let receipt: [String: Any] = ["checks": checks, "repaired_count": count]
        if let data = try? JSONSerialization.data(withJSONObject: receipt, options: [.sortedKeys]) {
            try? data.write(to: FileManager.default.temporaryDirectory.appendingPathComponent("repair-video-receipt.json"), options: .atomic)
        }
    }
    @MainActor private func verifyRendering() async {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("render-check-" + UUID().uuidString)
        var checks: [String: Bool] = [:]
        do {
            let temporaryStore = StudioStore(root: root)
            var project = temporaryStore.create(kind: "news")
            project.scenes[0].duration = 0.4
            project.scenes[0].body = "카드 본문 확인"
            project.scenes[0].narration = "자막 확인"
            checks["music_catalog_11_tracks"] = MusicLibrary.tracks.count == 11
            checks["photo_save_usage_description"] = !(Bundle.main.object(forInfoDictionaryKey: "NSPhotoLibraryAddUsageDescription") as? String ?? "").isEmpty
            checks["mood_recommendations"] = MusicLibrary.moods.allSatisfy { (2...3).contains(MusicLibrary.recommended($0).count) }
            for music in MusicLibrary.tracks.map(\.id) {
                project.musicID = music
                let url = try await VideoRenderer.render(project, assets: temporaryStore.assets, exports: temporaryStore.exports) { _, _ in }
                let asset = AVURLAsset(url: url)
                let tracks = try await asset.loadTracks(withMediaType: .audio)
                let duration = try await asset.load(.duration)
                checks[music] = !tracks.isEmpty && duration.seconds > 0.3
            }
            project.musicID = "carefree"; project.caption = "오늘의 기록"
            checks["music_credit_in_caption"] = project.postingCaption.contains("Kevin MacLeod") && project.postingCaption.contains("CC BY 4.0")
            project.musicID = ""
            checks["no_music_no_credit"] = project.postingCaption == project.caption
            temporaryStore.delete(project)
            checks["delete_persisted"] = StudioStore(root: root).projects.isEmpty
            let session = AVAudioSession.sharedInstance()
            try session.setCategory(.playback, mode: .moviePlayback)
            try session.setActive(true)
            checks["playback_session"] = session.category == .playback
            checks.merge(try await MobileVerification.runChecks(root: root)) { _, new in new }
        } catch { checks["completed"] = false }
        try? FileManager.default.removeItem(at: root)
        if let data = try? JSONEncoder().encode(checks) {
            try? data.write(to: FileManager.default.temporaryDirectory.appendingPathComponent("render-check-receipt.json"), options: .atomic)
        }
    }
    #endif
}

#if DEBUG
@MainActor enum MobileVerification {
    static let previewRoot: URL? = {
        if ProcessInfo.processInfo.arguments.contains("--verify-export-ui") {
            return FileManager.default.temporaryDirectory.appendingPathComponent("export-ui-check-" + UUID().uuidString)
        }
        return ProcessInfo.processInfo.arguments.contains(where: { $0.hasPrefix("--preview-daily-") }) ?
            FileManager.default.temporaryDirectory.appendingPathComponent("daily-ui-preview") : nil
    }()
    static func previewProject(store: StudioStore) -> StudioProject? {
        guard previewRoot != nil else { return nil }
        if let project = store.projects.first { return project }
        let fixture = FileManager.default.temporaryDirectory.appendingPathComponent("export-fixture")
        let original = FileManager.default.fileExists(atPath: fixture.appendingPathComponent("projects.json").path) ? StudioStore(root: fixture) : StudioStore()
        if ProcessInfo.processInfo.arguments.contains("--verify-export-ui"), let source = original.projects.first(where: { $0.isDaily && !$0.scenes.isEmpty }) {
            var project = source; project.id = UUID().uuidString; project.title = "저장 화면 검증"; project.lastVideo = ""
            for id in Set(source.scenes.map(\.photoID) + [source.fontAssetID, source.musicAssetID]).filter({ !$0.isEmpty }) {
                try? FileManager.default.copyItem(at: original.assets.appendingPathComponent(id), to: store.assets.appendingPathComponent(id))
            }
            project.scenes = (0..<10).map { index in
                var scene = source.scenes[index % source.scenes.count]; scene.id = UUID().uuidString; scene.duration = 3
                return scene
            }
            project.thumbnailSceneID = project.scenes[7].id
            store.save(project); return project
        }
        var project = StudioProject(); project.title = "느긋한 주말의 기록"; project.mood = "산책"
        project.description = "햇살 아래 산책한 주말"; project.musicID = "after-hours"
        for (index, colors) in [[UIColor.systemOrange, UIColor.systemPink], [UIColor.systemTeal, UIColor.systemBlue], [UIColor.systemPurple, UIColor.systemIndigo]].enumerated() {
            let image = UIGraphicsImageRenderer(size: CGSize(width: 540, height: 960)).image { context in
                let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: colors.map(\.cgColor) as CFArray, locations: [0, 1])!
                context.cgContext.drawLinearGradient(gradient, start: .zero, end: CGPoint(x: 540, y: 960), options: [])
                UIColor.white.withAlphaComponent(0.3).setFill(); UIBezierPath(ovalIn: CGRect(x: 60+index*30, y: 190, width: 320, height: 320)).fill()
                UIColor.white.withAlphaComponent(0.17).setFill(); UIBezierPath(roundedRect: CGRect(x: 100, y: 600, width: 450, height: 400), cornerRadius: 90).fill()
            }
            if let data = image.jpegData(compressionQuality: 0.8), let id = try? store.importPhoto(data) {
                var scene = StudioScene(title: "사진 \(index+1)", photoID: id)
                scene.narration = ["햇살 따라 걷는 느긋한 오후", "오늘은 조금 천천히", "일상의 작은 순간을 모아요"][index]
                project.scenes.append(scene)
            }
        }
        if let font = store.bundledFonts.first(where: { $0.name == "감자꽃" }), let id = try? store.importBundledFont(font) { project.fontAssetID = id; project.fontName = font.name }
        store.save(project); return project
    }
    static func runChecks(root: URL) async throws -> [String: Bool] {
        let store = StudioStore(root: root.appendingPathComponent("daily-check"))
        var checks: [String: Bool] = [:]
        var daily = StudioProject(); daily.title = "일상 기능 검증"; daily.mood = "여행"
        daily.description = "산책한 주말"; daily.tone = "가볍고 유쾌하게"; daily.musicOffset = 7.5
        daily.subtitleSize = 76; daily.motion = "pan-left"; daily.transition = "cut"
        for color in [UIColor.systemOrange, UIColor.systemBlue] {
            let image = UIGraphicsImageRenderer(size: CGSize(width: 2000, height: 1000)).image { _ in
                color.setFill(); UIRectFill(CGRect(x: 0, y: 0, width: 2000, height: 1000))
                UIColor.white.setFill(); UIRectFill(CGRect(x: 920, y: 0, width: 160, height: 1000))
            }
            let id = try store.importPhoto(image.jpegData(compressionQuality: 0.8)!)
            var scene = StudioScene(title: "사진", photoID: id); scene.duration = 2; scene.narration = "오늘의 작은 순간"
            daily.scenes.append(scene)
        }
        if let image = store.image(daily.scenes[0].photoID) { checks["photo_resized"] = max(image.size.width, image.size.height) <= 1920 }
        if let font = store.bundledFonts.first { daily.fontAssetID = try store.importBundledFont(font); daily.fontName = font.name }
        let photo = daily.scenes[0].photoID; daily.scenes.swapAt(0,1); store.save(daily)
        checks["scene_order_persisted"] = StudioStore(root: store.root).projects.first?.scenes[1].photoID == photo
        daily.thumbnailSceneID = daily.scenes[1].id
        let transferred = try store.importTransfer(store.exportTransfer(daily))
        checks["thumbnail_transfer_selection"] = transferred.thumbnailIndex == 1
        checks["daily_transfer_settings"] = transferred.effectiveMood == "여행" && transferred.effectiveDescription == "산책한 주말" && transferred.effectiveTone == "가볍고 유쾌하게" && transferred.effectiveMusicOffset == 7.5 && transferred.effectiveSubtitleSize == 76 && transferred.effectiveMotion == "pan-left" && transferred.effectiveTransition == "cut"
        var legacy = StudioProject(); legacy.kind = "news"; legacy.scenes = [StudioScene(title: "기존 카드")]
        let legacyFile = try store.exportTransfer(legacy)
        let before = store.projects.count
        do { _ = try store.importTransfer(legacyFile); checks["news_import_rejected"] = false }
        catch { checks["news_import_rejected"] = store.projects.count == before }
        for provider in ["openai", "anthropic", "opencode"] {
            let content = try AIService.imageContent(project: daily, assets: store.assets, provider: provider, instruction: "offline verification")
            let images = content.filter { ($0["type"] as? String) == (provider == "anthropic" ? "image" : "image_url") }
            var valid = images.count == daily.scenes.count
            for item in images {
                let base64: String
                if provider == "anthropic" { base64 = (item["source"] as? [String: String])?["data"] ?? "" }
                else { base64 = ((item["image_url"] as? [String: String])?["url"] ?? "").replacingOccurrences(of: "data:image/jpeg;base64,", with: "") }
                if let data = Data(base64Encoded: base64), let image = UIImage(data: data) { valid = valid && max(image.size.width, image.size.height) <= 768 }
                else { valid = false }
            }
            checks["photo_ai_payload_" + provider] = valid
        }
        let selectedID = daily.scenes[1].id
        let selectedProject = try AIService.sceneProject(daily, sceneID: selectedID)
        for provider in ["openai", "anthropic", "opencode"] {
            let chosen = try AIService.imageContent(project: selectedProject, assets: store.assets, provider: provider, instruction: "one scene")
            let expected = try AIService.imageContent(project: { var p = daily; p.scenes = [daily.scenes[1]]; return p }(), assets: store.assets, provider: provider, instruction: "one scene")
            checks["single_scene_payload_" + provider] = NSDictionary(dictionary: ["content": chosen]).isEqual(to: ["content": expected]) && chosen.count == 3
        }
        var edited = daily; edited.scenes.swapAt(0, 1)
        let unchanged = edited
        try edited.applySceneSubtitle(sceneID: selectedID, text: "새로운 장면 자막")
        var expected = unchanged; expected.scenes[0].narration = "새로운 장면 자막"
        checks["single_scene_preserves_other_edits"] = edited == expected
        for invalid in ["", String(repeating: "가", count: 161)] {
            let before = edited
            do { try edited.applySceneSubtitle(sceneID: selectedID, text: invalid); checks["single_scene_invalid_\(invalid.count)"] = false }
            catch { checks["single_scene_invalid_\(invalid.count)"] = edited == before }
        }
        do { try edited.applySceneSubtitle(sceneID: "missing", text: "추천"); checks["single_scene_missing_rejected"] = false }
        catch { checks["single_scene_missing_rejected"] = edited == expected }
        // A cold, scaled preview must contain the source photo, not just captions/background.
        var previewScene = daily.scenes[1]; previewScene.photoID = try store.importPhoto(store.image(previewScene.photoID)!.jpegData(compressionQuality: 0.8)!)
        previewScene.narration = ""; var previewProject = daily; previewProject.motion = "still"
        for fit in ["cover", "contain"] {
            previewScene.photoFit = fit
            let preview = try VideoRenderer.frame(previewProject, scene: previewScene, index: 1, assets: store.assets, outputSize: CGSize(width: 180, height: 320))
            let full = try VideoRenderer.frame(previewProject, scene: previewScene, index: 1, assets: store.assets)
            func sample(_ image: UIImage) -> [UInt8] {
                // Physical devices can use extended-range/P3 renderer buffers. Normalize
                // to 8-bit sRGB before reading pixels so checks also work on device.
                var pixels = [UInt8](repeating: 0, count: 9 * 16 * 4)
                pixels.withUnsafeMutableBytes { bytes in
                    let context = CGContext(data: bytes.baseAddress, width: 9, height: 16,
                        bitsPerComponent: 8, bytesPerRow: 9 * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue)!
                    context.draw(image.cgImage!, in: CGRect(x: 0, y: 0, width: 9, height: 16))
                }
                return pixels
            }
            let smallPixels = sample(preview), fullPixels = sample(full)
            checks["scaled_photo_preview_" + fit] = zip(smallPixels, fullPixels).allSatisfy { abs(Int($0)-Int($1)) < 12 } && smallPixels[(8*9+1)*4..<(8*9+1)*4+3].max()! > 200 && smallPixels[(8*9+1)*4..<(8*9+1)*4+3].min()! < 70
        }
        var missing = daily.scenes[0]; missing.photoID = "missing.jpg"
        do { _ = try VideoRenderer.frame(daily, scene: missing, index: 0, assets: store.assets); checks["missing_preview_photo_reported"] = false }
        catch { checks["missing_preview_photo_reported"] = true }
        for motion in ["still", "zoom", "zoom-out", "pan-left", "pan-right"] {
            daily.motion = motion
            let start = try VideoRenderer.frame(daily, scene: daily.scenes[0], index: 0, assets: store.assets, progress: 0).pngData()
            let end = try VideoRenderer.frame(daily, scene: daily.scenes[0], index: 0, assets: store.assets, progress: 1).pngData()
            checks["motion_" + motion] = motion == "still" ? start == end : start != end
        }
        var reorderedCover = daily; reorderedCover.scenes.swapAt(0, 1)
        checks["thumbnail_follows_reorder"] = reorderedCover.thumbnailIndex == 0 && reorderedCover.thumbnailScene?.id == daily.thumbnailSceneID
        reorderedCover.scenes.remove(at: 0); reorderedCover.normalizeThumbnail()
        checks["deleted_thumbnail_falls_back"] = reorderedCover.thumbnailIndex == 0 && reorderedCover.thumbnailScene != nil
        daily.motion = "zoom-out"; daily.transition = "fade"; daily.musicID = "little-weekend"
        let result = try await VideoRenderer.render(daily, assets: store.assets, exports: store.exports) { _, _ in }
        checks.merge(try await decodedPhotoChecks(project: daily, video: result, assets: store.assets)) { _, new in new }
        let asset = AVURLAsset(url: result)
        let audio = try await asset.loadTracks(withMediaType: .audio)
        let duration = try await asset.load(.duration)
        checks["daily_mp4_with_offset_music"] = !audio.isEmpty && abs(duration.seconds - 4) < 0.05
        let jpeg = try Data(contentsOf: VideoRenderer.thumbnailURL(for: result))
        let expectedCover = try VideoRenderer.frame(daily, scene: daily.scenes[1], index: 1, assets: store.assets, progress: 0.5).jpegData(compressionQuality: 0.9)
        checks["thumbnail_uses_selected_scene"] = jpeg == expectedCover
        let metadata = try await asset.loadMetadata(for: .iTunesMetadata)
        if let cover = AVMetadataItem.metadataItems(from: metadata, filteredByIdentifier: .iTunesMetadataCoverArt).first {
            checks["thumbnail_embedded_with_music"] = try await cover.load(.dataValue) == jpeg
        } else { checks["thumbnail_embedded_with_music"] = false }
        var noMusic = daily; noMusic.musicID = ""
        let silentURL = try await VideoRenderer.render(noMusic, assets: store.assets, exports: store.exports) { _, _ in }
        let silentMetadata = try await AVURLAsset(url: silentURL).loadMetadata(for: .iTunesMetadata)
        if let cover = AVMetadataItem.metadataItems(from: silentMetadata, filteredByIdentifier: .iTunesMetadataCoverArt).first {
            checks["thumbnail_embedded_without_music"] = try await cover.load(.dataValue) == Data(contentsOf: VideoRenderer.thumbnailURL(for: silentURL))
        } else { checks["thumbnail_embedded_without_music"] = false }
        var long = daily; long.scenes[0].duration = 30; long.scenes[1].duration = 30
        let task = Task { try await VideoRenderer.render(long, assets: store.assets, exports: store.exports) { _, _ in } }
        try await Task.sleep(nanoseconds: 100_000_000); task.cancel()
        do { _ = try await task.value; checks["render_cancelled"] = false }
        catch is CancellationError { checks["render_cancelled"] = true }
        catch { checks["render_cancelled"] = false }
        checks["cancelled_render_cleans_temporary_video"] = !(try FileManager.default.contentsOfDirectory(at: store.exports, includingPropertiesForKeys: nil)).contains { $0.lastPathComponent.hasSuffix("-silent.mp4") }
        checks.merge(try await fontSizeChecks(store: store)) { _, new in new }
        return checks
    }

    /// Index recovery, text limits, file cleanup and clean-subtitle shadow checks.
    /// Uses only temporary stores and writes tmp/store-check-receipt.json.
    static func verifyStore() async {
        let base = FileManager.default.temporaryDirectory.appendingPathComponent("store-check-" + UUID().uuidString)
        var checks: [String: Bool] = [:]
        let files = FileManager.default
        func names(_ url: URL) -> Set<String> { Set((try? files.contentsOfDirectory(atPath: url.path)) ?? []) }
        func corruptCopies(_ root: URL) -> [URL] { names(root).filter { $0.hasPrefix("projects.corrupt-") }.map { root.appendingPathComponent($0) } }
        do {
            // I1: one null field and one broken record must not erase the other projects.
            let lossy = base.appendingPathComponent("lossy")
            try files.createDirectory(at: lossy, withIntermediateDirectories: true)
            var good = StudioProject(); good.title = "정상"; good.scenes = [StudioScene(title: "장면")]
            var nullVideo = StudioProject(); nullVideo.title = "lastVideo null"
            var rows = try JSONSerialization.jsonObject(with: JSONEncoder().encode([good, nullVideo])) as! [[String: Any]]
            rows[1]["lastVideo"] = NSNull(); rows[1].removeValue(forKey: "musicVolume")
            rows.append(["id": "broken", "title": "깨진 항목", "scenes": "not-a-list"])
            let original = try JSONSerialization.data(withJSONObject: rows)
            try original.write(to: lossy.appendingPathComponent("projects.json"))
            let orphan = lossy.appendingPathComponent("assets/old-orphan.jpg")
            try files.createDirectory(at: orphan.deletingLastPathComponent(), withIntermediateDirectories: true)
            try Data([1]).write(to: orphan); try files.setAttributes([.modificationDate: Date(timeIntervalSinceNow: -7200)], ofItemAtPath: orphan.path)
            let lossyStore = StudioStore(root: lossy)
            checks["lossy_keeps_valid_projects"] = lossyStore.projects.map(\.title) == ["정상", "lastVideo null"]
            checks["lossy_null_field_defaults"] = lossyStore.projects.last?.lastVideo == "" && lossyStore.projects.last?.musicVolume == 0.35
            checks["lossy_reports_issue"] = lossyStore.loadIssue != nil && !lossyStore.persistBlocked
            checks["lossy_backup_is_original"] = corruptCopies(lossy).count == 1 && (try? Data(contentsOf: corruptCopies(lossy)[0])) == original
            checks["lossy_skips_orphan_sweep"] = files.fileExists(atPath: orphan.path)
            _ = lossyStore.create(kind: "daily")
            checks["lossy_create_keeps_projects"] = StudioStore(root: lossy).projects.count == 3

            let garbage = base.appendingPathComponent("garbage")
            try files.createDirectory(at: garbage, withIntermediateDirectories: true)
            try Data("{not json".utf8).write(to: garbage.appendingPathComponent("projects.json"))
            let garbageStore = StudioStore(root: garbage)
            checks["garbage_backed_up"] = garbageStore.projects.isEmpty && garbageStore.loadIssue != nil && corruptCopies(garbage).count == 1

            let unreadable = base.appendingPathComponent("unreadable")
            try files.createDirectory(at: unreadable.appendingPathComponent("projects.json"), withIntermediateDirectories: true)
            let unreadableStore = StudioStore(root: unreadable)
            _ = unreadableStore.create(kind: "daily")
            var isDirectory: ObjCBool = false
            checks["unreadable_blocks_persist"] = unreadableStore.persistBlocked && files.fileExists(atPath: unreadable.appendingPathComponent("projects.json").path, isDirectory: &isDirectory) && isDirectory.boolValue

            // I4: long/blank titles and long captions export with safe names and PC limits.
            let store = StudioStore(root: base.appendingPathComponent("main"))
            let white = UIGraphicsImageRenderer(size: CGSize(width: 1080, height: 1920)).image { _ in UIColor.white.setFill(); UIRectFill(CGRect(x: 0, y: 0, width: 1080, height: 1920)) }
            let jpeg = try await Task.detached { try StudioStore.preparePhoto(white.jpegData(compressionQuality: 0.9)!) }.value
            var project = StudioProject(); project.title = String(repeating: "가", count: 120)
            var scene = StudioScene(title: "흰 사진", photoID: try store.registerPhoto(jpeg)); scene.duration = 0.5; scene.narration = "밝은 사진 위 자막"
            project.scenes = [scene]; project.musicID = ""; project.motion = "still"; project.transition = "cut"; project.subtitleStyle = "clean"
            func exported(_ value: StudioProject) throws -> (URL, StudioProject) {
                let url = try store.exportTransfer(value)
                return (url, try JSONDecoder().decode(TransferFile.self, from: Data(contentsOf: url)).project)
            }
            let (longURL, longProject) = try exported(project)
            checks["export_long_title_file_name"] = files.fileExists(atPath: longURL.path) && longURL.lastPathComponent.precomposedStringWithCanonicalMapping.utf8.count < 255
            checks["export_long_title_kept"] = longProject.title.count == 120
            project.title = String(repeating: "나", count: 151); project.caption = String(repeating: "다", count: 2300)
            project.scenes[0].title = String(repeating: "라", count: 100)
            let (_, clamped) = try exported(project)
            checks["export_clamps_text"] = clamped.title.count == 150 && clamped.caption.count == 2200 && clamped.scenes[0].title.count == 90
            project.title = "   "
            let (blankURL, blank) = try exported(project)
            checks["export_blank_title_default"] = blank.title == "나의 일상 영상" && blankURL.lastPathComponent.hasPrefix("나의 일상 영상-")
            checks["export_unsafe_name"] = StudioStore.transferFileName("a/b:c\\d?e%f*g|h\"i<j>k") == "a-b-c-d-e-f-g-h-i-j-k" && StudioStore.transferFileName("  ") == "project"
            checks["export_keeps_latest_studio_only"] = names(store.exports).filter { $0.hasSuffix(".studio") } == [blankURL.lastPathComponent]
            let family = String(repeating: "👨‍👩‍👧", count: 60)
            checks["limit_counts_code_points"] = StudioProject.limited(family, 150).unicodeScalars.count <= 150 && StudioProject.limited("abc", 150) == "abc"

            // I3: clean subtitles get a dark shadow on a white photo.
            project.title = "검증"; project.caption = ""
            let frame = try VideoRenderer.frame(project, scene: project.scenes[0], index: 0, assets: store.assets)
            var gray = [UInt8](repeating: 0, count: 1080 * 1920)
            gray.withUnsafeMutableBytes { bytes in
                let context = CGContext(data: bytes.baseAddress, width: 1080, height: 1920, bitsPerComponent: 8, bytesPerRow: 1080,
                                        space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGImageAlphaInfo.none.rawValue)!
                context.draw(frame.cgImage!, in: CGRect(x: 0, y: 0, width: 1080, height: 1920))
            }
            checks["clean_subtitle_shadow_visible"] = gray.filter { $0 < 80 }.count > 500
            try? frame.pngData()?.write(to: FileManager.default.temporaryDirectory.appendingPathComponent("store-check-clean-frame.png"))

            // I5: re-render, invalidation and delete remove unreachable files.
            store.save(project)
            let first = try await VideoRenderer.render(project, assets: store.assets, exports: store.exports) { _, _ in }
            project.lastVideo = first.lastPathComponent; store.save(project)
            let second = try await VideoRenderer.render(project, assets: store.assets, exports: store.exports) { _, _ in }
            project.lastVideo = second.lastPathComponent; store.save(project)
            checks["rerender_removes_previous_video"] = !files.fileExists(atPath: first.path) && !files.fileExists(atPath: VideoRenderer.thumbnailURL(for: first).path)
                && files.fileExists(atPath: second.path) && files.fileExists(atPath: VideoRenderer.thumbnailURL(for: second).path)
            project.lastVideo = ""; store.save(project)
            checks["invalidation_removes_video"] = !files.fileExists(atPath: second.path) && !files.fileExists(atPath: VideoRenderer.thumbnailURL(for: second).path)
            let third = try await VideoRenderer.render(project, assets: store.assets, exports: store.exports) { _, _ in }
            project.lastVideo = third.lastPathComponent; store.save(project)
            var sharing = StudioProject(); sharing.scenes = [StudioScene(title: "공유 사진", photoID: project.scenes[0].photoID)]; store.save(sharing)
            let ownPhoto = try store.registerPhoto(jpeg)
            var deleting = StudioProject(); deleting.scenes = [StudioScene(title: "삭제", photoID: ownPhoto)]; store.save(deleting)
            store.delete(deleting)
            checks["delete_removes_own_photo"] = !files.fileExists(atPath: store.assets.appendingPathComponent(ownPhoto).path)
            store.delete(project)
            checks["delete_removes_video_keeps_shared_photo"] = !files.fileExists(atPath: third.path) && !files.fileExists(atPath: VideoRenderer.thumbnailURL(for: third).path)
                && files.fileExists(atPath: store.assets.appendingPathComponent(sharing.scenes[0].photoID).path)
            let oldOrphan = store.assets.appendingPathComponent("orphan-old.jpg"), newOrphan = store.assets.appendingPathComponent("orphan-new.jpg")
            let oldExport = store.exports.appendingPathComponent("orphan-old.mp4")
            for url in [oldOrphan, newOrphan, oldExport] { try Data([1]).write(to: url) }
            for url in [oldOrphan, oldExport] { try files.setAttributes([.modificationDate: Date(timeIntervalSinceNow: -7200)], ofItemAtPath: url.path) }
            let reopened = StudioStore(root: store.root)
            checks["sweep_removes_old_orphans"] = !files.fileExists(atPath: oldOrphan.path) && !files.fileExists(atPath: oldExport.path)
            checks["sweep_keeps_recent_and_referenced"] = files.fileExists(atPath: newOrphan.path) && files.fileExists(atPath: store.assets.appendingPathComponent(sharing.scenes[0].photoID).path) && reopened.projects.count == 1
        } catch { checks["completed"] = false }
        try? files.removeItem(at: base)
        if let data = try? JSONSerialization.data(withJSONObject: checks, options: [.sortedKeys]) {
            try? data.write(to: FileManager.default.temporaryDirectory.appendingPathComponent("store-check-receipt.json"), options: .atomic)
        }
    }

    nonisolated static func photoPixels(_ image: CGImage) -> [UInt8] {
        var pixels = [UInt8](repeating: 0, count: 64 * 114 * 4)
        pixels.withUnsafeMutableBytes { bytes in
            let context = CGContext(data: bytes.baseAddress, width: 64, height: 114, bitsPerComponent: 8,
                bytesPerRow: 64 * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue | CGBitmapInfo.byteOrder32Big.rawValue)!
            context.draw(image, in: CGRect(x: 0, y: 0, width: 64, height: 114))
        }
        return pixels
    }
    nonisolated static func decodedPhotoChecks(project: StudioProject, video: URL, assets: URL) async throws -> [String: Bool] {
        let generator = AVAssetImageGenerator(asset: AVURLAsset(url: video))
        generator.appliesPreferredTrackTransform = true
        generator.requestedTimeToleranceBefore = .zero; generator.requestedTimeToleranceAfter = .zero
        var checks: [String: Bool] = [:]; var cursor = 0.0
        var samples: [(String, Int, Double, Double)] = [("decoded_first_frame_photo", 0, 0, 0)]
        for (index, scene) in project.scenes.enumerated() {
            samples.append(("decoded_scene_\(index + 1)_photo", index, cursor + scene.duration / 2, scene.duration / 2))
            cursor += scene.duration
        }
        samples.append(("decoded_last_frame_photo", project.scenes.count - 1, cursor - 1 / Double(VideoRenderer.fps), project.scenes.last!.duration - 1 / Double(VideoRenderer.fps)))
        for (key, index, time, elapsed) in samples {
            let image = try await generator.image(at: CMTime(seconds: time, preferredTimescale: 600)).image
            let expected = try VideoRenderer.frame(project, scene: project.scenes[index], index: index, assets: assets,
                progress: elapsed / project.scenes[index].duration, elapsed: elapsed)
            let actualPixels = photoPixels(image), expectedPixels = photoPixels(expected.cgImage!)
            let error = zip(actualPixels, expectedPixels).enumerated().filter { $0.offset % 4 != 3 }.reduce(0.0) { $0 + Double(abs(Int($1.element.0)-Int($1.element.1))) } / Double(64*114*3)
            let average = actualPixels.enumerated().filter { $0.offset % 4 != 3 }.reduce(0.0) { $0 + Double($1.element) } / Double(64*114*3)
            checks[key] = error < 12 && average > 10
            if key == "decoded_first_frame_photo" {
                try UIImage(cgImage: image).jpegData(compressionQuality: 0.85)?.write(to: FileManager.default.temporaryDirectory.appendingPathComponent("decoded-first-frame.jpg"))
            }
        }
        return checks
    }

    static func whitePixels(_ image: CGImage) -> Int {
        var pixels = [UInt8](repeating: 0, count: image.width * image.height)
        pixels.withUnsafeMutableBytes { bytes in
            let context = CGContext(data: bytes.baseAddress, width: image.width, height: image.height,
                bitsPerComponent: 8, bytesPerRow: image.width, space: CGColorSpaceCreateDeviceGray(), bitmapInfo: CGImageAlphaInfo.none.rawValue)!
            context.draw(image, in: CGRect(x: 0, y: 0, width: image.width, height: image.height))
        }
        return pixels.filter { $0 > 225 }.count
    }

    static func fontSizeChecks(store: StudioStore) async throws -> [String: Bool] {
        var checks: [String: Bool] = [:]
        let image = UIGraphicsImageRenderer(size: CGSize(width: 1080, height: 1920)).image { _ in
            UIColor.black.setFill(); UIRectFill(CGRect(x: 0, y: 0, width: 1080, height: 1920))
        }
        let photoID = try store.importPhoto(image.jpegData(compressionQuality: 0.8)!)
        var project = StudioProject(); var scene = StudioScene(title: "크기", photoID: photoID)
        scene.narration = "한글 크기 확인"; scene.duration = 0.6
        project.scenes = [scene]; project.subtitleStyle = "clean"; project.motion = "still"; project.transition = "cut"; project.musicID = ""
        var fonts: [(String, String)] = [("system", "")]
        for font in store.bundledFonts { fonts.append((font.id, try store.importBundledFont(font))) }
        for (name, id) in fonts {
            project.fontAssetID = id
            let counts = try [24.0, 96.0].map { size in
                try autoreleasepool {
                    project.subtitleSize = size
                    return whitePixels(try VideoRenderer.frame(project, scene: scene, index: 0, assets: store.assets).cgImage!)
                }
            }
            checks["font_size_preview_" + name] = counts[0] > 0 && counts[1] > counts[0] * 6
        }
        project.fontAssetID = fonts.last!.1
        var encodedCounts: [Int] = []
        for size in [24.0, 96.0] {
            project.subtitleSize = size
            let url = try await VideoRenderer.render(project, assets: store.assets, exports: store.exports) { _, _ in }
            let generator = AVAssetImageGenerator(asset: AVURLAsset(url: url)); generator.appliesPreferredTrackTransform = true
            let frame = try await generator.image(at: CMTime(seconds: 0.3, preferredTimescale: 600)).image
            encodedCounts.append(whitePixels(frame))
        }
        checks["font_size_encoded_mp4"] = encodedCounts[0] > 0 && encodedCounts[1] > encodedCounts[0] * 6
        project.subtitleSize = 96; store.save(project)
        checks["font_size_persisted"] = StudioStore(root: store.root).projects.first(where: { $0.id == project.id })?.effectiveSubtitleSize == 96
        return checks
    }
}
#endif
