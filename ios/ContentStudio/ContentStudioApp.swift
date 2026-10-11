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
                    #endif
                }
                .tint(.indigo)
        }
    }
    #if DEBUG
    @MainActor private func verifyRendering() async {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("render-check-" + UUID().uuidString)
        var checks: [String: Bool] = [:]
        do {
            let temporaryStore = StudioStore(root: root)
            var project = temporaryStore.create(kind: "news")
            project.scenes[0].duration = 0.4
            project.scenes[0].body = "카드 본문 확인"
            project.scenes[0].narration = "자막 확인"
            for music in ["slow-morning", "little-weekend", "after-hours"] {
                project.musicID = music
                let url = try await VideoRenderer.render(project, assets: temporaryStore.assets, exports: temporaryStore.exports) { _, _ in }
                let asset = AVURLAsset(url: url)
                let tracks = try await asset.loadTracks(withMediaType: .audio)
                let duration = try await asset.load(.duration)
                checks[music] = !tracks.isEmpty && duration.seconds > 0.3
            }
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
    static var previewRoot: URL? {
        ProcessInfo.processInfo.arguments.contains(where: { $0.hasPrefix("--preview-daily-") }) ?
            FileManager.default.temporaryDirectory.appendingPathComponent("daily-ui-preview") : nil
    }
    static func previewProject(store: StudioStore) -> StudioProject? {
        guard previewRoot != nil else { return nil }
        if let project = store.projects.first { return project }
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
        let transferred = try store.importTransfer(store.exportTransfer(daily))
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
        for motion in ["still", "zoom", "zoom-out", "pan-left", "pan-right"] {
            daily.motion = motion
            let start = try VideoRenderer.frame(daily, scene: daily.scenes[0], index: 0, assets: store.assets, progress: 0).pngData()
            let end = try VideoRenderer.frame(daily, scene: daily.scenes[0], index: 0, assets: store.assets, progress: 1).pngData()
            checks["motion_" + motion] = motion == "still" ? start == end : start != end
        }
        daily.motion = "zoom-out"; daily.transition = "fade"; daily.musicID = "little-weekend"
        let result = try await VideoRenderer.render(daily, assets: store.assets, exports: store.exports) { _, _ in }
        let asset = AVURLAsset(url: result)
        let audio = try await asset.loadTracks(withMediaType: .audio)
        let duration = try await asset.load(.duration)
        checks["daily_mp4_with_offset_music"] = !audio.isEmpty && abs(duration.seconds - 4) < 0.05
        var long = daily; long.scenes[0].duration = 30; long.scenes[1].duration = 30
        let task = Task { try await VideoRenderer.render(long, assets: store.assets, exports: store.exports) { _, _ in } }
        try await Task.sleep(nanoseconds: 100_000_000); task.cancel()
        do { _ = try await task.value; checks["render_cancelled"] = false }
        catch is CancellationError { checks["render_cancelled"] = true }
        catch { checks["render_cancelled"] = false }
        return checks
    }

}
#endif
