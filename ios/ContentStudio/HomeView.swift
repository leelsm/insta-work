import SwiftUI
import PhotosUI
import UniformTypeIdentifiers

private enum HomeRoute: Hashable {
    case savedProject(String)
    case newProject
}

struct HomeView: View {
    @ObservedObject var store: StudioStore
    @ObservedObject var ai: AISettings
    @State private var showSettings = false
    @State private var showImporter = false
    @State private var showLegacy = false
    @State private var legacyURL: URL?
    @State private var error = ""
    @State private var path: [HomeRoute] = []
    @State private var deleting: StudioProject?
    @State private var startAIProjectID: String?

    private var dailyProjects: [StudioProject] { store.projects.filter(\.isDaily) }

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("사진으로 남긴 하루,\n영상으로 이어봐요.").font(.system(size: 30, weight: .bold))
                        Text("사진을 고르고, 자막과 음악을 더하면 완성.")
                            .font(.subheadline).foregroundStyle(.secondary)
                    }.padding(.top, 12)
                    Button { path.append(.newProject) } label: {
                        HStack(spacing: 16) {
                            Image(systemName: "photo.stack.fill").font(.system(size: 30)).frame(width: 58, height: 64)
                            VStack(alignment: .leading, spacing: 7) {
                                Text("새 일상 영상").font(.title3.bold())
                                Text("사진 1~10장 · 자막 · 음악").font(.subheadline).opacity(0.88)
                            }
                            Spacer()
                            Image(systemName: "arrow.right")
                        }.foregroundStyle(.white).padding(22)
                            .background(LinearGradient(colors: [.indigo, Color(red: 0.44, green: 0.32, blue: 0.75)], startPoint: .topLeading, endPoint: .bottomTrailing), in: RoundedRectangle(cornerRadius: 22))
                    }.buttonStyle(.plain).accessibilityIdentifier("daily-create")
                    HStack {
                        Label("내 영상", systemImage: "film.stack").font(.title3.bold())
                        Spacer()
                        Text("\(dailyProjects.count)개").font(.caption).foregroundStyle(.secondary)
                    }
                    if dailyProjects.isEmpty {
                        VStack(spacing: 12) {
                            Image(systemName: "photo.on.rectangle.angled").font(.largeTitle).foregroundStyle(.indigo)
                            Text("첫 번째 일상을 담아보세요").font(.headline)
                            Text("직접 자막을 쓰면 AI 연결 없이 만들 수 있어요.").font(.caption).foregroundStyle(.secondary)
                        }.frame(maxWidth: .infinity).padding(.vertical, 30)
                            .background(.background, in: RoundedRectangle(cornerRadius: 18))
                    }
                    ForEach(dailyProjects) { project in
                        HStack(spacing: 14) {
                            NavigationLink(value: HomeRoute.savedProject(project.id)) {
                                HStack(spacing: 14) {
                                    thumbnail(project).frame(width: 64, height: 82).clipShape(RoundedRectangle(cornerRadius: 10))
                                    VStack(alignment: .leading, spacing: 7) {
                                        Text(project.title).font(.headline).lineLimit(1)
                                        Text("\(project.scenes.count)장 · \(project.duration, specifier: "%.1f")초")
                                            .font(.caption).foregroundStyle(.secondary)
                                        Text(project.lastVideo.isEmpty ? "이어서 편집" : (project.renderLayoutVersion ?? 0) >= VideoRenderer.layoutVersion ? "완성 영상 있음" : "영상 다시 만들기")
                                            .font(.caption2.weight(.medium)).foregroundStyle(.indigo)
                                    }
                                    Spacer(minLength: 0)
                                }.contentShape(Rectangle())
                            }.buttonStyle(.plain)
                            Menu {
                                Button("삭제", role: .destructive) { deleting = project }
                            } label: { Image(systemName: "ellipsis").frame(width: 44, height: 44) }
                                .accessibilityLabel("\(project.title) 메뉴")
                        }.padding(14).background(.background, in: RoundedRectangle(cornerRadius: 18))
                    }
                    Button { showImporter = true } label: {
                        Label("PC 버전에서 가져오기", systemImage: "square.and.arrow.down")
                            .font(.subheadline).frame(maxWidth: .infinity).padding(.vertical, 8)
                    }.buttonStyle(.bordered)
                    Text("PC 버전에서 저장한 .studio 파일로 일상 영상의 사진·자막·음악·편집 설정을 가져와요.")
                        .font(.caption).foregroundStyle(.secondary)
                }.padding(20)
            }
            .background(Color(uiColor: .systemGroupedBackground))
            .navigationTitle("Content Studio").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                Menu {
                    Button("AI 자막 연결", systemImage: "sparkles") { showSettings = true }
                    Button("PC 버전에서 가져오기", systemImage: "square.and.arrow.down") { showImporter = true }
                    if store.projects.contains(where: { !$0.isDaily }) {
                        Button("이전 카드 프로젝트를 PC 버전으로 보내기", systemImage: "desktopcomputer") { showLegacy = true }
                    }
                } label: { Image(systemName: "gearshape").frame(width: 44, height: 44) }.accessibilityLabel("앱 설정")
            }
            .navigationDestination(for: HomeRoute.self) { route in
                switch route {
                case .savedProject(let id):
                    if let project = dailyProjects.first(where: { $0.id == id }) { EditorView(initial: project, store: store, ai: ai, startWithAI: project.id == startAIProjectID) }
                    else { ContentUnavailableView("영상을 찾을 수 없습니다", systemImage: "film") }
                case .newProject:
                    DailyCreateView(store: store, ai: ai) { project, withAI in
                        startAIProjectID = withAI ? project.id : nil
                        store.save(project)
                        path.removeLast()
                        path.append(.savedProject(project.id))
                    }
                }
            }
            .onChange(of: path) { _, value in if value.isEmpty { startAIProjectID = nil } }
            .alert("프로젝트를 삭제할까요?", isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } })) {
                Button("취소", role: .cancel) { deleting = nil }
                Button("삭제", role: .destructive) { if let project = deleting { store.delete(project) }; deleting = nil }
            } message: { Text("‘\(deleting?.title ?? "")’ 프로젝트를 삭제합니다.") }
            .sheet(isPresented: $showSettings) { AISettingsView(settings: ai) }
            .sheet(isPresented: $showLegacy) {
                NavigationStack {
                    List {
                        Section { Text("이전 카드 프로젝트는 파일로 저장해 PC 버전 Content Studio에서 이어서 편집하세요.").font(.subheadline) }
                        ForEach(store.projects.filter { !$0.isDaily }) { project in
                            Button(project.title) { do { legacyURL = try store.exportTransfer(project) } catch { self.error = error.localizedDescription } }
                        }
                        if let legacyURL { ShareLink(item: legacyURL) { Label("PC 버전으로 프로젝트 보내기", systemImage: "square.and.arrow.up") } }
                    }.navigationTitle("이전 프로젝트").toolbar { Button("완료") { showLegacy = false } }
                }
            }
            .fileImporter(isPresented: $showImporter, allowedContentTypes: [.item], allowsMultipleSelection: false) { result in
                do {
                    guard let url = try result.get().first else { return }
                    path.append(.savedProject(try store.importTransfer(url).id))
                } catch { self.error = error.localizedDescription }
            }
            .alert("프로젝트를 열지 못했습니다", isPresented: Binding(get: { !error.isEmpty }, set: { if !$0 { error = "" } })) {
                Button("확인") { error = "" }
            } message: { Text(error) }
            #if DEBUG
            .onAppear {
                if let project = MobileVerification.previewProject(store: store) {
                    if ProcessInfo.processInfo.arguments.contains("--preview-daily-create") { path = [.newProject] }
                    else if (ProcessInfo.processInfo.arguments.contains("--preview-daily-editor") || ProcessInfo.processInfo.arguments.contains("--verify-export-ui")) { path = [.savedProject(project.id)] }
                }
            }
            #endif
        }
    }

    @ViewBuilder private func thumbnail(_ project: StudioProject) -> some View {
        if let scene = project.thumbnailScene { StudioPhotoThumbnail(url: store.assets.appendingPathComponent(scene.photoID), width: 64, height: 82).equatable() }
        else { Color.indigo.opacity(0.1).overlay(Image(systemName: "photo").foregroundStyle(.indigo)) }
    }
}

private struct DailyCreateView: View {
    @ObservedObject var store: StudioStore
    @ObservedObject var ai: AISettings
    let onCreated: (StudioProject, Bool) -> Void
    @State private var project = StudioProject()
    @State private var photos: [PhotosPickerItem] = []
    @State private var step = 1
    @State private var importing = false
    @State private var error = ""
    private let moods = MusicLibrary.moods

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                HStack(spacing: 10) {
                    stepLabel("1 사진 선택", active: step == 1)
                    Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary)
                    stepLabel("2 분위기 · 자막", active: step == 2)
                }
                if step == 1 {
                    Text("영상으로 이어갈\n사진을 골라주세요.").font(.title2.bold())
                    PhotosPicker(selection: $photos, maxSelectionCount: max(1, 10-project.scenes.count), selectionBehavior: .ordered, matching: .images) {
                        VStack(spacing: 14) {
                            Image(systemName: "photo.badge.plus").font(.system(size: 32))
                            Text(project.scenes.isEmpty ? "사진 선택하기" : "사진 더 추가하기").font(.headline)
                            Text("\(project.scenes.count)/10장 · 큰 사진도 자동 축소").font(.caption)
                        }.frame(maxWidth: .infinity).padding(28)
                            .background(.indigo.opacity(0.08), in: RoundedRectangle(cornerRadius: 20))
                    }.disabled(importing || project.scenes.count >= 10)
                    if importing { ProgressView("사진을 준비하고 있어요…") }
                    LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                        ForEach(Array(project.scenes.enumerated()), id: \.element.id) { index, scene in
                            VStack(spacing: 0) {
                                if let image = store.image(scene.photoID) { Image(uiImage: image).resizable().scaledToFill().frame(height: 145).clipped() }
                                HStack {
                                    Text("\(index+1)").font(.caption.bold())
                                    Spacer()
                                    Button { swap(index, -1) } label: { Image(systemName: "chevron.left").frame(width: 32, height: 38) }.disabled(index == 0)
                                    Button { swap(index, 1) } label: { Image(systemName: "chevron.right").frame(width: 32, height: 38) }.disabled(index == project.scenes.count-1)
                                    Button(role: .destructive) { project.scenes.remove(at: index) } label: { Image(systemName: "trash").frame(width: 32, height: 38) }
                                }.padding(.horizontal, 8)
                            }.background(.background, in: RoundedRectangle(cornerRadius: 14)).clipShape(RoundedRectangle(cornerRadius: 14))
                        }
                    }
                    if !project.scenes.isEmpty { Text("화살표로 순서를 바꾸세요. 사진과 자막이 함께 이동해요.").font(.caption).foregroundStyle(.secondary) }
                } else {
                    Text("어떤 하루였나요?").font(.title2.bold())
                    Text("\(project.scenes.count)장을 선택했어요. 이 내용은 AI 자막을 제안할 때도 참고해요.").font(.subheadline).foregroundStyle(.secondary)
                    GroupBox {
                        VStack(alignment: .leading, spacing: 16) {
                            TextField("영상 제목", text: $project.title).textFieldStyle(.roundedBorder)
                            Picker("분위기", selection: Binding(get: { project.effectiveMood }, set: { project.mood = $0 })) { ForEach(moods, id: \.self) { Text($0).tag($0) } }
                            Text("한 줄 설명").font(.subheadline.bold())
                            TextField("예: 친구와 카페에서 보낸 느긋한 주말", text: Binding(get: { project.effectiveDescription }, set: { project.description = String($0.prefix(2000)) }), axis: .vertical).lineLimit(3...5)
                            Picker("자막 말투", selection: Binding(get: { project.effectiveTone }, set: { project.tone = $0 })) {
                                ForEach(["담백하고 자연스럽게", "따뜻하고 감성적으로", "가볍고 유쾌하게"], id: \.self) { Text($0).tag($0) }
                            }
                        }
                    }
                    Text("직접 자막을 쓰거나 편집 화면에서 AI 제안을 받을 수 있어요.").font(.caption).foregroundStyle(.secondary)
                    Button("사진 선택으로 돌아가기") { step = 1 }.font(.subheadline)
                }
            }.padding(20)
        }
        .background(Color(uiColor: .systemGroupedBackground))
        .navigationTitle("새 일상 영상").navigationBarTitleDisplayMode(.inline)
        .safeAreaInset(edge: .bottom) {
            VStack(spacing: 10) {
                if step == 1 {
                    Button { step = 2 } label: { Text("사진 \(project.scenes.count)장 선택 · 다음").font(.headline).frame(maxWidth: .infinity).padding(.vertical, 12) }.buttonStyle(.borderedProminent)
                } else {
                    Button { finish(false) } label: { Text("직접 자막 쓰기").font(.headline).frame(maxWidth: .infinity).padding(.vertical, 10) }.buttonStyle(.borderedProminent)
                    Button { finish(true) } label: { Label("AI 자막으로 시작하기", systemImage: "sparkles").frame(maxWidth: .infinity).padding(.vertical, 4) }.buttonStyle(.bordered)
                }
            }.disabled(project.scenes.isEmpty || importing).padding(16).background(.bar)
        }
        .onAppear {
            project.kind = "daily"; if project.title == "새 영상" { project.title = "나의 일상 영상" }
            #if DEBUG
            if ProcessInfo.processInfo.arguments.contains("--preview-daily-create"), let preview = MobileVerification.previewProject(store: store) { project = preview }
            #endif
        }
        .onChange(of: photos) { _, items in Task { await addPhotos(items) } }
        .alert("사진을 추가하지 못했습니다", isPresented: Binding(get: { !error.isEmpty }, set: { if !$0 { error = "" } })) { Button("확인") { error = "" } } message: { Text(error) }
    }

    private func finish(_ withAI: Bool) {
        project.musicID = MusicLibrary.recommended(project.effectiveMood).first?.id ?? "slow-morning"
        if project.title.trimmingCharacters(in: .whitespaces).isEmpty { project.title = "\(project.effectiveMood)의 순간" }
        onCreated(project, withAI)
    }

    private func stepLabel(_ title: String, active: Bool) -> some View { Text(title).font(.caption.bold()).foregroundStyle(active ? .indigo : .secondary).padding(.vertical, 9).padding(.horizontal, 12).background(active ? Color.indigo.opacity(0.1) : .clear, in: Capsule()) }
    private func swap(_ index: Int, _ offset: Int) { let next = index+offset; if project.scenes.indices.contains(next) { project.scenes.swapAt(index, next) } }
    private func addPhotos(_ items: [PhotosPickerItem]) async {
        importing = true; defer { importing = false; photos = [] }
        for item in items.prefix(10-project.scenes.count) {
            do {
                guard let data = try await item.loadTransferable(type: Data.self) else { continue }
                let id = try store.importPhoto(data)
                project.scenes.append(StudioScene(title: "사진 \(project.scenes.count+1)", photoID: id))
            } catch { self.error = error.localizedDescription }
        }
    }
}
struct AISettingsView: View {
    @ObservedObject var settings: AISettings
    @Environment(\.dismiss) private var dismiss
    private let providers = [("openai", "ChatGPT"), ("anthropic", "Claude"),
                             ("freellmapi", "FreeLLMAPI 서버"), ("opencode", "OpenCode 서버")]

    var body: some View {
        NavigationStack {
            Form {
                Section("AI 서비스") {
                    Picker("제공자", selection: Binding(get: { settings.provider }, set: { settings.select($0) })) {
                        ForEach(providers.indices, id: \.self) { index in
                            Text(providers[index].1).tag(providers[index].0)
                        }
                    }
                    TextField("모델 이름", text: $settings.model).textInputAutocapitalization(.never)
                    SecureField("API 키", text: $settings.apiKey)
                    if settings.provider == "freellmapi" || settings.provider == "opencode" {
                        TextField("HTTPS 서버 주소 (…/v1)", text: $settings.endpoint)
                            .textInputAutocapitalization(.never).keyboardType(.URL)
                    }
                }
                Section {
                    Text("API 키는 이 iPhone의 Keychain에 저장됩니다. Mac의 로컬 OpenCode·FreeLLMAPI는 iPhone에서 실행되지 않으므로, 두 서버는 iPhone이 접속할 수 있는 HTTPS 주소가 필요합니다.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }
            .navigationTitle("AI 자막 연결")
            .toolbar { Button("완료") { dismiss() } }
        }
    }
}
