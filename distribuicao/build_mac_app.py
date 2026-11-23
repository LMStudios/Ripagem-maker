"""Gera app Mac Universal, com código embarcado e dados fora do bundle."""
import importlib.util,plistlib,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'distribuicao/pacotes/Aplicativo-Mac'
APP=OUT/'Ripagem Maker.app'
BUILD=ROOT/'distribuicao/build-mac'
BUILD.mkdir(parents=True,exist_ok=True)
s=(ROOT/'mac_app/main.swift').read_text()
s=s.replace('    lazy var root: String = (Bundle.main.object(forInfoDictionaryKey: "DRStudioRoot") as? String) ?? ""','    var root: String = ""')
s=s.replace('    lazy var python: String = (Bundle.main.object(forInfoDictionaryKey: "DRStudioPython") as? String) ?? "/usr/bin/python3"','    let python = "/bin/zsh"')
s=s.replace('        buildMenu()','        buildMenu()',1)
s=s.replace('        DispatchQueue.global(qos: .userInitiated).async { self.startServer() }','''        if ping() { fail("Feche a versão anterior do Ripagem Maker (incluindo o Terminal que a iniciou) e abra este aplicativo novamente. Seus trabalhos permanecem salvos."); return }
        guard preparePortable() else { return }
        DispatchQueue.global(qos: .userInitiated).async { self.startServer() }''',1)
s=s.replace('p.arguments = [root + "/app.py"]','p.arguments = [root + "/abrir-interno.zsh"]')
s=s.replace('"Aguardando permissão do macOS…",\n                        "Se apareceu um aviso pedindo acesso à pasta Documentos, clique em Permitir. Isso só acontece na primeira vez."','"Preparando o Ripagem Maker…",\n                        "Na primeira abertura, as dependências são preparadas neste Mac. Isso pode levar alguns minutos. Se o macOS pedir acesso à pasta escolhida, permita."')
pos=s.index('    func startServer()')
s=s[:pos]+'''    func preparePortable() -> Bool {
        let fm = FileManager.default
        let defaults = UserDefaults.standard
        if let saved = defaults.string(forKey: "PortableRoot"), fm.fileExists(atPath: saved + "/app.py") {
            root = saved
        } else {
            let a = NSAlert()
            a.messageText = "Bem-vindo ao Ripagem Maker"
            a.informativeText = "Se você já usa o Ripagem Maker, escolha a pasta da instalação que contém app.py para preservar os trabalhos e as configurações."
            a.addButton(withTitle: "Usar instalação anterior")
            a.addButton(withTitle: "Começar em pasta nova")
            if a.runModal() == .alertFirstButtonReturn {
                let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false
                panel.message = "Escolha a pasta da instalação anterior que contém app.py."
                guard panel.runModal() == .OK, let folder = panel.url,
                      fm.fileExists(atPath: folder.appendingPathComponent("app.py").path) else {
                    fail("Escolha a pasta da instalação anterior que contém app.py e abra o aplicativo novamente."); return false
                }
                root = folder.path
            } else {
                root = fm.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/Ripagem Maker/Dados").path
            }
        }
        let installedVersion = (try? String(contentsOfFile: root + "/VERSION", encoding: .utf8))?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "0.0.0"
        let bundledVersion = (try? String(contentsOf: Bundle.main.resourceURL!.appendingPathComponent("Aplicativo/VERSION"), encoding: .utf8))?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "0.0.0"
        if installedVersion.compare(bundledVersion, options: .numeric) != .orderedAscending {
            do {
                for name in ["abrir-interno.zsh", "iniciar.py", "requirements.txt"] {
                    let target = URL(fileURLWithPath: root).appendingPathComponent(name)
                    if !fm.fileExists(atPath: target.path) {
                        let source = Bundle.main.resourceURL!.appendingPathComponent("Aplicativo/" + name)
                        try Data(contentsOf: source).write(to: target, options: .atomic)
                    }
                }
            } catch { fail("Não foi possível preparar o iniciador: " + error.localizedDescription); return false }
            defaults.set(root, forKey: "PortableRoot"); return true
        }
        do {
            try fm.createDirectory(atPath: root, withIntermediateDirectories: true)
            let bundled = Bundle.main.resourceURL!.appendingPathComponent("Aplicativo")
            let enumerator = fm.enumerator(at: bundled, includingPropertiesForKeys: [.isRegularFileKey])!
            for case let file as URL in enumerator {
                if try file.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile != true { continue }
                let relative = String(file.path.dropFirst(bundled.path.count + 1))
                let target = URL(fileURLWithPath: root).appendingPathComponent(relative)
                try fm.createDirectory(at: target.deletingLastPathComponent(), withIntermediateDirectories: true)
                try Data(contentsOf: file).write(to: target, options: .atomic)
            }
            defaults.set(root, forKey: "PortableRoot")
            return true
        } catch { fail("Não foi possível preparar os arquivos: " + error.localizedDescription); return false }
    }

'''+s[pos:]
source=BUILD/'portable.swift';source.write_text(s)
for arch in ('arm64','x86_64'):
 subprocess.run(['swiftc','-O','-swift-version','5','-target',arch+'-apple-macos13.0',str(source),'-o',str(BUILD/arch),'-framework','Cocoa','-framework','WebKit'],check=True)
if APP.exists():shutil.rmtree(APP)
resources=APP/'Contents/Resources';macos=APP/'Contents/MacOS';macos.mkdir(parents=True);resources.mkdir()
subprocess.run(['lipo','-create',str(BUILD/'arm64'),str(BUILD/'x86_64'),'-output',str(macos/'RipagemMaker')],check=True)
payload=resources/'Aplicativo';payload.mkdir()
spec=importlib.util.spec_from_file_location('pack',ROOT/'distribuicao/empacotar.py');pack=importlib.util.module_from_spec(spec);spec.loader.exec_module(pack)
for file in pack.files():
 dest=payload/file.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(file,dest)
for name in ('iniciar.py','requirements.txt'):shutil.copy2(ROOT/'distribuicao'/name,payload/name)
(payload/'abrir-interno.zsh').write_text('''#!/bin/zsh
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
cd "${0:A:h}"
for candidate in python3.12 python3.13 python3.11 python3.10 python3; do
 if command -v "$candidate" >/dev/null; then
  exec "$candidate" iniciar.py --embedded
 fi
done
echo "Instale Python 3.12 para macOS e abra novamente."
exit 1
''')
info={'CFBundleName':'Ripagem Maker','CFBundleDisplayName':'Ripagem Maker','CFBundleIdentifier':'local.ripagemmaker.portable','CFBundleExecutable':'RipagemMaker','CFBundlePackageType':'APPL','CFBundleShortVersionString':(ROOT/'VERSION').read_text().strip(),'CFBundleVersion':(ROOT/'VERSION').read_text().strip().replace('.',''),'LSMinimumSystemVersion':'13.0','NSHighResolutionCapable':True,'NSAppTransportSecurity':{'NSAllowsLocalNetworking':True}}
icon=ROOT/'design/logo/RipagemMaker.icns'
if icon.exists():shutil.copy2(icon,resources/'AppIcon.icns');info['CFBundleIconFile']='AppIcon'
with (APP/'Contents/Info.plist').open('wb') as f:plistlib.dump(info,f)
subprocess.run(['codesign','--force','--deep','-s','-',str(APP)],check=True)
(OUT/'COMO ABRIR.txt').write_text('''Ripagem Maker — macOS 13 ou superior, Intel e Apple Silicon.
1. Feche a versão anterior e o Terminal que mantém o servidor aberto.
2. Arraste Ripagem Maker.app para Aplicativos e abra com dois cliques.
3. Se já usa o app, escolha Usar instalação anterior e selecione a pasta que contém app.py.
   Ela continua guardando seus trabalhos. Para uma instalação nova, escolha Começar em pasta nova.
4. Configure ou substitua sua chave em Ajustes → Integrações e APIs.
Python e FFmpeg já instalados são aproveitados. Novos computadores ainda precisam dessas dependências.
O app tem assinatura local, sem notarização Apple; a abertura em outro Mac pode depender da política do macOS.
O pacote não inclui credenciais, vídeos ou trabalhos do autor.
''')
zip_path=ROOT/'distribuicao/pacotes/Ripagem-Maker-App-Mac.zip'
if zip_path.exists():zip_path.unlink()
subprocess.run(['ditto','-c','-k','--sequesterRsrc','--keepParent',str(OUT),str(zip_path)],check=True)
print(zip_path)
