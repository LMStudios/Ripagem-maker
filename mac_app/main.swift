// Ripagem Maker — app nativo do macOS.
// Liga o servidor local (app.py) ao abrir, mostra a interface numa janela própria (WKWebView)
// e desliga o servidor — e os processos de transcrição/render que ele criou — ao fechar.
import Cocoa
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate, WKScriptMessageHandler {
    var window: NSWindow!
    var web: WKWebView!
    var server: Process?
    var popups: [NSWindow] = []
    var downloads: [ObjectIdentifier: URL] = [:]
    let port = 8765
    lazy var root: String = (Bundle.main.object(forInfoDictionaryKey: "DRStudioRoot") as? String) ?? ""
    lazy var python: String = (Bundle.main.object(forInfoDictionaryKey: "DRStudioPython") as? String) ?? "/usr/bin/python3"
    var base: URL { URL(string: "http://127.0.0.1:\(port)/")! }
    lazy var logURL: URL = {
        let dir = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/Ripagem Maker")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("servidor.log")
    }()

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.name == "chooseStorage", message.frameInfo.isMainFrame,
              let host = message.webView?.url?.host, ["127.0.0.1", "localhost"].contains(host) else { return }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = true
        panel.allowsMultipleSelection = false
        panel.prompt = "Usar esta pasta"
        panel.message = "Escolha a pasta principal dos novos trabalhos do Ripagem Maker."
        panel.beginSheetModal(for: window) { response in
            guard response == .OK, let path = panel.url?.path,
                  let data = try? JSONSerialization.data(withJSONObject: path, options: .fragmentsAllowed),
                  let encoded = String(data: data, encoding: .utf8) else { return }
            self.web.evaluateJavaScript("window.dispatchEvent(new CustomEvent('dr-folder-selected', {detail: \(encoded)}))", completionHandler: nil)
        }
    }

    // MARK: ciclo de vida
    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()
        let cfg = WKWebViewConfiguration()
        cfg.userContentController.add(self, name: "chooseStorage")
        cfg.preferences.setValue(true, forKey: "developerExtrasEnabled")
        cfg.mediaTypesRequiringUserActionForPlayback = []
        web = WKWebView(frame: .zero, configuration: cfg)
        web.navigationDelegate = self
        web.uiDelegate = self
        web.allowsBackForwardNavigationGestures = true
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 900),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "Ripagem Maker"
        window.minSize = NSSize(width: 960, height: 620)
        window.contentView = web
        window.center()
        window.setFrameAutosaveName("DRStudioJanela")
        window.makeKeyAndOrderFront(nil)
        web.loadHTMLString(page("Iniciando o Ripagem Maker…", "Ligando o motor local de transcrição e montagem."), baseURL: nil)
        NSApp.activate(ignoringOtherApps: true)
        DispatchQueue.global(qos: .userInitiated).async { self.startServer() }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ notification: Notification) { stopServer() }

    // MARK: servidor local
    func ping() -> Bool {
        var ok = false
        let sem = DispatchSemaphore(value: 0)
        var req = URLRequest(url: base.appendingPathComponent("api/sistema"))
        req.timeoutInterval = 1.0
        URLSession.shared.dataTask(with: req) { _, resp, _ in
            ok = (resp as? HTTPURLResponse)?.statusCode == 200
            sem.signal()
        }.resume()
        _ = sem.wait(timeout: .now() + 1.5)
        return ok
    }

    func startServer() {
        if ping() { DispatchQueue.main.async { self.web.load(URLRequest(url: self.base)) }; return }
        guard FileManager.default.fileExists(atPath: root + "/app.py") else {
            return fail("Não encontrei os arquivos do Ripagem Maker em:\n\(root)\n\nA pasta APP_TRANSCRICAO_SPEAKERS foi movida ou renomeada?")
        }
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        let log = try? FileHandle(forWritingTo: logURL)
        let p = Process()
        p.executableURL = URL(fileURLWithPath: python)
        p.arguments = [root + "/app.py"]
        p.currentDirectoryURL = FileManager.default.homeDirectoryForCurrentUser
        var env = ProcessInfo.processInfo.environment
        env["DRSTUDIO_EMBED"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        p.environment = env
        p.standardOutput = log
        p.standardError = log
        do { try p.run() } catch {
            return fail("Não consegui iniciar o Python (\(python)).\n\(error.localizedDescription)")
        }
        server = p
        var hinted = false
        for i in 0..<1200 {  // até 10 min: na 1ª vez o macOS pede permissão para a pasta Documentos
            if !p.isRunning { return fail("O motor local fechou ao iniciar.\n\n" + logTail()) }
            if ping() { DispatchQueue.main.async { self.web.load(URLRequest(url: self.base)) }; return }
            if i == 12 && !hinted {
                hinted = true
                DispatchQueue.main.async {
                    self.web.loadHTMLString(self.page("Aguardando permissão do macOS…",
                        "Se apareceu um aviso pedindo acesso à pasta Documentos, clique em Permitir. Isso só acontece na primeira vez."), baseURL: nil)
                }
            }
            Thread.sleep(forTimeInterval: 0.5)
        }
        fail("O motor local não respondeu.\n\n" + logTail())
    }

    func stopServer() {
        guard let p = server, p.isRunning else { return }
        // encerra primeiro os filhos (ffmpeg, transcrição) e depois o servidor
        let k = Process()
        k.executableURL = URL(fileURLWithPath: "/usr/bin/pkill")
        k.arguments = ["-TERM", "-P", String(p.processIdentifier)]
        try? k.run(); k.waitUntilExit()
        p.terminate()
        p.waitUntilExit()
    }

    func logTail() -> String {
        let t = (try? String(contentsOf: logURL, encoding: .utf8)) ?? ""
        return t.split(separator: "\n").suffix(12).joined(separator: "\n")
    }

    func fail(_ msg: String) {
        DispatchQueue.main.async {
            self.web.loadHTMLString(self.page("Não foi possível abrir o Ripagem Maker", msg, erro: true), baseURL: nil)
        }
    }

    func page(_ title: String, _ msg: String, erro: Bool = false) -> String {
        let m = msg.replacingOccurrences(of: "&", with: "&amp;").replacingOccurrences(of: "<", with: "&lt;")
        return """
        <html><head><meta charset="utf-8"><style>
        :root{color-scheme:light dark} body{font:15px -apple-system,sans-serif;display:grid;place-items:center;height:100vh;margin:0;
        background:Canvas;color:CanvasText} .b{max-width:640px;text-align:center} h1{font-size:20px;font-weight:600}
        pre{white-space:pre-wrap;text-align:left;font-size:12px;opacity:.8;background:rgba(127,127,127,.12);padding:12px;border-radius:10px}
        .s{width:28px;height:28px;border:3px solid rgba(127,127,127,.3);border-top-color:#5b5bf5;border-radius:50%;margin:0 auto 16px;animation:r 1s linear infinite}
        @keyframes r{to{transform:rotate(360deg)}}</style></head><body><div class="b">
        \(erro ? "" : "<div class='s'></div>")<h1>\(title)</h1>\(erro ? "<pre>\(m)</pre><p>Registro completo: ~/Library/Logs/Ripagem Maker/servidor.log</p>" : "<p>\(m)</p>")
        </div></body></html>
        """
    }

    // MARK: navegação, janelas e downloads
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let u = action.request.url, let host = u.host, !["127.0.0.1", "localhost"].contains(host),
           u.scheme == "http" || u.scheme == "https" {
            NSWorkspace.shared.open(u)  // links externos abrem no navegador padrão
            return decisionHandler(.cancel)
        }
        decisionHandler(action.shouldPerformDownload ? .download : .allow)
    }

    func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
                 decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
        if let h = response.response as? HTTPURLResponse,
           let cd = h.value(forHTTPHeaderField: "Content-Disposition"), cd.lowercased().contains("attachment") {
            return decisionHandler(.download)
        }
        decisionHandler(response.canShowMIMEType ? .allow : .download)
    }

    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) { download.delegate = self }
    func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) { download.delegate = self }

    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse, suggestedFilename: String,
                  completionHandler: @escaping (URL?) -> Void) {
        let dir = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask)[0]
        var dest = dir.appendingPathComponent(suggestedFilename)
        let stem = dest.deletingPathExtension().lastPathComponent, ext = dest.pathExtension
        var i = 2
        while FileManager.default.fileExists(atPath: dest.path) {
            dest = dir.appendingPathComponent("\(stem) (\(i))" + (ext.isEmpty ? "" : ".\(ext)")); i += 1
        }
        downloads[ObjectIdentifier(download)] = dest
        completionHandler(dest)
    }

    func downloadDidFinish(_ download: WKDownload) {
        if let u = downloads.removeValue(forKey: ObjectIdentifier(download)) {
            NSWorkspace.shared.activateFileViewerSelecting([u])
        }
    }

    func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
        alert("Download não concluído", error.localizedDescription)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        if (error as NSError).code == NSURLErrorCancelled { return }
        if server.map({ !$0.isRunning }) ?? false {
            webView.loadHTMLString(page("O motor local parou", logTail(), erro: true), baseURL: nil)
        }
    }

    // links com target=_blank (assistir vídeo, abrir transcrição) abrem numa janela do próprio app
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        let v = WKWebView(frame: .zero, configuration: configuration)
        v.navigationDelegate = self; v.uiDelegate = self
        let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 960, height: 640),
                         styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        w.title = action.request.url?.lastPathComponent.removingPercentEncoding ?? "Ripagem Maker"
        w.contentView = v; w.isReleasedWhenClosed = false; w.center(); w.makeKeyAndOrderFront(nil)
        popups.append(w)
        return v
    }

    func webViewDidClose(_ webView: WKWebView) { webView.window?.close() }

    // seletor de arquivos (input type=file)
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let p = NSOpenPanel()
        p.allowsMultipleSelection = parameters.allowsMultipleSelection
        p.canChooseDirectories = false
        p.canChooseFiles = true
        p.beginSheetModal(for: webView.window ?? window) { r in completionHandler(r == .OK ? p.urls : nil) }
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let a = NSAlert(); a.messageText = message; a.addButton(withTitle: "OK")
        a.beginSheetModal(for: webView.window ?? window) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = NSAlert(); a.messageText = message
        a.addButton(withTitle: "OK"); a.addButton(withTitle: "Cancelar")
        a.beginSheetModal(for: webView.window ?? window) { r in completionHandler(r == .alertFirstButtonReturn) }
    }

    func alert(_ title: String, _ text: String) {
        let a = NSAlert(); a.messageText = title; a.informativeText = text; a.runModal()
    }

    // MARK: menus
    func buildMenu() {
        let main = NSMenu()
        func item(_ t: String, _ s: Selector?, _ k: String, _ m: NSEvent.ModifierFlags = .command, target: AnyObject? = nil) -> NSMenuItem {
            let i = NSMenuItem(title: t, action: s, keyEquivalent: k); i.keyEquivalentModifierMask = m; i.target = target; return i
        }
        let app = NSMenu()
        app.addItem(item("Sobre o Ripagem Maker", #selector(NSApplication.orderFrontStandardAboutPanel(_:)), ""))
        app.addItem(.separator())
        app.addItem(item("Ocultar Ripagem Maker", #selector(NSApplication.hide(_:)), "h"))
        app.addItem(.separator())
        app.addItem(item("Sair do Ripagem Maker", #selector(NSApplication.terminate(_:)), "q"))
        let file = NSMenu(title: "Arquivo")
        file.addItem(item("Abrir montagens (vídeos e XMLs)", #selector(openOutMl), "o", [.command, .shift], target: self))
        file.addItem(item("Abrir saídas do Fatiador", #selector(openOutFat), "", target: self))
        file.addItem(.separator())
        file.addItem(item("Mostrar registro do motor", #selector(openLog), "", target: self))
        file.addItem(item("Fechar janela", #selector(NSWindow.performClose(_:)), "w"))
        let edit = NSMenu(title: "Editar")
        edit.addItem(item("Desfazer", Selector(("undo:")), "z"))
        edit.addItem(item("Refazer", Selector(("redo:")), "z", [.command, .shift]))
        edit.addItem(.separator())
        edit.addItem(item("Recortar", #selector(NSText.cut(_:)), "x"))
        edit.addItem(item("Copiar", #selector(NSText.copy(_:)), "c"))
        edit.addItem(item("Colar", #selector(NSText.paste(_:)), "v"))
        edit.addItem(item("Selecionar tudo", #selector(NSText.selectAll(_:)), "a"))
        let view = NSMenu(title: "Ir")
        view.addItem(item("Painel", #selector(goHome), "1", target: self))
        view.addItem(item("Microlead + Body", #selector(goMl), "2", target: self))
        view.addItem(item("Lote de combinações", #selector(goLote), "3", target: self))
        view.addItem(item("Fatiador e troca de potes", #selector(goFat), "4", target: self))
        view.addItem(item("Regras de corte", #selector(goRegras), "5", target: self))
        view.addItem(.separator())
        view.addItem(item("Voltar", #selector(goBack), "[", target: self))
        view.addItem(item("Recarregar", #selector(reload), "r", target: self))
        let win = NSMenu(title: "Janela")
        win.addItem(item("Minimizar", #selector(NSWindow.performMiniaturize(_:)), "m"))
        win.addItem(item("Zoom", #selector(NSWindow.performZoom(_:)), ""))
        for (title, sub) in [("Ripagem Maker", app), ("Arquivo", file), ("Editar", edit), ("Ir", view), ("Janela", win)] {
            let top = NSMenuItem(title: title, action: nil, keyEquivalent: ""); top.submenu = sub; main.addItem(top)
        }
        NSApp.mainMenu = main
        NSApp.windowsMenu = win
    }

    func go(_ path: String) { window.makeKeyAndOrderFront(nil); web.load(URLRequest(url: URL(string: path, relativeTo: base)!)) }
    @objc func goHome() { go("/#/") }
    @objc func goMl() { go("/#/microlead") }
    @objc func goLote() { go("/#/lote") }
    @objc func goRegras() { go("/#/regras") }
    @objc func goFat() { go("/fatiador") }
    @objc func goBack() { web.goBack() }
    @objc func reload() { web.reload() }
    func storagePath(_ subfolder: String, legacy: String) -> URL {
        let config = URL(fileURLWithPath: root + "/plataforma/workspace/ajustes.json")
        if let data = try? Data(contentsOf: config),
           let settings = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let path = settings["pasta_principal"] as? String, !path.isEmpty {
            return URL(fileURLWithPath: path).appendingPathComponent(subfolder)
        }
        return URL(fileURLWithPath: root + legacy)
    }
    @objc func openOutMl() { NSWorkspace.shared.open(storagePath("Montagens", legacy: "/plataforma/workspace/saidas")) }
    @objc func openOutFat() { NSWorkspace.shared.open(storagePath("Fatiador", legacy: "/saidas")) }
    @objc func openLog() { NSWorkspace.shared.open(logURL) }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
