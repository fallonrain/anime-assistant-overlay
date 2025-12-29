ANIME ASSISTANT OVERLAY (PNGTuber + Neural TTS)
===============================================

Projeto em Python com overlay transparente (estilo PNGTuber) usando sprites PNG e
voz neural via Edge TTS (ex.: ja-JP-NanamiNeural), tocando áudio com mpv.

Preview (imagem no repositório):
- docs\screenshot.png


FEATURES
--------
- Overlay transparente sempre no topo
- Click-through (não atrapalha cliques)
- Animação: idle / talking / blink
- Voz neural (Edge TTS): ja-JP-NanamiNeural (configurável)
- Controles por comando no terminal
- (Opcional) ask usando Ollama (LLM local)


REQUISITOS
----------
- Windows 10/11
- Python 3.10+ (recomendado)
- mpv instalado (para tocar o áudio)
- Internet (para Edge TTS)
- (Opcional) Ollama instalado + modelo baixado (para comando ask)


ESTRUTURA SUGERIDA
------------------
anime_assistant\
  main.py
  config.json
  requirements.txt
  assets\
    Open Eyes Closed Mouth.png
    Open Eyes Open Mouth.png
    Closed Eyes Closed Mouth.png
    Closed Eyes Open Mouth.png
  docs\
    screenshot.png


INSTALACAO (Windows / PowerShell)
---------------------------------
1) Criar e ativar venv:
   python -m venv .venv
   .venv\Scripts\activate

2) Instalar dependências:
   python -m pip install -r requirements.txt

   Se não tiver requirements.txt:
   python -m pip install PySide6 pywin32 edge-tts
   (opcional para ask) python -m pip install ollama

3) Instalar mpv:
   winget install mpv


CONFIGURACAO (config.json)
--------------------------
Exemplo:

{
  "scale": 0.55,
  "click_through": false,
  "always_on_top": true,
  "position": "bottom_right",
  "margin": [20, 20],
  "fps_ms": 110,
  "frames": {
    "idle": ["assets/Open Eyes Closed Mouth.png"],
    "talk": ["assets/Open Eyes Open Mouth.png", "assets/Open Eyes Closed Mouth.png"],
    "blink_idle": ["assets/Closed Eyes Closed Mouth.png"],
    "blink_talk": ["assets/Closed Eyes Open Mouth.png"]
  },
  "blink": { "enabled": true, "min_ms": 2500, "max_ms": 6000, "duration_ms": 120 }
}


RODANDO
-------
python main.py


COMANDOS (no terminal)
----------------------
- say <texto>        : fala com voz neural e anima a boca
- ask <pergunta>     : pergunta para IA local (Ollama) [opcional]
- model <nome>       : troca o modelo do Ollama (ex: qwen2.5:3b)
- ct                 : alterna click-through (passar clique através do overlay)
- talk on/off        : liga/desliga animação de fala manual
- voice <nome>       : troca voz (ex: ja-JP-NanamiNeural)
- pitch <+25Hz>      : ajusta pitch (ex: +35Hz)
- rate <+10%>        : ajusta velocidade (ex: -10%)
- quit               : fecha


ASK COM OLLAMA (opcional)
-------------------------
1) Instale o Ollama (app do Windows)
2) Baixe um modelo:
   ollama pull qwen2.5:3b

3) Rode o app e use:
   ask oi, quem é você?


DICAS
-----
- Para posicionar com o mouse: deixe click_through=false, arraste o avatar e depois use ct.
- Se o overlay não ficar acima de jogos fullscreen, use modo "borderless windowed" no jogo.


LICENCA / AVISOS
----------------
Uso educacional. Se você usar sprites de terceiros, respeite a licença dos assets.
