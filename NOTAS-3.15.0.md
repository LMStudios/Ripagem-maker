# Ripagem Maker 3.15.0 — Busca automática de b-roll no TikTok e no Pinterest

Base: 3.14.0.

## Novo
- **Takes → B-roll → botões "TikTok" e "Pinterest"** (app instalado): o app abre a busca do site numa janela própria, coleta os links dos vídeos dos resultados (até 8), baixa ~10 s de cada um, confere texto na tela e marca d'água e mostra os clipes junto dos do YouTube. Nada entra no XML sem "Usar nesta frase".
- **Login guardado:** a janela usa uma sessão própria do app. O TikTok costuma mostrar resultados sem login; o **Pinterest exige login** (sem ele, esconde o link de cada vídeo) — a janela abre sozinha pedindo para entrar, só na primeira vez. "Entrar com Google/Apple/Facebook" funciona nessa janela; outras janelas são bloqueadas, e a janela não tem acesso a arquivos do computador.
- No navegador comum (sem o app instalado), TikTok e Pinterest continuam por link colado.
- O mesmo vídeo usado em outra frase é reaproveitado sem baixar de novo.

## Correções
- **App Mac 3.14.0 sem o componente de busca:** o motor do app Mac é montado uma vez e não incluía o yt-dlp; na 3.14.0 instalada no Mac o b-roll avisava "Falta o componente de busca". O motor foi remontado com o yt-dlp.
- **Marca d'água — alarme falso em vídeo do TikTok:** bordas paradas de espelho, teto e parede (câmera parada) eram lidas como grade. Agora só conta linha diagonal que atravessa a cena em movimento, e legenda fixa é tratada como "Texto na tela", não como marca d'água.
- YouTube usa o deno ou o node do computador quando houver (sem eles ainda baixa; alguns formatos podem faltar).

## Testado
- TikTok real dentro do Electron: 8 links em 19 s sem login; os 6 primeiros baixados e conferidos em 47 s (1 limpo e 5 com legenda gravada no vídeo).
- Pinterest real: a janela abre em 2,5 s pedindo login; fechar a janela encerra a busca com aviso. **A coleta depois do login no Pinterest não foi testada** (precisa da sua conta).
- Detector conferido em 15 clipes reais: 2 marcas d'água (grade do Motion Array), 5 com texto, 8 limpos, nenhum alarme falso.
- Testes: Python (inclui 8 do b-roll), 17 do Electron (5 novos da coleta), interface.

## Limites
- Os botões TikTok/Pinterest precisam do **instalador completo** (o ZIP de atualização não atualiza a parte nativa do app).
- TikTok e Pinterest mudam a página de resultados de tempos em tempos; se a coleta parar de achar vídeos, a busca precisa de ajuste.
- Muitos vídeos do TikTok vêm com legenda gravada: use "Só clipes limpos" para esconder.
- Confira a licença de cada vídeo antes de entregar.
