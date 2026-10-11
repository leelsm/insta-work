import Foundation

@main struct NewsChecks {
    static func main() async throws {
        let fixture = """
        <div class="rankingnews_box"><strong class="rankingnews_name">연합뉴스</strong><ul class="rankingnews_list">
        <li><em class="list_ranking_num">1위</em><a class="list_title" href="https://n.news.naver.com/article/001/123?ntype=RANKING">테스트 &amp; <b>뉴스</b></a></li>
        <li><em class="list_ranking_num">2</em><a class="list_title" href="https://evil.example/article/001/124">잘못된 주소</a></li>
        <li><em class="list_ranking_num">3</em><a class="list_title" href="https://n.news.naver.com/article/001/123">중복</a></li>
        </ul></div>
        """
        let rows = try NewsService.parseRanking(fixture)
        precondition(rows.count == 1 && rows[0].rank == 1 && rows[0].title == "테스트 & 뉴스")
        precondition(rows[0].url == "https://n.news.naver.com/article/001/123")
        precondition(NewsHTML.clean("&lt;b&gt; &quot;글&quot; &#xD55C; &#44544;") == "<b> \"글\" 한 글")
        let article = "<script>숨길 내용</script><div id='dic_area'>" + String(repeating: "확인된 기사 내용입니다. ", count: 12) + "</div><footer>제외할 내용</footer>"
        let summary = try NewsService.parseArticle(article)
        precondition(!summary.contains("숨길") && !summary.contains("제외할"))
        let project = try NewsDraft.make(item: rows[0], summary: summary)
        precondition(project.scenes.count == 5 && project.sources[0].url == rows[0].url)
        precondition(project.scenes.dropFirst().map(\.body).joined() == summary)
        precondition(project.scenes.allSatisfy { $0.sourceIDs == [0] })
        do { _ = try NewsDraft.make(item: rows[0], summary: "  "); fatalError("Blank material accepted") } catch {}
        do { _ = try NewsService.parseRanking("<html>unavailable</html>"); fatalError("Broken ranking accepted") } catch {}
        if CommandLine.arguments.count > 1 && CommandLine.arguments[1] != "--network" {
            let html = try String(contentsOfFile: CommandLine.arguments[1], encoding: .utf8)
            let live = try NewsService.parseRanking(html)
            precondition(!live.isEmpty && live.count <= 25)
            print("Live ranking parsed: \(live.count) items from \(Set(live.map(\.publisher)).count) publishers")
        }
        if CommandLine.arguments.contains("--network") {
            let rows = try await NewsService.popular(date: Date())
            let summary = try await NewsService.summary(rows[0])
            let project = try NewsDraft.make(item: rows[0], summary: summary)
            precondition(project.scenes.count == 5 && summary.count >= 100)
            print("Live request → article summary → five cards passed (\(rows.count) news items, \(summary.count) summary characters)")
        }
        print("News parser and draft checks passed")
    }
}
