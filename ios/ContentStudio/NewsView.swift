import SwiftUI

struct NewsView: View {
    @ObservedObject var store: StudioStore
    @ObservedObject var ai: AISettings
    var open: (StudioProject) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var mode = "popular"
    @State private var date = Date()
    @State private var query = ""
    @State private var items: [NewsItem] = []
    @State private var selected: NewsItem?
    @State private var material = ""
    @State private var busy = ""
    @State private var error = ""
    @State private var searched = false
    @State private var showSettings = false
    @State private var loadedDate: Date?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    Text("뉴스를 골라 카드뉴스로").font(.title2.bold())
                    Text("1. 기사 선택 → 2. 요약 확인 → 3. 카드 편집 → 영상 제작")
                        .font(.subheadline).foregroundStyle(.secondary)
                    if selected == nil { searchPanel }
                    if !busy.isEmpty {
                        HStack { ProgressView(); Text(busy).font(.subheadline) }
                            .padding().frame(maxWidth: .infinity, alignment: .leading)
                            .background(.green.opacity(0.15), in: RoundedRectangle(cornerRadius: 12))
                    }
                    if !error.isEmpty { Text(error).foregroundStyle(.red).font(.subheadline) }
                    if let article = selected { review(article) }
                    else {
                        ForEach(items) { item in
                            VStack(alignment: .leading, spacing: 10) {
                                Text(item.rank > 0 ? "\(item.publisher) · \(item.rank)위" : "네이버 검색 결과")
                                    .font(.caption).foregroundStyle(.secondary)
                                Text(item.title).font(.headline)
                                if !item.summary.isEmpty { Text(item.summary).font(.subheadline).lineLimit(3) }
                                Button("기사 요약 확인") { Task { await select(item) } }
                                    .buttonStyle(.bordered).disabled(!busy.isEmpty)
                            }.padding().frame(maxWidth: .infinity, alignment: .leading)
                                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 14))
                        }
                        if searched && items.isEmpty && busy.isEmpty && error.isEmpty {
                            ContentUnavailableView("조회된 뉴스가 없습니다", systemImage: "newspaper", description: Text("날짜나 검색어를 바꿔 주세요."))
                        }
                    }
                }.padding(18)
            }
            .background(Color(uiColor: .systemGroupedBackground))
            .navigationTitle("네이버 카드뉴스").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("닫기") { dismiss() }.disabled(!busy.isEmpty) }
                ToolbarItem(placement: .primaryAction) { Button("연결 설정") { showSettings = true }.disabled(!busy.isEmpty) }
            }
            .interactiveDismissDisabled(!busy.isEmpty)
            .sheet(isPresented: $showSettings) { AISettingsView(settings: ai) }
        }
    }

    private var searchPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            Picker("뉴스 선택 방식", selection: $mode) {
                Text("인기뉴스").tag("popular"); Text("키워드 검색").tag("search")
            }.pickerStyle(.segmented).disabled(!busy.isEmpty)
                .onChange(of: mode) { _, _ in items = []; error = ""; searched = false; loadedDate = nil }
            if mode == "popular" {
                DatePicker("랭킹 날짜", selection: $date, in: Date().addingTimeInterval(-89 * 86400)...Date(), displayedComponents: .date)
                    .environment(\.timeZone, TimeZone(identifier: "Asia/Seoul")!)
                Text("주요 언론사 5곳의 언론사별 1~5위입니다. 네이버 API 키 없이 조회합니다.")
                    .font(.caption).foregroundStyle(.secondary)
                if let loadedDate { Text("표시 목록: \(loadedDate.formatted(date: .numeric, time: .omitted)) · 날짜 변경 후 다시 불러오세요.").font(.caption) }
            } else {
                TextField("검색어를 입력하세요", text: $query).textFieldStyle(.roundedBorder)
                Text("연결 설정의 네이버 검색 키가 필요합니다. Mac에 저장한 키는 iPhone으로 자동 복사되지 않습니다.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Button(mode == "popular" ? "인기뉴스 불러오기" : "뉴스 검색") { Task { await load() } }
                .buttonStyle(.borderedProminent).disabled(!busy.isEmpty || (mode == "search" && query.trimmingCharacters(in: .whitespaces).isEmpty))
        }
    }

    private func review(_ item: NewsItem) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            Button("← 뉴스 목록으로") { selected = nil; material = ""; error = "" }.disabled(!busy.isEmpty)
            Text(item.title).font(.title3.bold())
            if let url = URL(string: item.url) { Link("원문 확인 ↗", destination: url) }
            Text("카드에 사용할 요약 · 직접 수정 가능").font(.headline)
            TextEditor(text: $material).frame(minHeight: 220).padding(8)
                .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10)).disabled(!busy.isEmpty)
            Text("원문에서 추린 문장을 확인하고 필요한 내용만 남겨 주세요. 제목만으로 기사 내용을 만들지 않습니다.")
                .font(.caption).foregroundStyle(.secondary)
            Button("5장 카드 편집 시작") { Task { await create(useAI: false) } }
                .buttonStyle(.borderedProminent).disabled(!ready)
            Button("선택한 AI로 5장 초안 만들기") { Task { await create(useAI: true) } }
                .buttonStyle(.bordered).disabled(!ready)
            Text("AI: \(ai.provider) · \(ai.model). AI 버튼은 요약을 해당 서비스에 전송합니다. 직접 편집은 AI 키 없이 가능합니다.")
                .font(.caption).foregroundStyle(.secondary)
        }
    }
    private var ready: Bool { busy.isEmpty && !material.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
    @MainActor private func load() async {
        busy = "뉴스를 불러오는 중…"; error = ""; items = []; searched = true
        defer { busy = "" }
        do {
            if mode == "popular" { items = try await NewsService.popular(date: date); loadedDate = date }
            else { items = try await NewsService.search(query: query, provider: ai.naverProvider, clientID: ai.naverID, secret: ai.naverSecret) }
        } catch { self.error = error.localizedDescription }
    }
    @MainActor private func select(_ item: NewsItem) async {
        selected = item; material = item.summary; error = ""; busy = "기사 본문에서 요약을 준비하는 중…"
        defer { busy = "" }
        do { material = try await NewsService.summary(item) }
        catch { self.error = error.localizedDescription + (item.summary.isEmpty ? "" : " 검색 요약을 대신 표시했습니다.") }
    }
    @MainActor private func create(useAI: Bool) async {
        guard let selected else { return }
        busy = useAI ? "선택한 AI로 카드 초안을 생성하는 중…" : "카드 프로젝트를 만드는 중…"
        error = ""; defer { busy = "" }
        do {
            var project = try NewsDraft.make(item: selected, summary: material)
            if useAI {
                let result = try await AIService.suggest(project: project, provider: ai.provider, model: ai.model, endpoint: ai.endpoint, key: ai.apiKey)
                for index in project.scenes.indices {
                    project.scenes[index].title = String(result.scenes[index].title.prefix(90))
                    project.scenes[index].body = String(result.scenes[index].body.prefix(500))
                    project.scenes[index].narration = String(result.scenes[index].narration.prefix(700))
                    project.scenes[index].imageSearchQuery = result.scenes[index].imageSearchQuery
                }
                project.caption = String(result.caption.prefix(2200))
            }
            busy = "뉴스에 맞는 이미지를 자동으로 찾는 중…"
            _ = await NewsImages.attach(to: &project, store: store)
            store.save(project); open(project); dismiss()
        } catch { self.error = error.localizedDescription }
    }
}
