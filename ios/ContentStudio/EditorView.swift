import AVKit
import PhotosUI
import SwiftUI
import UniformTypeIdentifiers

private enum EditorTool: String, Identifiable, CaseIterable {
    case photo = "사진", subtitle = "자막", effects = "효과", music = "음악", ai = "분위기 · AI 자막"
    var id: String { rawValue }
    var icon: String { switch self { case .photo: return "photo"; case .subtitle: return "textformat"; case .effects: return "wand.and.stars"; case .music: return "music.note"; case .ai: return "sparkles" } }
}

struct EditorView: View {
    @ObservedObject var store: StudioStore
    @ObservedObject var ai: AISettings
    @State private var project: StudioProject
    @State private var selected = 0
    @State private var tool: EditorTool?
    @State private var photos: [PhotosPickerItem] = []
    @State private var replacement: PhotosPickerItem?
    @State private var showReplace = false
    @State private var importing = false
    @State private var importingMusic = false
    @State private var importingFont = false
    @State private var showAISettings = false
    @State private var showInspectorAISettings = false
    @State private var showExport = false
    @State private var showLargePreview = false
    @State private var rendering = false
    @State private var generating = false
    @State private var renderTask: Task<Void, Never>?
    @State private var progress = 0.0
    @State private var message = ""
    @State private var resultURL: URL?
    @State private var transferURL: URL?
    @State private var error = ""
    @State private var draggedID: String?
    @State private var previewTime = 0.0
    @State private var previewPlaying = false
    @State private var previewEpoch = Date()
    @State private var previewAnchor = 0.0
    @State private var auditioning = false
    @StateObject private var previewAudio = PreviewAudio()
    private let previewTimer = Timer.publish(every: 1.0 / 30, on: .main, in: .common).autoconnect()
    private var locked: Bool { rendering || generating || importing }
    private var scene: StudioScene? { project.scenes.indices.contains(selected) ? project.scenes[selected] : nil }

    init(initial: StudioProject, store: StudioStore, ai: AISettings, startWithAI: Bool = false) {
        self.store = store; self.ai = ai; _project = State(initialValue: initial)
        if !initial.lastVideo.isEmpty {
            let saved = store.exports.appendingPathComponent(initial.lastVideo)
            if FileManager.default.fileExists(atPath: saved.path) { _resultURL = State(initialValue: saved) }
        }
        if startWithAI { _tool = State(initialValue: .ai) }
        #if DEBUG
        if let value = ProcessInfo.processInfo.arguments.first(where: { $0.hasPrefix("--editor-tool=") }), let chosen = EditorTool(rawValue: String(value.dropFirst("--editor-tool=".count))) { _tool = State(initialValue: chosen) }
        #endif
    }

    var body: some View {
        GeometryReader { geometry in
            VStack(spacing: 12) {
                HStack {
                    TextField("영상 제목", text: binding(\.title)).font(.headline).submitLabel(.done)
                    Text("\(project.scenes.count)장 · \(project.duration, specifier: "%.1f")초").font(.caption).foregroundStyle(.secondary).fixedSize()
                }.padding(.horizontal, 20)
                preview(height: max(150, min(geometry.size.height - 285, tool == nil ? 460 : 270)))
                timeline
                HStack(spacing: 0) {
                    ForEach([EditorTool.photo, .subtitle, .effects, .music]) { item in
                        Button { pausePreview(); tool = item } label: {
                            VStack(spacing: 6) { Image(systemName: item.icon).font(.title3); Text(item.rawValue).font(.caption.weight(.medium)) }
                                .frame(maxWidth: .infinity).frame(minHeight: 56)
                                .foregroundStyle(tool == item ? .indigo : .primary)
                        }.buttonStyle(.plain).accessibilityIdentifier("editor-tool-\(item.id)")
                    }
                }.padding(.horizontal, 12)
            }.padding(.top, 8).frame(maxWidth: .infinity).disabled(locked)
        }
        .background(Color(uiColor: .systemGroupedBackground))
        .navigationTitle("일상 영상 편집").navigationBarTitleDisplayMode(.inline)
        .toolbar {
            Menu {
                Button("AI로 사진 자막 제안", systemImage: "sparkles") { requestAI() }
                Button("AI 연결 설정", systemImage: "gearshape") { pausePreview(); showAISettings = true }
                Button("게시 문안 · Mac으로 보내기", systemImage: "square.and.arrow.up") { pausePreview(); showExport = true }
            } label: { Image(systemName: "ellipsis.circle").frame(width: 44, height: 44) }.disabled(locked).accessibilityLabel("영상 메뉴")
        }
        .safeAreaInset(edge: .bottom) {
            VStack(spacing: 8) {
                if rendering || generating || importing {
                    HStack {
                        ProgressView(value: rendering ? progress : nil)
                        Text(message.isEmpty ? "사진을 준비하는 중…" : message).font(.caption).lineLimit(2)
                        if rendering { Button("중단") { renderTask?.cancel() }.font(.caption) }
                    }
                }
                Button { pausePreview(); showExport = true } label: {
                    Label(resultURL == nil ? "완성하고 저장하기" : "완성 영상 보기 · 공유", systemImage: resultURL == nil ? "film" : "square.and.arrow.up")
                        .font(.headline).frame(maxWidth: .infinity).padding(.vertical, 10)
                }.buttonStyle(.borderedProminent).disabled(!project.canRender || locked)
            }.padding(.horizontal, 20).padding(.vertical, 10).background(.bar)
        }
        .sheet(item: $tool, onDismiss: { previewAudio.stop(); auditioning = false }) { item in
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        switch item { case .photo: photoPanel; case .subtitle: subtitlePanel; case .effects: effectsPanel; case .music: musicPanel; case .ai: aiPanel }
                    }.padding(20).disabled(locked)
                }.background(Color(uiColor: .systemGroupedBackground))
                    .navigationTitle(item == .photo ? "장면 \(selected + 1) · 사진" : item.rawValue).navigationBarTitleDisplayMode(.inline)
                    .toolbar { Button("완료") { tool = nil } }
                    .sheet(isPresented: $showInspectorAISettings) { AISettingsView(settings: ai) }
                    .photosPicker(isPresented: $showReplace, selection: $replacement, matching: .images)
        .fileImporter(isPresented: $importingMusic, allowedContentTypes: [.audio]) { result in
            do {
                let url = try result.get()
                project.musicAssetID = try store.importFile(url, allowed: ["mp3", "m4a", "wav"], maxBytes: 25_000_000)
                project.musicName = url.lastPathComponent; project.musicID = ""; changed()
            } catch { self.error = error.localizedDescription }
        }
        .fileImporter(isPresented: $importingFont, allowedContentTypes: [.font, .data]) { result in
            do {
                let url = try result.get()
                project.fontAssetID = try store.importFile(url, allowed: ["ttf", "otf"], maxBytes: 20_000_000)
                project.fontName = url.lastPathComponent; changed()
            } catch { self.error = error.localizedDescription }
        }
                    .alert("작업을 완료하지 못했습니다", isPresented: Binding(get: { !error.isEmpty }, set: { if !$0 { error = "" } })) { Button("확인") { error = "" } } message: { Text(error) }
            }.presentationDetents([.height(320), .large]).presentationDragIndicator(.visible)
                .presentationBackgroundInteraction(.enabled(upThrough: .height(320)))
        }
        .sheet(isPresented: $showAISettings) { AISettingsView(settings: ai) }
        .sheet(isPresented: $showExport) { exportSheet }
        .fullScreenCover(isPresented: $showLargePreview) {
            GeometryReader { geometry in
                preview(height: max(150, min(geometry.size.height - 110, (geometry.size.width - 40) * 16 / 9)))
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }.background(.black).foregroundStyle(.white).tint(.white)
                .safeAreaInset(edge: .top) {
                    HStack { Text("실시간 미리보기").font(.headline); Spacer(); Button("완료") { pausePreview(); showLargePreview = false } }.padding(20).background(.black)
                }
        }
        .onChange(of: photos) { _, items in Task { await addPhotos(items) } }
        .onChange(of: replacement) { _, item in if let item { Task { await replacePhoto(item) } } }
        .onChange(of: selected) { _, _ in seekToSelected() }
        .onReceive(previewTimer) { date in
            guard previewPlaying else { return }
            previewTime = min(project.duration, previewAnchor + date.timeIntervalSince(previewEpoch))
            if previewTime >= project.duration { pausePreview() }
        }
        .onDisappear { pausePreview(); renderTask?.cancel() }
        .alert("작업을 완료하지 못했습니다", isPresented: Binding(get: { !error.isEmpty && tool == nil && !showExport }, set: { if !$0 { error = "" } })) { Button("확인") { error = "" } } message: { Text(error) }
    }

    private var previewPosition: (index: Int, elapsed: Double) {
        var cursor = 0.0
        for (index, scene) in project.scenes.enumerated() {
            if previewTime < cursor + scene.duration || index == project.scenes.count - 1 { return (index, max(0, min(scene.duration, previewTime-cursor))) }
            cursor += scene.duration
        }
        return (0, 0)
    }

    private func preview(height: CGFloat) -> some View {
        VStack(spacing: 9) {
            let position = previewPosition
            let canvas = CGSize(width: height * 9 / 16, height: height)
            ZStack {
                if project.scenes.indices.contains(position.index), let image = try? VideoRenderer.frame(project,
                    scene: project.scenes[position.index], index: position.index, assets: store.assets,
                    progress: position.elapsed / project.scenes[position.index].duration,
                    elapsed: previewPlaying ? position.elapsed : nil, outputSize: canvas) {
                    Image(uiImage: image).resizable().frame(width: canvas.width, height: canvas.height)
                } else { Color.indigo.opacity(0.1).overlay(Image(systemName: "photo").font(.largeTitle)) }
            }.frame(width: canvas.width, height: canvas.height).clipShape(RoundedRectangle(cornerRadius: 14))
                .contentShape(Rectangle()).gesture(DragGesture(minimumDistance: 5).onChanged { value in
                    guard !previewPlaying else { return }
                    project.subtitleX = min(0.95, max(0.05, value.location.x / canvas.width))
                    project.subtitleY = min(0.92, max(0.05, value.location.y / canvas.height))
                }.onEnded { _ in if !previewPlaying { changed() } })
                .accessibilityLabel("장면 \(position.index+1) 실시간 미리보기")
            HStack(spacing: 14) {
                Button { togglePreview() } label: { Image(systemName: previewPlaying ? "pause.fill" : "play.fill").frame(width: 40, height: 32) }.accessibilityLabel(previewPlaying ? "미리보기 일시정지" : "미리보기 재생")
                Button { seek(0) } label: { Image(systemName: "backward.end.fill").frame(width: 32, height: 32) }.accessibilityLabel("미리보기 처음부터")
                Button { showLargePreview.toggle() } label: { Image(systemName: "arrow.up.left.and.arrow.down.right").frame(width: 32, height: 32) }.accessibilityLabel("전체 화면 미리보기")
                Spacer()
                Text("\(position.index + 1)/\(project.scenes.count) · \(previewTime, specifier: "%.1f") / \(project.duration, specifier: "%.1f")초").font(.caption).monospacedDigit()
            }
            Slider(value: Binding(get: { min(previewTime, project.duration) }, set: { seek($0) }), in: 0...max(0.01, project.duration)).accessibilityLabel("미리보기 재생 위치")
        }.padding(.horizontal, 20)
    }

    private var timeline: some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 10) {
                    ForEach(Array(project.scenes.enumerated()), id: \.element.id) { index, scene in
                        Button { selected = index; seekToSelected() } label: {
                            VStack(spacing: 4) {
                                ZStack(alignment: .topLeading) {
                                    if let image = store.image(scene.photoID) { Image(uiImage: image).resizable().scaledToFill().frame(width: 56, height: 60).clipped() }
                                    Text("\(index+1)").font(.caption2.bold()).foregroundStyle(.white).padding(4).background(.black.opacity(0.55), in: RoundedRectangle(cornerRadius: 4))
                                }.clipShape(RoundedRectangle(cornerRadius: 8))
                                Text("\(scene.duration, specifier: "%.1f")초").font(.caption2).foregroundStyle(.secondary)
                            }.padding(4).overlay(RoundedRectangle(cornerRadius: 11).stroke(index == selected ? Color.indigo : .clear, lineWidth: 2))
                        }.buttonStyle(.plain).id(scene.id)
                            .onDrag { pausePreview(); draggedID = scene.id; return NSItemProvider(object: scene.id as NSString) }
                            .onDrop(of: [.text], delegate: SceneReorderDelegate(project: $project, selected: $selected, draggedID: $draggedID, targetID: scene.id, onChange: changed))
                            .contextMenu {
                                Button("앞으로 이동", systemImage: "arrow.left") { moveScene(index, -1) }.disabled(index == 0)
                                Button("뒤로 이동", systemImage: "arrow.right") { moveScene(index, 1) }.disabled(index == project.scenes.count-1)
                                Button("사진 설정", systemImage: "slider.horizontal.3") { selected = index; pausePreview(); tool = .photo }
                            }.accessibilityLabel("장면 \(index + 1), \(scene.duration, specifier: "%.1f")초")
                    }
                    PhotosPicker(selection: $photos, maxSelectionCount: max(1, 10-project.scenes.count), selectionBehavior: .ordered, matching: .images) {
                        Image(systemName: "plus").font(.title2).frame(width: 56, height: 78).background(.indigo.opacity(0.07), in: RoundedRectangle(cornerRadius: 10))
                    }.disabled(project.scenes.count >= 10).accessibilityLabel("사진 추가")
                }.padding(.horizontal, 20).padding(.vertical, 3)
            }.frame(height: 92)
                .onChange(of: selected) { _, _ in if let scene { withAnimation { proxy.scrollTo(scene.id, anchor: .center) } } }
        }
    }

    @ViewBuilder private var photoPanel: some View {
        if let scene {
            HStack {
                Button { moveScene(selected, -1) } label: { Label("앞으로", systemImage: "arrow.left") }.disabled(selected == 0)
                Spacer()
                Button { moveScene(selected, 1) } label: { Label("뒤로", systemImage: "arrow.right") }.disabled(selected == project.scenes.count-1)
            }.buttonStyle(.bordered)
            HStack {
                Button { showReplace = true } label: { Label("사진 바꾸기", systemImage: "photo") }.buttonStyle(.bordered)
                Spacer()
                Button("삭제", role: .destructive) { project.scenes.remove(at: selected); selected = max(0, min(selected, project.scenes.count-1)); changed(); seekToSelected() }.disabled(project.scenes.count <= 1)
            }
            VStack(alignment: .leading, spacing: 8) {
                Text("표시 시간 · \(scene.duration, specifier: "%.1f")초").font(.subheadline.bold())
                Slider(value: sceneBinding(\.duration, scene), in: 2...30, step: 0.5)
            }
            Picker("사진 맞춤", selection: sceneBinding(\.photoFit, scene)) { Text("화면 채우기").tag("cover"); Text("사진 전체 보기").tag("contain") }.pickerStyle(.segmented)
            if scene.photoFit == "cover" {
                VStack(alignment: .leading, spacing: 8) {
                    Text("사진 위치").font(.subheadline.bold())
                    HStack { Text("가로"); Slider(value: sceneBinding(\.positionX, scene), in: 0...1) }
                    HStack { Text("세로"); Slider(value: sceneBinding(\.positionY, scene), in: 0...1) }
                    Button("사진 중앙으로") { project.scenes[selected].positionX = 0.5; project.scenes[selected].positionY = 0.5; changed() }.font(.caption)
                }
            }
        }
    }

    private var subtitlePanel: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let scene {
                HStack { Text("장면 \(selected + 1) 자막").font(.headline); Spacer(); Text("\(scene.narration.count)/160").font(.caption).foregroundStyle(.secondary) }
                TextField("이 순간을 한 문장으로", text: Binding(get: { scene.narration }, set: { value in
                    guard let index = project.scenes.firstIndex(where: { $0.id == scene.id }) else { return }
                    project.scenes[index].narration = String(value.prefix(160)); changed()
                }), axis: .vertical).lineLimit(2...4).textFieldStyle(.roundedBorder)
            }
            Text("모든 장면의 글씨").font(.subheadline.bold())
            Picker("폰트", selection: Binding(get: { project.fontAssetID.isEmpty ? "" : presetFont?.id ?? "custom" }, set: selectFont)) {
                Text("기본 한글 폰트").tag("")
                ForEach(store.bundledFonts) { Text($0.name).tag($0.id) }
                if !project.fontAssetID.isEmpty && presetFont == nil { Text("내 폰트 · \(project.fontName)").tag("custom") }
            }
            Text("오늘도 신나는 하루!").font(.custom(VideoRenderer.font(project, assets: store.assets, size: 24).fontName, size: 24)).padding(12).frame(maxWidth: .infinity, alignment: .leading).background(.background, in: RoundedRectangle(cornerRadius: 10))
            HStack { Text("크기 \(Int(project.effectiveSubtitleSize))px").font(.subheadline); Slider(value: Binding(get: { project.effectiveSubtitleSize }, set: { project.subtitleSize = $0; changed() }), in: 24...96, step: 2) }
            Picker("자막 모양", selection: binding(\.subtitleStyle)) { Text("반투명 박스").tag("box"); Text("심플 텍스트").tag("clean") }.pickerStyle(.segmented)
            HStack {
                Button("하단 배치") { project.subtitleX = 0.5; project.subtitleY = 0.76; changed() }
                Button("가운데 배치") { project.subtitleX = 0.5; project.subtitleY = 0.5; changed() }
            }.buttonStyle(.bordered)
            Text("일시정지 후 미리보기의 자막을 손가락으로 옮길 수 있어요.").font(.caption).foregroundStyle(.secondary)
            Button { importingFont = true } label: { Label("내 TTF·OTF 폰트 첨부", systemImage: "square.and.arrow.down") }.buttonStyle(.bordered)
        }
    }

    private var effectsPanel: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("사진 움직임").font(.headline)
            ForEach([("still", "정지", "pause"), ("zoom", "서서히 확대", "plus.magnifyingglass"), ("zoom-out", "서서히 축소", "minus.magnifyingglass"), ("pan-left", "왼쪽으로 이동", "arrow.left"), ("pan-right", "오른쪽으로 이동", "arrow.right")], id: \.0) { value, title, icon in
                selectionRow(title, icon: icon, selected: project.effectiveMotion == value) { project.motion = value; changed() }
            }
            Text("장면 전환").font(.headline)
            Picker("장면 전환", selection: Binding(get: { project.effectiveTransition }, set: { project.transition = $0; changed() })) { Text("바로 전환").tag("cut"); Text("어둡게 페이드").tag("fade") }.pickerStyle(.segmented)
            Button { togglePreview() } label: { Label(previewPlaying ? "미리보기 일시정지" : "움직임 미리보기", systemImage: previewPlaying ? "pause.fill" : "play.fill") }.buttonStyle(.bordered)
            Text("움직임과 전환은 모든 장면에 적용됩니다.").font(.caption).foregroundStyle(.secondary)
        }
    }

    private var musicPanel: some View {
        VStack(alignment: .leading, spacing: 15) {
            selectionRow("음악 없이", icon: "speaker.slash", selected: project.musicID.isEmpty && project.musicAssetID.isEmpty) { project.musicID = ""; project.musicAssetID = ""; project.musicName = ""; changed() }
            ForEach([("slow-morning", "Slow Morning", "차분한 일상 · 카페"), ("little-weekend", "Little Weekend", "밝은 여행 · 음식"), ("after-hours", "After Hours", "잔잔한 기록 · 산책")], id: \.0) { id, title, note in
                selectionRow(title + " · " + note, icon: "music.note", selected: project.musicID == id && project.musicAssetID.isEmpty) { project.musicID = id; project.musicAssetID = ""; project.musicName = ""; changed() }
            }
            if !project.musicAssetID.isEmpty { Label(project.musicName, systemImage: "checkmark.circle.fill").font(.subheadline).foregroundStyle(.indigo) }
            HStack {
                Button { importingMusic = true } label: { Label("내 음악 첨부", systemImage: "square.and.arrow.down") }
                Spacer()
                Button {
                    if auditioning { previewAudio.stop(); auditioning = false }
                    else { do { try previewAudio.play(project, assets: store.assets, time: previewTime); auditioning = true } catch { self.error = error.localizedDescription } }
                } label: { Label(auditioning ? "듣기 중단" : "미리 듣기", systemImage: auditioning ? "stop.fill" : "play.fill") }.disabled(VideoRenderer.musicURL(project, assets: store.assets) == nil)
            }.buttonStyle(.bordered)
            HStack { Text("음량 \(Int(project.musicVolume * 100))%"); Slider(value: binding(\.musicVolume), in: 0...1) }.font(.subheadline)
            VStack(alignment: .leading, spacing: 8) {
                Text("음악 시작 구간 · \(project.effectiveMusicOffset, specifier: "%.1f")초").font(.subheadline)
                Slider(value: Binding(get: { project.effectiveMusicOffset }, set: { project.musicOffset = $0; changed() }), in: 0...30, step: 0.5)
            }
            Text("음악은 영상 길이에 맞춰 반복하고 시작과 끝을 부드럽게 처리해요. 내 음악은 MP3·M4A·WAV 파일을 사용할 수 있어요.").font(.caption).foregroundStyle(.secondary)
        }
    }

    private var aiPanel: some View {
        VStack(alignment: .leading, spacing: 16) {
            Picker("분위기", selection: Binding(get: { project.effectiveMood }, set: { project.mood = $0; changed() })) {
                ForEach(["일상", "여행", "카페", "음식", "운동", "산책"], id: \.self) { Text($0).tag($0) }
            }
            TextField("사진 설명", text: Binding(get: { project.effectiveDescription }, set: { project.description = String($0.prefix(2000)); changed() }), axis: .vertical).lineLimit(3...5).textFieldStyle(.roundedBorder)
            Picker("자막 말투", selection: Binding(get: { project.effectiveTone }, set: { project.tone = $0; changed() })) {
                ForEach(["담백하고 자연스럽게", "따뜻하고 감성적으로", "가볍고 유쾌하게"], id: \.self) { Text($0).tag($0) }
            }
            if ai.apiKey.isEmpty {
                Text("직접 자막은 무료로 쓸 수 있어요. 사진을 보고 자막을 제안받으려면 AI를 연결하세요.").font(.subheadline).foregroundStyle(.secondary)
            } else {
                Text("\(ai.provider) · \(ai.model)").font(.caption).foregroundStyle(.secondary)
                Text("아래 버튼을 누르면 축소한 사진 \(project.scenes.count)장과 설명을 선택한 AI 서비스로 전송합니다. 사진 입력을 지원하는 모델이 필요하며 API 요금이 발생할 수 있어요.").font(.caption).foregroundStyle(.secondary)
                Button { Task { await generate() } } label: { Label(generating ? "AI 자막 제안 중…" : "사진 전송 · AI 자막 제안받기", systemImage: "sparkles").frame(maxWidth: .infinity) }.buttonStyle(.borderedProminent).disabled(locked || project.scenes.isEmpty)
            }
            Button { showInspectorAISettings = true } label: { Label(ai.apiKey.isEmpty ? "AI 연결하기" : "AI 연결 변경", systemImage: "gearshape") }.buttonStyle(.bordered)
        }
    }

    private var exportSheet: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text("\(project.scenes.count)장의 순간을 \(project.duration, specifier: "%.1f")초 영상으로").font(.headline)
                    if rendering { ProgressView(value: progress); Text(message).font(.caption); Button("제작 중단") { renderTask?.cancel() } }
                    if let resultURL {
                        StudioVideoPlayer(url: resultURL).frame(height: 320).clipShape(RoundedRectangle(cornerRadius: 14))
                        ShareLink(item: resultURL) { Label("MP4 저장 · 공유", systemImage: "square.and.arrow.up").frame(maxWidth: .infinity) }.buttonStyle(.borderedProminent)
                    }
                    Button { renderTask = Task { await render() } } label: {
                        Label(resultURL == nil ? "MP4 영상 만들기" : "MP4 다시 만들기", systemImage: "film").frame(maxWidth: .infinity).padding(.vertical, 8)
                    }.buttonStyle(.borderedProminent).disabled(!project.canRender || locked)
                    if project.duration > 180 { Text("장면 시간을 줄여 180초 이하로 맞춰주세요.").font(.caption).foregroundStyle(.red) }
                    Text("게시 문안").font(.headline)
                    TextField("본문과 해시태그", text: binding(\.caption), axis: .vertical).lineLimit(4...8).textFieldStyle(.roundedBorder).disabled(locked)
                    if !project.caption.isEmpty { ShareLink(item: project.caption) { Label("게시 문안 공유", systemImage: "doc.on.doc") } }
                    Divider()
                    Button { do { transferURL = try store.exportTransfer(project) } catch { self.error = error.localizedDescription } } label: { Label("Mac에서 이어서 편집하기", systemImage: "desktopcomputer") }.buttonStyle(.bordered).disabled(locked)
                    if let transferURL { ShareLink(item: transferURL) { Label(".studio 프로젝트 보내기", systemImage: "square.and.arrow.up") } }
                }.padding(20)
            }.navigationTitle("완성 · 저장").navigationBarTitleDisplayMode(.inline).toolbar { Button("완료") { showExport = false } }
                .alert("작업을 완료하지 못했습니다", isPresented: Binding(get: { !error.isEmpty }, set: { if !$0 { error = "" } })) { Button("확인") { error = "" } } message: { Text(error) }
        }
    }

    private func selectionRow(_ title: String, icon: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 12) { Image(systemName: icon).frame(width: 25); Text(title).font(.subheadline); Spacer(); if selected { Image(systemName: "checkmark.circle.fill") } }
                .foregroundStyle(selected ? .indigo : .primary).padding(14).background(selected ? Color.indigo.opacity(0.09) : Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12))
        }.buttonStyle(.plain)
    }
    private var presetFont: BundledStudioFont? { store.bundledFonts.first { project.fontAssetID == $0.id + "." + URL(fileURLWithPath: $0.filename).pathExtension } }
    private func selectFont(_ id: String) {
        do {
            if id.isEmpty { project.fontAssetID = ""; project.fontName = "" }
            else if let font = store.bundledFonts.first(where: { $0.id == id }) { project.fontAssetID = try store.importBundledFont(font); project.fontName = font.name }
            else { return }
            changed()
        } catch { self.error = error.localizedDescription }
    }
    private func binding<Value>(_ keyPath: WritableKeyPath<StudioProject, Value>) -> Binding<Value> { Binding(get: { project[keyPath: keyPath] }, set: { project[keyPath: keyPath] = $0; changed() }) }
    private func sceneBinding<Value>(_ keyPath: WritableKeyPath<StudioScene, Value>, _ original: StudioScene) -> Binding<Value> {
        Binding(get: { project.scenes.first(where: { $0.id == original.id })?[keyPath: keyPath] ?? original[keyPath: keyPath] }, set: { value in
            guard let index = project.scenes.firstIndex(where: { $0.id == original.id }) else { return }
            project.scenes[index][keyPath: keyPath] = value; changed()
        })
    }
    private func changed() {
        previewTime = min(previewTime, project.duration); previewAnchor = previewTime; previewEpoch = Date()
        project.lastVideo = ""; resultURL = nil; transferURL = nil
        store.save(project)
        if previewPlaying || auditioning { do { try previewAudio.play(project, assets: store.assets, time: previewTime) } catch { self.error = error.localizedDescription } }
    }
    private func seek(_ value: Double) { previewTime = min(project.duration, max(0, value)); previewAnchor = previewTime; previewEpoch = Date(); if previewPlaying { do { try previewAudio.play(project, assets: store.assets, time: previewTime) } catch { self.error = error.localizedDescription } } }
    private func seekToSelected() { pausePreview(); seek(project.scenes.prefix(selected).reduce(0) { $0 + $1.duration }) }
    private func pausePreview() { previewPlaying = false; auditioning = false; previewAudio.stop() }
    private func togglePreview() {
        if previewPlaying { pausePreview(); return }
        if previewTime >= project.duration { previewTime = 0 }
        previewAnchor = previewTime; previewEpoch = Date(); previewPlaying = true; auditioning = false
        do { try previewAudio.play(project, assets: store.assets, time: previewTime) } catch { self.error = error.localizedDescription }
    }
    private func moveScene(_ index: Int, _ offset: Int) {
        let target = index+offset
        guard project.scenes.indices.contains(index), project.scenes.indices.contains(target) else { return }
        project.scenes.swapAt(index, target); selected = target; changed(); seekToSelected()
    }
    private func addPhotos(_ items: [PhotosPickerItem]) async {
        guard !items.isEmpty else { return }; pausePreview(); importing = true; defer { importing = false; photos = [] }
        for item in items.prefix(max(0, 10-project.scenes.count)) {
            do {
                guard let data = try await item.loadTransferable(type: Data.self) else { continue }
                project.scenes.append(StudioScene(title: "사진 \(project.scenes.count+1)", photoID: try store.importPhoto(data))); selected = project.scenes.count-1; changed()
            } catch { self.error = error.localizedDescription }
        }
    }
    private func replacePhoto(_ item: PhotosPickerItem) async {
        guard let original = scene else { return }; pausePreview(); importing = true; defer { importing = false; replacement = nil }
        do {
            guard let data = try await item.loadTransferable(type: Data.self), let index = project.scenes.firstIndex(where: { $0.id == original.id }) else { return }
            project.scenes[index].photoID = try store.importPhoto(data); changed()
        } catch { self.error = error.localizedDescription }
    }
    private func requestAI() { pausePreview(); tool = .ai }
    private func generate() async {
        generating = true; message = "사진에 맞는 자막을 제안하는 중…"; defer { generating = false }
        do {
            let result = try await AIService.suggest(project: project, provider: ai.provider, model: ai.model, endpoint: ai.endpoint, key: ai.apiKey, assets: store.assets)
            for index in project.scenes.indices { project.scenes[index].title = result.scenes[index].title; project.scenes[index].narration = result.scenes[index].narration }
            project.caption = result.caption; changed(); tool = .subtitle
        } catch { self.error = error.localizedDescription }
    }
    private func render() async {
        pausePreview(); rendering = true; progress = 0; message = "영상을 준비하는 중…"; defer { rendering = false }
        do {
            let url = try await VideoRenderer.render(project, assets: store.assets, exports: store.exports) { value, status in Task { @MainActor in progress = value; message = status } }
            resultURL = url; project.lastVideo = url.lastPathComponent; project.renderLayoutVersion = 3; store.save(project)
        } catch is CancellationError { message = "영상 제작을 중단했습니다." }
        catch { self.error = error.localizedDescription }
    }
}

private struct SceneReorderDelegate: DropDelegate {
    @Binding var project: StudioProject
    @Binding var selected: Int
    @Binding var draggedID: String?
    let targetID: String
    let onChange: () -> Void
    func dropEntered(info: DropInfo) {
        guard let draggedID, draggedID != targetID, let from = project.scenes.firstIndex(where: { $0.id == draggedID }), let to = project.scenes.firstIndex(where: { $0.id == targetID }) else { return }
        let selectedID = project.scenes.indices.contains(selected) ? project.scenes[selected].id : ""
        project.scenes.move(fromOffsets: IndexSet(integer: from), toOffset: from < to ? to+1 : to)
        selected = project.scenes.firstIndex(where: { $0.id == selectedID }) ?? 0; onChange()
    }
    func dropUpdated(info: DropInfo) -> DropProposal? { DropProposal(operation: .move) }
    func performDrop(info: DropInfo) -> Bool { draggedID = nil; return true }
}

@MainActor private final class PreviewAudio: ObservableObject {
    private var player: AVAudioPlayer?
    private var url: URL?
    func play(_ project: StudioProject, assets: URL, time: Double) throws {
        guard let source = VideoRenderer.musicURL(project, assets: assets) else { stop(); return }
        if url != source { player = try AVAudioPlayer(contentsOf: source); url = source; player?.numberOfLoops = -1; player?.prepareToPlay() }
        let session = AVAudioSession.sharedInstance(); try session.setCategory(.playback, mode: .moviePlayback); try session.setActive(true)
        guard let player, player.duration > 0 else { return }
        player.currentTime = (project.effectiveMusicOffset+time).truncatingRemainder(dividingBy: player.duration)
        player.volume = Float(project.musicVolume); player.play()
    }
    func stop() { player?.pause() }
}

private struct StudioVideoPlayer: View {
    let url: URL
    @State private var player = AVPlayer()
    var body: some View {
        VideoPlayer(player: player).onAppear {
            try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .moviePlayback)
            try? AVAudioSession.sharedInstance().setActive(true)
            player.replaceCurrentItem(with: AVPlayerItem(url: url)); player.isMuted = false
        }.onDisappear { player.pause() }
    }
}
