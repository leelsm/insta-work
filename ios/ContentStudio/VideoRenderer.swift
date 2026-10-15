import AVFoundation
import CoreText
import CoreVideo
import Foundation
import UIKit

enum VideoRenderer {
    static let size = CGSize(width: 1080, height: 1920)
    static let fps: Int32 = 30
    static let layoutVersion = 4

    static func render(_ project: StudioProject, assets: URL, exports: URL,
                       progress: @escaping @Sendable (Double, String) -> Void) async throws -> URL {
        guard project.canRender else { throw StudioError.render("장면을 추가하고 영상 길이를 180초 이하로 맞춰 주세요.") }
        let job = Task.detached(priority: .userInitiated) {
            let silent = exports.appendingPathComponent(UUID().uuidString + "-silent.mp4")
            let result = exports.appendingPathComponent(project.id + "-" + UUID().uuidString + ".mp4")
            try FileManager.default.createDirectory(at: exports, withIntermediateDirectories: true)
            do {
                let jpeg = try autoreleasepool {
                    let image = try thumbnailImage(project, assets: assets)
                    guard let data = image.jpegData(compressionQuality: 0.9) else { throw StudioError.render("썸네일 이미지를 만들 수 없습니다.") }
                    return data
                }
                try jpeg.write(to: thumbnailURL(for: result), options: .atomic)
                let metadata = thumbnailMetadata(jpeg)
                try await encodeVideo(project, assets: assets, output: silent, metadata: metadata, progress: progress)
                try Task.checkCancellation()
                if let music = musicURL(project, assets: assets) {
                    progress(0.92, "배경음악 합치는 중")
                    try await addMusic(music, to: silent, output: result,
                                       volume: Float(project.musicVolume), offset: project.effectiveMusicOffset, metadata: metadata)
                    try? FileManager.default.removeItem(at: silent)
                } else {
                    try FileManager.default.moveItem(at: silent, to: result)
                }
                try Task.checkCancellation()
                progress(1, "영상 제작 완료")
                return result
            } catch {
                try? FileManager.default.removeItem(at: silent)
                try? FileManager.default.removeItem(at: result)
                try? FileManager.default.removeItem(at: thumbnailURL(for: result))
                throw error
            }
        }
        return try await withTaskCancellationHandler(operation: { try await job.value }, onCancel: { job.cancel() })
    }

    static func thumbnailURL(for video: URL) -> URL { video.deletingPathExtension().appendingPathExtension("jpg") }
    static func thumbnailImage(_ project: StudioProject, assets: URL) throws -> UIImage {
        guard let scene = project.thumbnailScene else { throw StudioError.render("썸네일 장면을 선택하세요.") }
        return try frame(project, scene: scene, index: project.thumbnailIndex, assets: assets, progress: 0.5)
    }
    private static func thumbnailMetadata(_ data: Data) -> [AVMetadataItem] {
        let item = AVMutableMetadataItem()
        item.identifier = .iTunesMetadataCoverArt
        item.value = data as NSData
        item.dataType = kCMMetadataBaseDataType_JPEG as String
        return [item]
    }

    static func musicURL(_ project: StudioProject, assets: URL) -> URL? {
        if !project.musicAssetID.isEmpty {
            let url = assets.appendingPathComponent(project.musicAssetID)
            return FileManager.default.fileExists(atPath: url.path) ? url : nil
        }
        guard !project.musicID.isEmpty else { return nil }
        if let track = MusicLibrary.tracks.first(where: { $0.id == project.musicID }) {
            return Bundle.main.url(forResource: track.filename, withExtension: nil, subdirectory: "music")
        }
        return Bundle.main.url(forResource: project.musicID, withExtension: "wav")
    }

    private static func encodeVideo(_ project: StudioProject, assets: URL, output: URL,
                                    metadata: [AVMetadataItem], progress: @escaping @Sendable (Double, String) -> Void) async throws {
        let writer = try AVAssetWriter(outputURL: output, fileType: .mp4)
        writer.metadata = metadata
        let settings: [String: Any] = [AVVideoCodecKey: AVVideoCodecType.h264,
                                      AVVideoWidthKey: Int(size.width), AVVideoHeightKey: Int(size.height),
                                      AVVideoCompressionPropertiesKey: [AVVideoAverageBitRateKey: 6_000_000]]
        let input = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
        input.expectsMediaDataInRealTime = false
        let attrs: [String: Any] = [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
                                    kCVPixelBufferWidthKey as String: Int(size.width),
                                    kCVPixelBufferHeightKey as String: Int(size.height),
                                    kCVPixelBufferCGImageCompatibilityKey as String: true,
                                    kCVPixelBufferCGBitmapContextCompatibilityKey as String: true]
        let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: attrs)
        guard writer.canAdd(input) else { throw StudioError.render("이 기기에서 MP4 인코딩을 시작할 수 없습니다.") }
        writer.add(input)
        guard writer.startWriting() else { throw writer.error ?? StudioError.render("영상 작성을 시작하지 못했습니다.") }
        writer.startSession(atSourceTime: .zero)
        // Cancel the writer on every early exit, including user cancellation.
        defer { if writer.status == .writing { writer.cancelWriting() } }
        guard let pool = adaptor.pixelBufferPool else { throw StudioError.render("영상 프레임 메모리를 준비하지 못했습니다.") }
        var frameNumber: Int64 = 0
        let totalFrames = max(1, project.scenes.reduce(0) { $0 + Int64(($1.duration * Double(fps)).rounded()) })
        for (index, scene) in project.scenes.enumerated() {
            try Task.checkCancellation()
            progress(Double(frameNumber) / Double(totalFrames) * 0.9, "장면 \(index + 1)/\(project.scenes.count) 제작 중")
            let count = max(1, Int64((scene.duration * Double(fps)).rounded()))
            for sceneFrame in 0..<count {
                try Task.checkCancellation()
                while !input.isReadyForMoreMediaData {
                    try Task.checkCancellation()
                    guard writer.status == .writing else { throw writer.error ?? StudioError.render("영상 작성을 계속할 수 없습니다.") }
                    try await Task.sleep(nanoseconds: 10_000_000)
                }
                // Drain UIKit temporaries every frame rather than retaining them for
                // the entire detached task. Reuse the encoder's pixel buffer pool.
                try autoreleasepool {
                    let elapsed = Double(sceneFrame) / Double(fps)
                    let outputImage = try frame(project, scene: scene, index: index, assets: assets,
                                                progress: elapsed / scene.duration, elapsed: elapsed)
                    guard let buffer = pixelBuffer(outputImage, pool: pool) else { throw StudioError.render("영상 프레임을 만들지 못했습니다.") }
                    let time = CMTime(value: frameNumber, timescale: fps)
                    guard adaptor.append(buffer, withPresentationTime: time) else {
                        throw writer.error ?? StudioError.render("영상 프레임을 저장하지 못했습니다.")
                    }
                }
                frameNumber += 1
                if frameNumber % Int64(fps) == 0 { progress(Double(frameNumber) / Double(totalFrames) * 0.9, "장면 \(index + 1)/\(project.scenes.count) 제작 중") }
            }
        }
        input.markAsFinished()
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            writer.finishWriting {
                if writer.status == .completed { continuation.resume() }
                else { continuation.resume(throwing: writer.error ?? StudioError.render("MP4 저장에 실패했습니다.")) }
            }
        }
    }

    private static func pixelBuffer(_ image: UIImage, pool: CVPixelBufferPool) -> CVPixelBuffer? {
        var buffer: CVPixelBuffer?
        guard CVPixelBufferPoolCreatePixelBuffer(kCFAllocatorDefault, pool, &buffer) == kCVReturnSuccess,
              let buffer, let cgImage = image.cgImage else { return nil }
        CVPixelBufferLockBaseAddress(buffer, [])
        defer { CVPixelBufferUnlockBaseAddress(buffer, []) }
        let info = CGBitmapInfo.byteOrder32Little.rawValue | CGImageAlphaInfo.premultipliedFirst.rawValue
        guard let context = CGContext(data: CVPixelBufferGetBaseAddress(buffer), width: Int(size.width),
                                      height: Int(size.height), bitsPerComponent: 8,
                                      bytesPerRow: CVPixelBufferGetBytesPerRow(buffer),
                                      space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: info) else { return nil }
        context.draw(cgImage, in: CGRect(origin: .zero, size: size))
        return buffer
    }

    private static let fontNames = NSCache<NSString, NSString>()

    static func font(_ project: StudioProject, assets: URL, size: CGFloat) -> UIFont {
        guard !project.fontAssetID.isEmpty else { return .systemFont(ofSize: size, weight: .semibold) }
        let url = assets.appendingPathComponent(project.fontAssetID)
        guard FileManager.default.fileExists(atPath: url.path) else { return .systemFont(ofSize: size, weight: .semibold) }
        let key = url.path as NSString
        if let name = fontNames.object(forKey: key), let face = UIFont(name: name as String, size: size) { return face }
        var registrationError: Unmanaged<CFError>?
        _ = CTFontManagerRegisterFontsForURL(url as CFURL, .process, &registrationError)
        guard let descriptors = CTFontManagerCreateFontDescriptorsFromURL(url as CFURL) as? [CTFontDescriptor],
              let descriptor = descriptors.first,
              let name = CTFontDescriptorCopyAttribute(descriptor, kCTFontNameAttribute) as? String,
              let face = UIFont(name: name, size: size) else { return .systemFont(ofSize: size, weight: .semibold) }
        fontNames.setObject(name as NSString, forKey: key)
        return face
    }

    private static func drawText(_ text: String, rect: CGRect, size: CGFloat, color: UIColor,
                                 font: UIFont, alignment: NSTextAlignment = .left) {
        let paragraph = NSMutableParagraphStyle()
        paragraph.alignment = alignment
        paragraph.lineBreakMode = .byWordWrapping
        (text as NSString).draw(in: rect, withAttributes: [.font: font, .foregroundColor: color,
                                                          .paragraphStyle: paragraph])
    }

    private static func caption(_ text: String, project: StudioProject, assets: URL, color: UIColor = .white) {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        let fontSize = CGFloat(project.effectiveSubtitleSize)
        let face = font(project, assets: assets, size: fontSize)
        let maxWidth: CGFloat = 880
        let measured = (text as NSString).boundingRect(with: CGSize(width: maxWidth - 60, height: 1100),
            options: [.usesLineFragmentOrigin, .usesFontLeading], attributes: [.font: face], context: nil)
        let boxWidth = min(maxWidth, max(340, measured.width + 80))
        let boxHeight = min(1200, max(125, measured.height + 56))
        let x = max(30, min(size.width - boxWidth - 30, size.width * project.subtitleX - boxWidth / 2))
        let y = max(75, min(size.height - boxHeight - 100, size.height * project.subtitleY - boxHeight / 2))
        let box = CGRect(x: x, y: y, width: boxWidth, height: boxHeight)
        if project.subtitleStyle == "box" {
            UIColor.black.withAlphaComponent(0.76).setFill()
            UIBezierPath(roundedRect: box, cornerRadius: 24).fill()
        }
        drawText(text, rect: box.insetBy(dx: 28, dy: 22), size: fontSize, color: color, font: face)
    }

    private static let backgrounds: NSCache<NSString, UIImage> = {
        let cache = NSCache<NSString, UIImage>()
        cache.totalCostLimit = 32_000_000
        cache.countLimit = 16
        return cache
    }()

    private static func background(_ scene: StudioScene, assets: URL, pixelWidth: CGFloat) -> UIImage? {
        let renderSize = CGSize(width: pixelWidth, height: pixelWidth * 16 / 9)
        let key = "\(assets.path)/\(scene.photoID)/\(scene.photoFit)/\(scene.positionX)/\(scene.positionY)/\(Int(pixelWidth))" as NSString
        if let image = backgrounds.object(forKey: key) { return image }
        guard let photo = UIImage(contentsOfFile: assets.appendingPathComponent(scene.photoID).path) else { return nil }
        let format = UIGraphicsImageRendererFormat(); format.scale = 1; format.preferredRange = .standard; format.opaque = true
        let image = UIGraphicsImageRenderer(size: renderSize, format: format).image { _ in
            UIColor(red: 0.08, green: 0.08, blue: 0.1, alpha: 1).setFill()
            UIRectFill(CGRect(origin: .zero, size: renderSize))
            let ratio = scene.photoFit == "contain" ? min(renderSize.width / photo.size.width, renderSize.height / photo.size.height) : max(renderSize.width / photo.size.width, renderSize.height / photo.size.height)
            let target = CGSize(width: photo.size.width * ratio, height: photo.size.height * ratio)
            let x = (renderSize.width - target.width) * (scene.photoFit == "contain" ? 0.5 : scene.positionX)
            let y = (renderSize.height - target.height) * (scene.photoFit == "contain" ? 0.5 : scene.positionY)
            photo.draw(in: CGRect(x: x, y: y, width: target.width, height: target.height))
        }
        let cost = image.cgImage.map { $0.bytesPerRow * $0.height } ?? Int(renderSize.width * renderSize.height * 4)
        backgrounds.setObject(image, forKey: key, cost: cost)
        return image
    }

    static func frame(_ project: StudioProject, scene: StudioScene, index: Int, assets: URL,
                      progress: Double = 0, elapsed: Double? = nil, outputSize: CGSize? = nil) throws -> UIImage {
        let pixelWidth = min(size.width, max(1, (outputSize?.width ?? size.width) * (outputSize == nil ? 1 : 3)))
        let photo = background(scene, assets: assets, pixelWidth: pixelWidth)
        if project.isDaily && photo == nil { throw StudioError.invalidFile("장면 \(index + 1)의 사진이 없습니다. 사진을 다시 선택해주세요.") }
        let format = UIGraphicsImageRendererFormat(); format.scale = outputSize == nil ? 1 : 3
        format.preferredRange = .standard; format.opaque = true
        let targetSize = outputSize ?? size
        let renderer = UIGraphicsImageRenderer(size: targetSize, format: format)
        return renderer.image { context in
            context.cgContext.scaleBy(x: targetSize.width / size.width, y: targetSize.height / size.height)
            (project.template == "ink" ? UIColor(red: 0.09, green: 0.11, blue: 0.14, alpha: 1) :
                UIColor(red: 0.96, green: 0.94, blue: 0.9, alpha: 1)).setFill()
            UIRectFill(CGRect(origin: .zero, size: size))
            if let photo {
                let p = CGFloat(min(1, max(0, progress)))
                let motion = project.effectiveMotion
                let zoom: CGFloat = motion == "zoom" ? 1 + 0.045 * p : motion == "zoom-out" ? 1 + 0.045 * (1-p) : motion.hasPrefix("pan-") ? 1.045 : 1
                let shift: CGFloat = motion == "pan-left" ? size.width * 0.045 * (0.5-p) : motion == "pan-right" ? size.width * 0.045 * (p-0.5) : 0
                photo.draw(in: CGRect(x: size.width * (1-zoom)/2 + shift,
                                      y: size.height * (1-zoom)/2, width: size.width * zoom, height: size.height * zoom))
            }
            var text = scene.narration
            if !project.isDaily {
                if text.isEmpty { text = scene.body.isEmpty ? scene.title : scene.body }
                let parts = captionParts(text)
                text = parts[min(parts.count-1, Int(min(0.9999, max(0, progress)) * Double(parts.count)))]
            }
            caption(text, project: project, assets: assets)
            if let credit = scene.imageCredit, !credit.isEmpty {
                UIColor.black.withAlphaComponent(0.8).setFill()
                UIRectFillUsingBlendMode(CGRect(x: 68, y: 1785, width: 944, height: 75), .normal)
                drawText(credit, rect: CGRect(x: 85, y: 1800, width: 910, height: 45), size: 24,
                         color: .white, font: .systemFont(ofSize: 24))
            }
            if project.effectiveTransition == "fade", let elapsed {
                // Fade between scenes. Keep the first/last exported frames visible
                // so Photos and messaging previews do not pick a black frame.
                let fadeIn = index == 0 ? 1 : elapsed / 0.25
                let fadeOut = index == project.scenes.count - 1 ? 1 : (scene.duration-elapsed)/0.25
                let opacity = max(0, min(1, fadeIn, fadeOut))
                if opacity < 1 {
                    UIColor.black.withAlphaComponent(1-opacity).setFill()
                    // UIRectFill uses .copy and erases the photo, even at alpha 0.
                    UIRectFillUsingBlendMode(CGRect(origin: .zero, size: size), .normal)
                }
            }
        }
    }

    private static func captionParts(_ text: String) -> [String] {
        var result: [String] = []
        for paragraph in text.components(separatedBy: .newlines) {
            var remaining = paragraph.trimmingCharacters(in: .whitespaces)
            while remaining.count > 64 {
                let prefix = String(remaining.prefix(64))
                let cut = prefix.lastIndex(of: " ")
                let count = cut.map { prefix.distance(from: prefix.startIndex, to: $0) } ?? 64
                let length = count >= 15 ? count : 64
                result.append(String(remaining.prefix(length)).trimmingCharacters(in: .whitespaces))
                remaining = String(remaining.dropFirst(length)).trimmingCharacters(in: .whitespaces)
            }
            if !remaining.isEmpty { result.append(remaining) }
        }
        return result.isEmpty ? [""] : result
    }

    private static func addMusic(_ musicURL: URL, to videoURL: URL, output: URL,
                                 volume: Float, offset: Double = 0, metadata: [AVMetadataItem]) async throws {
        let video = AVURLAsset(url: videoURL)
        let audio = AVURLAsset(url: musicURL)
        guard let videoSource = try await video.loadTracks(withMediaType: .video).first,
              let audioSource = try await audio.loadTracks(withMediaType: .audio).first else {
            throw StudioError.render("음악 파일의 오디오 트랙을 읽을 수 없습니다.")
        }
        let composition = AVMutableComposition()
        guard let videoTrack = composition.addMutableTrack(withMediaType: .video,
                         preferredTrackID: kCMPersistentTrackID_Invalid),
              let musicTrack = composition.addMutableTrack(withMediaType: .audio,
                         preferredTrackID: kCMPersistentTrackID_Invalid) else {
            throw StudioError.render("영상과 음악을 합칠 수 없습니다.")
        }
        // Scene durations are rounded to whole frames during encoding. Use the
        // encoded track's duration so the composition never asks past its end.
        let total = try await video.load(.duration)
        try videoTrack.insertTimeRange(CMTimeRange(start: .zero, duration: total), of: videoSource, at: .zero)
        let audioDuration = try await audio.load(.duration)
        guard audioDuration.seconds > 0 else { throw StudioError.render("음악 길이를 확인할 수 없습니다.") }
        var cursor = CMTime.zero
        var audioStart = CMTime(seconds: offset.truncatingRemainder(dividingBy: audioDuration.seconds), preferredTimescale: 48000)
        while cursor < total {
            let remaining = CMTimeSubtract(total, cursor)
            let segment = CMTimeMinimum(CMTimeSubtract(audioDuration, audioStart), remaining)
            try musicTrack.insertTimeRange(CMTimeRange(start: audioStart, duration: segment), of: audioSource, at: cursor)
            cursor = CMTimeAdd(cursor, segment)
            audioStart = .zero
        }
        let mix = AVMutableAudioMix()
        let parameters = AVMutableAudioMixInputParameters(track: musicTrack)
        let level = max(0, min(1, volume))
        let fadeIn = CMTime(seconds: min(0.6, total.seconds / 2), preferredTimescale: 48000)
        let fadeOut = CMTime(seconds: min(0.8, total.seconds / 2), preferredTimescale: 48000)
        parameters.setVolumeRamp(fromStartVolume: 0, toEndVolume: level, timeRange: CMTimeRange(start: .zero, duration: fadeIn))
        parameters.setVolumeRamp(fromStartVolume: level, toEndVolume: 0, timeRange: CMTimeRange(start: CMTimeSubtract(total, fadeOut), duration: fadeOut))
        mix.inputParameters = [parameters]
        guard let session = AVAssetExportSession(asset: composition, presetName: AVAssetExportPresetHighestQuality) else {
            throw StudioError.render("영상 내보내기를 시작할 수 없습니다.")
        }
        session.outputURL = output
        session.outputFileType = .mp4
        session.audioMix = mix
        session.metadata = metadata
        try await withTaskCancellationHandler(operation: {
            try Task.checkCancellation()
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                session.exportAsynchronously {
                    if session.status == .completed { continuation.resume() }
                    else if session.status == .cancelled { continuation.resume(throwing: CancellationError()) }
                    else { continuation.resume(throwing: session.error ?? StudioError.render("배경음악 합치기에 실패했습니다.")) }
                }
            }
        }, onCancel: { session.cancelExport() })
    }
}
