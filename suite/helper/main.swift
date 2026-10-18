import Cocoa
import Carbon.HIToolbox

let supportURL = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/Application Support/HSDisconnect")
let runtimeURL = supportURL.appendingPathComponent("runtime.json")
let runtime = (try? Data(contentsOf: runtimeURL))
    .flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: String] }
let scriptPath = Bundle.main.resourceURL!.appendingPathComponent("hsd.py").path
let pythonPath = runtime?["python"] ?? FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("miniconda3/bin/python3").path
let configPath = supportURL.appendingPathComponent("config.json").path

// Read-only installation probe: exercises the real bundled backend with
// --help, never the cut command, and never starts the floating UI.
if CommandLine.arguments.contains("--diagnose") {
    let probe = Process()
    probe.executableURL = URL(fileURLWithPath: pythonPath)
    probe.arguments = [scriptPath, "--help"]
    let pipe = Pipe()
    probe.standardOutput = pipe
    probe.standardError = pipe
    var backendOK = false
    do {
        try probe.run()
        let output = pipe.fileHandleForReading.readDataToEndOfFile()
        probe.waitUntilExit()
        backendOK = probe.terminationStatus == 0
            && String(data: output, encoding: .utf8)?.contains("usage:") == true
            && String(data: output, encoding: .utf8)?.contains("cut") == true
    } catch { }
    let result: [String: Any] = [
        "suite_version": "3.0.0", "backend_help_ok": backendOK,
        "bundled_backend": FileManager.default.fileExists(atPath: scriptPath),
        "runtime_configured": runtime?["python"] != nil,
        "user_config_exists": FileManager.default.fileExists(atPath: configPath)
    ]
    let data = try! JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
    print(String(data: data, encoding: .utf8)!)
    exit(backendOK ? 0 : 1)
}
let logDir = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/Logs/HSDisconnect")
let logURL = logDir.appendingPathComponent("app.log")

func appLog(_ msg: String) {
    try? FileManager.default.createDirectory(at: logDir, withIntermediateDirectories: true)
    if !FileManager.default.fileExists(atPath: logURL.path) {
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
    }
    let line = "\(ISO8601DateFormatter().string(from: Date())) \(msg)\n"
    if let h = try? FileHandle(forWritingTo: logURL) {
        h.seekToEndOfFile()
        h.write(line.data(using: .utf8)!)
        h.closeFile()
    }
}

final class DragView: NSView {
    override func mouseDown(with event: NSEvent) {
        window?.performDrag(with: event)
    }

    override func draw(_ dirtyRect: NSRect) {
        let shadow = NSShadow()
        shadow.shadowColor = NSColor.black.withAlphaComponent(0.65)
        shadow.shadowBlurRadius = 2
        shadow.shadowOffset = .zero
        shadow.set()

        NSColor(calibratedRed: 0.95, green: 0.88, blue: 0.72, alpha: 0.95).setStroke()
        let grip = NSBezierPath()
        grip.lineWidth = 1.5
        for y in [14.0, 20.0, 26.0] {
            grip.move(to: NSPoint(x: 10, y: y))
            grip.line(to: NSPoint(x: 20, y: y))
        }
        grip.stroke()
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    private var statusItem: NSStatusItem!
    private var hotKeyRef: EventHotKeyRef?
    private var isBusy = false
    private var lastCutAt: Date?
    private var statusMenuItem: NSMenuItem!
    private var floatingPanel: NSPanel?
    private var floatingButton: NSButton?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.accessory)
        appLog("launched pid=\(ProcessInfo.processInfo.processIdentifier)")

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let button = statusItem.button {
            button.title = "拔线"
            button.font = NSFont.systemFont(ofSize: 12, weight: .semibold)
        }

        let menu = NSMenu()
        let item2 = NSMenuItem(title: "拔线", action: #selector(cut2), keyEquivalent: "")
        item2.target = self
        menu.addItem(item2)
        let toggle = NSMenuItem(title: "显示/隐藏悬浮按钮", action: #selector(togglePanel), keyEquivalent: "")
        toggle.target = self
        menu.addItem(toggle)
        menu.addItem(.separator())
        statusMenuItem = NSMenuItem(title: "快捷键 ⌃⌥D", action: nil, keyEquivalent: "")
        menu.addItem(statusMenuItem)
        menu.addItem(.separator())
        let quit = NSMenuItem(title: "退出", action: #selector(quit), keyEquivalent: "q")
        quit.target = self
        menu.addItem(quit)
        statusItem.menu = menu

        registerHotKey()
        setupFloatingButton()
    }

    private func registerHotKey() {
        var eventType = EventTypeSpec(eventClass: OSType(kEventClassKeyboard),
                                      eventKind: UInt32(kEventHotKeyPressed))
        let handlerStatus = InstallEventHandler(
            GetApplicationEventTarget(),
            { (_, _, userData) -> OSStatus in
                guard let userData = userData else { return noErr }
                let delegate = Unmanaged<AppDelegate>.fromOpaque(userData).takeUnretainedValue()
                appLog("hotkey pressed")
                delegate.performCut(seconds: 2.0)
                return noErr
            },
            1,
            &eventType,
            Unmanaged.passUnretained(self).toOpaque(),
            nil
        )
        appLog("InstallEventHandler status=\(handlerStatus)")

        let hotKeyID = EventHotKeyID(signature: OSType(0x48534431), id: 1)
        let status = RegisterEventHotKey(
            UInt32(kVK_ANSI_D),
            UInt32(controlKey | optionKey),
            hotKeyID,
            GetApplicationEventTarget(),
            0,
            &hotKeyRef
        )
        appLog("RegisterEventHotKey ctrl+opt+D status=\(status)")
        if status != noErr, let item = statusMenuItem {
            item.title = "快捷键注册失败（\(status)），请点悬浮按钮"
        }
    }

    private func setupFloatingButton() {
        let panel = NSPanel(
            contentRect: NSRect(x: 0, y: 0, width: 104, height: 40),
            styleMask: [.nonactivatingPanel, .borderless],
            backing: .buffered,
            defer: false
        )
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.isMovableByWindowBackground = false
        panel.becomesKeyOnlyIfNeeded = true
        panel.delegate = self

        let content = DragView(frame: NSRect(x: 0, y: 0, width: 104, height: 40))
        content.toolTip = "拖动左侧把手可移动"
        let button = NSButton(title: "拔线", target: self, action: #selector(cut2))
        button.isBordered = false
        button.wantsLayer = true
        button.layer?.backgroundColor = NSColor(calibratedRed: 0.16, green: 0.12, blue: 0.09, alpha: 0.72).cgColor
        button.layer?.cornerRadius = 9
        button.layer?.borderWidth = 1
        button.layer?.borderColor = NSColor(calibratedRed: 0.83, green: 0.66, blue: 0.36, alpha: 0.75).cgColor
        button.frame = NSRect(x: 28, y: 4, width: 72, height: 32)
        button.autoresizingMask = [.width, .height]
        content.addSubview(button)
        floatingButton = button
        setButtonTitle("拔线")
        panel.contentView = content

        let defaults = UserDefaults.standard
        if defaults.object(forKey: "panelX") != nil {
            let x = defaults.double(forKey: "panelX")
            let y = defaults.double(forKey: "panelY")
            panel.setFrameOrigin(NSPoint(x: x, y: y))
        } else if let screen = NSScreen.main {
            let f = screen.visibleFrame
            panel.setFrameOrigin(NSPoint(x: f.maxX - 114, y: f.maxY - 50))
        }

        if let screen = NSScreen.main {
            let vf = screen.visibleFrame
            let w = panel.frame.width
            let h = panel.frame.height
            var origin = panel.frame.origin
            origin.x = min(max(origin.x, vf.minX), vf.maxX - w)
            origin.y = min(max(origin.y, vf.minY), vf.maxY - h)
            panel.setFrameOrigin(origin)
        }

        panel.orderFrontRegardless()
        floatingPanel = panel
        floatingButton = button
        appLog("floating panel shown at \(panel.frame.origin)")
    }

    func windowDidMove(_ notification: Notification) {
        guard let w = notification.object as? NSWindow else { return }
        UserDefaults.standard.set(w.frame.origin.x, forKey: "panelX")
        UserDefaults.standard.set(w.frame.origin.y, forKey: "panelY")
    }

    @objc private func togglePanel() {
        guard let p = floatingPanel else { return }
        if p.isVisible {
            p.orderOut(nil)
        } else {
            p.orderFrontRegardless()
        }
    }

    @objc private func cut2() {
        appLog("menu cut2")
        performCut(seconds: 0)
    }

    private func setButtonTitle(_ text: String) {
        let attrs: [NSAttributedString.Key: Any] = [
            .foregroundColor: NSColor(calibratedRed: 0.97, green: 0.91, blue: 0.78, alpha: 1.0),
            .font: NSFont.systemFont(ofSize: 13, weight: .semibold)
        ]
        floatingButton?.attributedTitle = NSAttributedString(string: text, attributes: attrs)
    }

    @objc private func cut3() {
        appLog("menu cut3")
        performCut(seconds: 0)
    }

    private func performCut(seconds: Double) {
        guard !isBusy else {
            appLog("busy, ignored")
            return
        }
        if let last = lastCutAt, Date().timeIntervalSince(last) < 5.0 {
            appLog("cooldown ignored")
            statusMenuItem.title = "冷却中，请稍等"
            return
        }
        lastCutAt = Date()
        isBusy = true
        statusItem.button?.title = "断线中"
        statusMenuItem.title = "正在断线…"
        setButtonTitle("断线中…")
        appLog("performCut seconds=\(seconds)")

        DispatchQueue.global(qos: .userInitiated).async {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: pythonPath)
            p.arguments = [scriptPath, "--config", configPath, "cut", "--seconds", "0"]
            let pipe = Pipe()
            p.standardOutput = pipe
            p.standardError = pipe
            var output = ""
            do {
                try p.run()
                p.waitUntilExit()
                let data = pipe.fileHandleForReading.readDataToEndOfFile()
                output = String(data: data, encoding: .utf8) ?? ""
                appLog("cut exit=\(p.terminationStatus) out=\(output.trimmingCharacters(in: .whitespacesAndNewlines))")
            } catch {
                output = "启动失败：\(error)"
                appLog("cut launch error=\(error)")
            }
            DispatchQueue.main.async {
                self.isBusy = false
                self.statusItem.button?.title = "拔线"
                self.setButtonTitle("已发出")
                let first = output.split(separator: "\n").first.map(String.init) ?? "完成"
                self.statusMenuItem.title = first
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
                    self.setButtonTitle("拔线")
                }
                NSSound.beep()
            }
        }
    }

    @objc private func quit() {
        appLog("quit")
        NSApp.terminate(nil)
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
