import Foundation
import CoreFoundation

struct NewsItem: Identifiable, Hashable {
    var title: String
    var url: String
    var publisher = "네이버 뉴스"
    var rank = 0
    var summary = ""
    var id: String { url }
}

// Small non-executing HTML reader: remote scripts are never loaded or evaluated.
final class NewsHTML {
    let tag: String
    let attributes: [String: String]
    var children: [NewsHTML] = []
    var content = ""
    init(_ tag: String = "", _ attributes: [String: String] = [:]) {
        self.tag = tag; self.attributes = attributes
    }
    var text: String {
        if tag == "#text" { return content }
        return children.map(\.text).joined(separator: " ").replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
    func find(_ predicate: (NewsHTML) -> Bool) -> [NewsHTML] {
        children.flatMap { (predicate($0) ? [$0] : []) + $0.find(predicate) }
    }
    func hasClass(_ name: String) -> Bool { (attributes["class"] ?? "").split(separator: " ").contains(Substring(name)) }
    static func clean(_ value: String) -> String { parse(value).text }
    static func decode(_ value: String) -> String {
        let pattern = try! NSRegularExpression(pattern: "&(#x[0-9a-fA-F]+|#[0-9]+|amp|lt|gt|quot|apos|nbsp);", options: .caseInsensitive)
        var result = value
        for match in pattern.matches(in: value, range: NSRange(value.startIndex..., in: value)).reversed() {
            guard let whole = Range(match.range, in: result), let keyRange = Range(match.range(at: 1), in: value) else { continue }
            let key = String(value[keyRange]).lowercased()
            let named = ["amp": "&", "lt": "<", "gt": ">", "quot": "\"", "apos": "'", "nbsp": " "]
            var replacement = named[key]
            if key.hasPrefix("#") {
                let hex = key.hasPrefix("#x")
                if let number = UInt32(key.dropFirst(hex ? 2 : 1), radix: hex ? 16 : 10), let scalar = UnicodeScalar(number) {
                    replacement = String(scalar)
                }
            }
            if let replacement { result.replaceSubrange(whole, with: replacement) }
        }
        return result
    }
    static func parse(_ input: String) -> NewsHTML {
        let markup = input.replacingOccurrences(of: "(?is)<(script|style|noscript)\\b[^>]*>.*?</\\1\\s*>", with: "", options: .regularExpression)
        let tokens = try! NSRegularExpression(pattern: "(?s)<!--.*?-->|<[^>]*>|[^<]+")
        let attrs = try! NSRegularExpression(pattern: "([\\w:-]+)\\s*=\\s*(?:\"([^\"]*)\"|'([^']*)'|([^\\s>]+))")
        let root = NewsHTML(); var stack = [root]
        let voids: Set<String> = ["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"]
        for match in tokens.matches(in: markup, range: NSRange(markup.startIndex..., in: markup)) {
            let token = (markup as NSString).substring(with: match.range)
            if token.hasPrefix("<!") || token.hasPrefix("<?") { continue }
            if token.hasPrefix("</") {
                let tag = token.dropFirst(2).prefix { $0.isLetter || $0.isNumber }.lowercased()
                if let index = stack.lastIndex(where: { $0.tag == tag }), index > 0 { stack.removeSubrange(index...) }
            } else if token.hasPrefix("<") {
                let tag = token.dropFirst().prefix { $0.isLetter || $0.isNumber }.lowercased()
                guard !tag.isEmpty else { continue }
                var attributes: [String: String] = [:]
                for attr in attrs.matches(in: token, range: NSRange(token.startIndex..., in: token)) {
                    let key = (token as NSString).substring(with: attr.range(at: 1)).lowercased()
                    for index in 2...4 where attr.range(at: index).location != NSNotFound {
                        attributes[key] = decode((token as NSString).substring(with: attr.range(at: index))); break
                    }
                }
                let node = NewsHTML(tag, attributes); stack.last!.children.append(node)
                if !voids.contains(tag), !token.hasSuffix("/>"), stack.count < 256 { stack.append(node) }
            } else {
                let node = NewsHTML("#text"); node.content = decode(token); stack.last!.children.append(node)
            }
        }
        return root
    }
}

enum NewsService {
    static func articleURL(_ value: String) -> URL? {
        guard let url = URL(string: value), url.scheme == "https", url.host == "n.news.naver.com",
              url.user == nil, url.password == nil, url.port == nil,
              url.path.range(of: "^/article/[0-9]{3}/[0-9]+$", options: .regularExpression) != nil else { return nil }
        return URL(string: "https://n.news.naver.com" + url.path)
    }
    static func parseRanking(_ markup: String) throws -> [NewsItem] {
        let tree = NewsHTML.parse(markup)
        var items: [NewsItem] = []; var seen: Set<String> = []
        for box in tree.find({ $0.hasClass("rankingnews_box") }) {
            guard let publisher = box.find({ $0.hasClass("rankingnews_name") }).first?.text,
                  let list = box.find({ $0.hasClass("rankingnews_list") }).first else { continue }
            for row in list.children where row.tag == "li" {
                guard let title = row.find({ $0.hasClass("list_title") }).first,
                      let raw = row.find({ $0.hasClass("list_ranking_num") }).first?.text,
                      let rank = Int(raw.prefix(while: { $0.isNumber })), (1...5).contains(rank),
                      let url = articleURL(title.attributes["href"] ?? ""), !title.text.isEmpty,
                      seen.insert(url.absoluteString).inserted else { continue }
                items.append(NewsItem(title: String(title.text.prefix(300)), url: url.absoluteString, publisher: publisher, rank: rank))
            }
        }
        guard !items.isEmpty else { throw StudioError.invalidFile("인기뉴스 목록을 읽지 못했습니다. 날짜를 바꾸거나 다시 불러오세요. 네이버 페이지 구조가 변경됐을 수 있습니다.") }
        var publishers = ["연합뉴스", "KBS", "조선일보", "중앙일보", "한겨레"].filter { name in items.contains { $0.publisher == name } }
        for item in items where publishers.count < 5 && !publishers.contains(item.publisher) { publishers.append(item.publisher) }
        return items.filter { publishers.contains($0.publisher) }.sorted {
            $0.rank == $1.rank ? publishers.firstIndex(of: $0.publisher)! < publishers.firstIndex(of: $1.publisher)! : $0.rank < $1.rank
        }
    }
    static func parseArticle(_ markup: String) throws -> String {
        let tree = NewsHTML.parse(markup)
        guard let body = tree.find({ $0.attributes["id"] == "dic_area" || $0.attributes["id"] == "articeBody" }).first,
              body.text.count >= 100 else {
            throw StudioError.invalidFile("기사 본문을 읽지 못했습니다. 원문을 확인하고 요약을 직접 입력해 주세요.")
        }
        let sentences = body.text.components(separatedBy: ". ").filter { $0.count >= 18 }
        return String((sentences.isEmpty ? body.text : sentences.prefix(8).joined(separator: ". ")).prefix(3000))
    }
    private static func fetch(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let (bytes, response) = try await URLSession.shared.bytes(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else {
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            throw StudioError.invalidFile("네이버 요청 실패 (HTTP \(status)). 연결 상태와 검색 API 키를 확인하세요.")
        }
        var data = Data()
        for try await byte in bytes {
            data.append(byte)
            guard data.count <= 3_000_000 else { throw StudioError.invalidFile("뉴스 페이지가 너무 큽니다.") }
        }
        return (data, http)
    }
    private static func html(_ url: URL) async throws -> String {
        var request = URLRequest(url: url, timeoutInterval: 25)
        request.setValue("Mozilla/5.0 (compatible; ContentStudio/1.0)", forHTTPHeaderField: "User-Agent")
        let (data, response) = try await fetch(request)
        let euc = String.Encoding(rawValue: CFStringConvertEncodingToNSStringEncoding(CFStringEncoding(CFStringEncodings.EUC_KR.rawValue)))
        if response.textEncodingName?.lowercased().contains("euc") == true, let value = String(data: data, encoding: euc) { return value }
        guard let value = String(data: data, encoding: .utf8) ?? String(data: data, encoding: euc) else {
            throw StudioError.invalidFile("뉴스 문서의 인코딩을 읽을 수 없습니다.")
        }
        return value
    }
    static func popular(date: Date) async throws -> [NewsItem] {
        let formatter = DateFormatter(); formatter.timeZone = TimeZone(identifier: "Asia/Seoul"); formatter.dateFormat = "yyyyMMdd"
        let url = URL(string: "https://news.naver.com/main/ranking/popularDay.naver?date=" + formatter.string(from: date))!
        return try parseRanking(await html(url))
    }
    static func summary(_ item: NewsItem) async throws -> String {
        guard let url = articleURL(item.url) else {
            if !item.summary.isEmpty { return item.summary }
            throw StudioError.invalidFile("이 기사는 자동 본문 읽기를 지원하지 않습니다. 원문을 확인하고 요약을 입력하세요.")
        }
        return try parseArticle(await html(url))
    }
    static func search(query: String, provider: String, clientID: String, secret: String) async throws -> [NewsItem] {
        guard !clientID.isEmpty, !secret.isEmpty else { throw StudioError.invalidFile("연결 설정에서 네이버 Client ID와 Client Secret을 등록하세요.") }
        let hub = provider == "hub"
        var url = URLComponents(string: hub ? "https://naverapihub.apigw.ntruss.com/search/v1/news" : "https://openapi.naver.com/v1/search/news.json")!
        url.queryItems = [URLQueryItem(name: "query", value: query), URLQueryItem(name: "display", value: "20"), URLQueryItem(name: "sort", value: "date")]
        var request = URLRequest(url: url.url!, timeoutInterval: 25)
        request.setValue(clientID, forHTTPHeaderField: hub ? "X-NCP-APIGW-API-KEY-ID" : "X-Naver-Client-Id")
        request.setValue(secret, forHTTPHeaderField: hub ? "X-NCP-APIGW-API-KEY" : "X-Naver-Client-Secret")
        let (data, _) = try await fetch(request)
        struct Response: Decodable { var items: [Item] }
        struct Item: Decodable { var title: String; var description: String; var link: String; var originallink: String }
        return try JSONDecoder().decode(Response.self, from: data).items.compactMap { item in
            let target = articleURL(item.link)?.absoluteString ?? item.originallink
            guard let url = URL(string: target), ["https", "http"].contains(url.scheme ?? "") else { return nil }
            return NewsItem(title: NewsHTML.clean(item.title), url: target, summary: NewsHTML.clean(item.description))
        }
    }
}

enum NewsDraft {
    static func make(item: NewsItem, summary: String) throws -> StudioProject {
        let text = summary.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { throw StudioError.invalidFile("기사 요약을 입력해 주세요.") }
        var project = StudioProject(); project.kind = "news"; project.title = item.title
        project.sources = [StudioSource(title: item.title, text: text, url: item.url, rights: "사용자가 확인한 뉴스 요약")]
        project.scenes = [StudioScene(title: String(item.title.prefix(90)))]
        project.scenes[0].narration = item.title; project.scenes[0].body = item.publisher; project.scenes[0].sourceIDs = [0]
        // Split user-reviewed material into four cards without inventing facts.
        let chars = Array(text); let size = max(1, Int(ceil(Double(chars.count) / 4)))
        for index in 0..<4 {
            let start = min(index * size, chars.count), end = min((index + 1) * size, chars.count)
            var scene = StudioScene(title: "핵심 내용 \(index + 1)")
            scene.body = String(chars[start..<end]); scene.narration = scene.body; scene.sourceIDs = [0]
            project.scenes.append(scene)
        }
        project.caption = item.title + "\n출처: " + item.url
        return project
    }
}

// Only attributed, commercially reusable Commons photographs are downloaded.
enum NewsImages {
    @MainActor static func attach(to project: inout StudioProject, store: StudioStore) async -> Int {
        var attached = 0
        for index in project.scenes.indices where project.scenes[index].photoID.isEmpty {
            let query = project.scenes[index].imageSearchQuery ?? project.title
            do {
                var url = URLComponents(string: "https://commons.wikimedia.org/w/api.php")!
                let parameters = ["action": "query", "generator": "search", "gsrsearch": query,
                    "gsrnamespace": "6", "gsrlimit": "10", "prop": "imageinfo", "iiprop": "url|extmetadata",
                    "iiurlwidth": "1080", "format": "json", "formatversion": "2"]
                url.queryItems = parameters.map { URLQueryItem(name: $0.key, value: $0.value) }
                var request = URLRequest(url: url.url!); request.timeoutInterval = 15
                request.setValue("ContentStudio/1.0 (news image search)", forHTTPHeaderField: "User-Agent")
                let (data, response) = try await URLSession.shared.data(for: request)
                guard (response as? HTTPURLResponse)?.statusCode == 200,
                      let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                      let result = json["query"] as? [String: Any], let pages = result["pages"] as? [[String: Any]] else { continue }
                for page in pages.sorted(by: { ($0["index"] as? Int ?? 999) < ($1["index"] as? Int ?? 999) }) {
                    guard let info = (page["imageinfo"] as? [[String: Any]])?.first,
                          let meta = info["extmetadata"] as? [String: Any] else { continue }
                    func value(_ key: String) -> String { NewsHTML.clean((meta[key] as? [String: Any])?["value"] as? String ?? "") }
                    let license = value("LicenseShortName"), lower = license.lowercased()
                    let allowed = lower.contains("cc0") || lower.contains("public domain") ||
                        ((lower.contains("cc by") || lower.contains("cc-by")) && !lower.contains("nc") && !lower.contains("nd"))
                    guard allowed, let address = info["thumburl"] as? String, let imageURL = URL(string: address),
                          imageURL.scheme == "https", imageURL.host == "upload.wikimedia.org" else { continue }
                    var imageRequest = URLRequest(url: imageURL); imageRequest.timeoutInterval = 15
                    let (photo, imageResponse) = try await URLSession.shared.data(for: imageRequest)
                    guard (imageResponse as? HTTPURLResponse)?.statusCode == 200, photo.count <= 8_000_000 else { continue }
                    project.scenes[index].photoID = try store.importPhoto(photo)
                    let author = String(value("Artist").prefix(48))
                    project.scenes[index].imageCredit = "\(author.isEmpty ? "작가 미상" : author) · \(license)"
                    let pageURL = info["descriptionurl"] as? String ?? ""
                    project.scenes[index].imageAuthor = author
                    project.scenes[index].imageLicense = license
                    project.scenes[index].imagePageURL = pageURL
                    project.scenes[index].imageLicenseURL = value("LicenseUrl")
                    let credit = "\n사진 \(index + 1): \(author) · \(license) · \(pageURL) · \(value("LicenseUrl"))"
                    if project.caption.count + credit.count <= 2200 { project.caption += credit }
                    attached += 1
                    break
                }
            } catch { continue } // A missing photograph must not discard the news draft.
        }
        return attached
    }
}
