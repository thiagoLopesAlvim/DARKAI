"""
Módulo gerador_audio.py
Integração com a API do ElevenLabs (ou sintetizador de contingência) para geração da narração em MP3.
"""

import os
import json
import re
import subprocess
import requests
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

# Voz padrão (Adam - tom grave e misterioso, ideal para Canal Dark)
DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"
ELEVEN_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"


def sanitizar_nome_arquivo(texto: str) -> str:
    """Converte um texto em uma string segura para nome de arquivo."""
    texto = texto.lower()
    texto = re.sub(r'[^\w\s-]', '', texto)
    return re.sub(r'[-\s]+', '_', texto).strip('_')[:50]


def extrair_texto_narracao(roteiro_dados: Dict[str, Any]) -> str:
    """Extrai e concatena o texto de todas as cenas com pausas pontuadas."""
    cenas = roteiro_dados.get("cenas", [])
    textos = []
    for c in cenas:
        narracao = c.get("narracao", "").strip()
        if narracao:
            # Garante terminação pontuada para pausa natural
            if not narracao.endswith((".", "!", "?")):
                narracao += "."
            textos.append(narracao)
    return " ".join(textos)


def sintetizar_audio_edge_tts(
    texto: str,
    caminho_saida: str,
    voz: str = "pt-BR-AntonioNeural",
    rate: str = "-4%",
    pitch: str = "-2Hz"
) -> bool:
    """
    Sintetiza áudio neural em Português do Brasil nativo com entonação de documentário Dark.
    Usa Edge-TTS (Microsoft Neural Voices) — gratuito, sem necessidade de chaves e com dicção impecável.
    Captura eventos de fronteira de sentença (SentenceBoundary) para sincronização perfeita de legendas.
    """
    try:
        import asyncio
        import edge_tts
        import json

        os.makedirs(os.path.dirname(caminho_saida), exist_ok=True)
        boundaries = []

        async def _gerar():
            communicate = edge_tts.Communicate(texto, voice=voz, rate=rate, pitch=pitch)
            with open(caminho_saida, "wb") as f_out:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f_out.write(chunk["data"])
                    elif chunk["type"] == "SentenceBoundary":
                        # offset e duration estão em 100ns (1s = 10_000_000)
                        start_s = round(chunk["offset"] / 10_000_000, 2)
                        dur_s = round(chunk["duration"] / 10_000_000, 2)
                        boundaries.append({
                            "start": start_s,
                            "end": round(start_s + dur_s, 2),
                            "duration": dur_s,
                            "text": chunk.get("text", "").strip()
                        })

        asyncio.run(_gerar())
        if os.path.exists(caminho_saida) and os.path.getsize(caminho_saida) > 1000:
            print(f"[gerador_audio] Audio neural brasileiro gerado com sucesso via Edge-TTS ({voz}): {caminho_saida}")
            
            # Salva metadados de boundaries com timestamps exatos de fala
            if boundaries:
                caminho_bound = caminho_saida.replace(".mp3", "_boundaries.json")
                try:
                    with open(caminho_bound, "w", encoding="utf-8") as fb:
                        json.dump(boundaries, fb, ensure_ascii=False, indent=2)
                    print(f"[gerador_audio] {len(boundaries)} marcações de frases salvas com precisão milimétrica em: {caminho_bound}")
                except Exception as eb:
                    print(f"[gerador_audio] Aviso ao salvar boundaries: {eb}")
            return True
    except Exception as e:
        print(f"[gerador_audio] Erro no Edge-TTS neural ({e}). Tentando fallback secundário...")

    return False


def sintetizar_audio_fallback(texto: str, caminho_saida: str) -> bool:
    """
    Sintetizador de contingência. Primeiro tenta a voz neural brasileira (Edge-TTS).
    Se não houver conexão, utiliza o subsistema SAPI nativo do Windows.
    """
    # 1. Primeira linha de contingência: Voz neural brasileira de alta fidelidade
    if sintetizar_audio_edge_tts(texto, caminho_saida):
        return True

    # 2. Segunda linha: TTS nativo do sistema operacional
    try:
        os.makedirs(os.path.dirname(caminho_saida), exist_ok=True)
        wav_temp = caminho_saida.replace(".mp3", "_temp.wav")
        texto_escapado = texto.replace('"', '""').replace("'", "''")

        ps_script = f"""
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SetOutputToWaveFile('{wav_temp}')
$synth.Speak('{texto_escapado}')
$synth.Dispose()
"""
        resultado = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True,
            text=True
        )

        if resultado.returncode == 0 and os.path.exists(wav_temp) and os.path.getsize(wav_temp) > 0:
            try:
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                subprocess.run(
                    [ffmpeg_exe, "-y", "-i", wav_temp, "-codec:a", "libmp3lame", "-qscale:a", "2", caminho_saida],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True
                )
                if os.path.exists(wav_temp):
                    os.remove(wav_temp)
                return True
            except Exception:
                if os.path.exists(caminho_saida):
                    os.remove(caminho_saida)
                os.rename(wav_temp, caminho_saida)
                return True

    except Exception as e:
        print(f"[gerador_audio] Erro no fallback TTS nativo: {e}")

    return False


def gerar_audio_elevenlabs(
    texto: str,
    caminho_saida: str,
    api_key: str,
    voice_id: str = DEFAULT_VOICE_ID,
    model_id: str = "eleven_multilingual_v2"
) -> bool:
    """Chama a API oficial da ElevenLabs para gerar áudio da narração."""
    url = f"{ELEVEN_API_URL}/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
    }
    payload = {
        "text": texto,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True
        }
    }

    resposta = requests.post(url, json=payload, headers=headers, timeout=120)

    if resposta.status_code == 200:
        with open(caminho_saida, "wb") as f:
            f.write(resposta.content)
        return True
    else:
        raise RuntimeError(f"ElevenLabs API retornou erro {resposta.status_code}: {resposta.text}")


def clonar_voz_elevenlabs(
    caminho_amostra: str,
    nome_voz: str = "Minha Voz DarkAI",
    api_key: Optional[str] = None
) -> str:
    """
    Realiza a clonagem instantânea de voz (Instant Voice Cloning) via ElevenLabs API (/v1/voices/add).
    
    Args:
        caminho_amostra: Caminho para o arquivo de áudio gravado (mp3 ou wav).
        nome_voz: Nome a ser atribuído à nova voz clonada.
        api_key: Chave da ElevenLabs (opcional, busca em ELEVENLABS_API_KEY).
        
    Returns:
        voice_id gerado pela ElevenLabs.
    """
    chave = api_key or os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not chave or "sua_chave" in chave.lower():
        raise ValueError("Chave secreta da ElevenLabs (iniciada com sk_) necessária para clonagem de voz.")

    if not os.path.exists(caminho_amostra):
        raise FileNotFoundError(f"Arquivo de amostra de áudio não encontrado: {caminho_amostra}")

    url = "https://api.elevenlabs.io/v1/voices/add"
    headers = {
        "xi-api-key": chave
    }

    nome_arq = os.path.basename(caminho_amostra)
    mime_type = "audio/mpeg" if nome_arq.lower().endswith(".mp3") else "audio/wav"

    with open(caminho_amostra, "rb") as f:
        files = {
            "files": (nome_arq, f, mime_type)
        }
        data = {
            "name": nome_voz,
            "description": "Voz clonada personalizada pelo criador para canal Dark no YouTube."
        }
        resposta = requests.post(url, headers=headers, data=data, files=files, timeout=60)

    if resposta.status_code in (200, 201):
        dados_resp = resposta.json()
        voice_id = dados_resp.get("voice_id")
        if not voice_id:
            raise RuntimeError(f"ElevenLabs não retornou voice_id: {dados_resp}")
        print(f"[gerador_audio] Voz clonada com sucesso! voice_id: {voice_id}")
        return voice_id
    else:
        raise RuntimeError(f"Erro ao clonar voz na ElevenLabs ({resposta.status_code}): {resposta.text}")


def usar_audio_proprio(caminho_arquivo_usuario: str, nome_base: Optional[str] = None) -> str:
    """
    Copia ou salva um áudio gravado diretamente pelo usuário para a pasta output/audios/.
    Permite usar 100% de locução humana própria, contornando qualquer penalidade de IA.
    
    Args:
        caminho_arquivo_usuario: Caminho do arquivo original gravado pelo usuário.
        nome_base: Prefixo do nome do arquivo salvo.
        
    Returns:
        Caminho do arquivo pronto em output/audios/.
    """
    import shutil
    if not os.path.exists(caminho_arquivo_usuario):
        raise FileNotFoundError(f"Arquivo de áudio não encontrado: {caminho_arquivo_usuario}")

    os.makedirs("output/audios", exist_ok=True)
    slug = nome_base or "audio_proprio_narracao"
    ext = os.path.splitext(caminho_arquivo_usuario)[1].lower() or ".mp3"
    caminho_destino = os.path.join("output", "audios", f"{slug}{ext}")

    shutil.copy2(caminho_arquivo_usuario, caminho_destino)
    print(f"[gerador_audio] Áudio próprio do usuário copiado para: {caminho_destino}")
    return caminho_destino


def gerar_audio(
    roteiro_dados: Dict[str, Any],
    api_key: Optional[str] = None,
    voice_id: Optional[str] = None,
    nome_base: Optional[str] = None,
    caminho_audio_proprio: Optional[str] = None
) -> str:
    """
    Gera o arquivo de áudio (.mp3) a partir do roteiro estruturado ou utiliza gravação própria.
    
    Args:
        roteiro_dados: Dicionário retornado por gerador_roteiro.py
        api_key: Chave ElevenLabs (opcional, busca em ELEVENLABS_API_KEY)
        voice_id: ID da voz ElevenLabs (opcional, busca em ELEVENLABS_VOICE_ID)
        nome_base: Nome base do arquivo de saída
        caminho_audio_proprio: Se fornecido, ignora TTS e usa o áudio gravado pelo usuário
        
    Returns:
        Caminho absoluto ou relativo do arquivo de áudio gerado.
    """
    titulo = roteiro_dados.get("titulo", "audio_narracao")
    slug = nome_base or sanitizar_nome_arquivo(titulo)

    # Caso o usuário tenha optado por gravação própria humana
    if caminho_audio_proprio and os.path.exists(caminho_audio_proprio):
        return usar_audio_proprio(caminho_audio_proprio, nome_base=slug)

    chave = api_key or os.getenv("ELEVENLABS_API_KEY", "").strip()
    voz = voice_id or os.getenv("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID).strip() or DEFAULT_VOICE_ID

    texto_completo = extrair_texto_narracao(roteiro_dados)
    if not texto_completo:
        raise ValueError("O roteiro fornecido não contém nenhuma narração válida.")

    os.makedirs("output/audios", exist_ok=True)
    caminho_saida = os.path.join("output", "audios", f"{slug}.mp3")

    # Se a voz selecionada for a Neural Brasileira, ou se a chave ElevenLabs não for do tipo secreta (sk_), usa Edge-TTS
    if voz.startswith("pt-BR-") or voz in ["antonio", "pt-BR-AntonioNeural", "neural_ptbr", "padrao", DEFAULT_VOICE_ID] or not chave.startswith("sk_"):
        voz_edge = voz if voz.startswith("pt-BR-") else "pt-BR-AntonioNeural"
        print(f"[gerador_audio] Sintetizando com Voz Neural Brasileira ({voz_edge})...")
        sucesso = sintetizar_audio_edge_tts(texto_completo, caminho_saida, voz=voz_edge)
        if sucesso:
            return caminho_saida
        print("[gerador_audio] Edge-TTS indisponível, tentando ElevenLabs ou fallback...")

    # Se o usuário escolheu voz clonada ou ElevenLabs e possui chave secreta válida
    if chave and chave.startswith("sk_"):
        try:
            print(f"[gerador_audio] Sintetizando áudio com ElevenLabs (Voz ID: {voz})...")
            sucesso = gerar_audio_elevenlabs(texto_completo, caminho_saida, chave, voz)
            print(f"[gerador_audio] Áudio ElevenLabs gerado com sucesso: {caminho_saida}")
        except Exception as e:
            print(f"[gerador_audio] Falha na chamada da ElevenLabs: {e}")
            print("[gerador_audio] Acionando sintetizador de áudio neural de contingência...")
            sucesso = sintetizar_audio_fallback(texto_completo, caminho_saida)
    else:
        sucesso = sintetizar_audio_fallback(texto_completo, caminho_saida)

    if not sucesso or not os.path.exists(caminho_saida):
        raise RuntimeError(f"Não foi possível gerar o áudio em: {caminho_saida}")

    return caminho_saida


if __name__ == "__main__":
    exemplo_roteiro = {
        "titulo": "Teste de Audio Canal Dark",
        "cenas": [
            {"cena_id": 1, "narracao": "Bem-vindos aos arquivos sombrios da história proibida."},
            {"cena_id": 2, "narracao": "O que você está prestes a descobrir nunca deveria ter sido revelado."}
        ]
    }
    caminho = gerar_audio(exemplo_roteiro)
    print(f"Áudio gerado em: {caminho}")
