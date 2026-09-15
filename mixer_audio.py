"""
Módulo para mixagem de áudio e música de fundo (BGM).
"""

import os
import subprocess
from typing import List, Dict, Optional
import imageio_ffmpeg
from google import genai

def listar_trilhas_disponiveis() -> List[Dict[str, str]]:
    """Lista todas as trilhas BGM disponíveis em assets/bgm/"""
    diretorio_bgm = os.path.join(os.path.dirname(__file__), "assets", "bgm")
    if not os.path.exists(diretorio_bgm):
        os.makedirs(diretorio_bgm, exist_ok=True)
        
    trilhas = []
    for arquivo in os.listdir(diretorio_bgm):
        if arquivo.lower().endswith((".mp3", ".wav", ".m4a")):
            caminho_completo = os.path.join(diretorio_bgm, arquivo)
            nome = os.path.splitext(arquivo)[0].replace("_", " ").title()
            
            # Tenta obter duração usando ffprobe
            duracao = 0.0
            try:
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                ffprobe_exe = os.path.join(os.path.dirname(ffmpeg_exe), "ffprobe.exe")
                if not os.path.exists(ffprobe_exe):
                    ffprobe_exe = "ffprobe"
                
                cmd = [
                    ffprobe_exe, "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", caminho_completo
                ]
                saida = subprocess.check_output(cmd, text=True, stderr=subprocess.PIPE).strip()
                duracao = float(saida)
            except Exception:
                pass
                
            trilhas.append({
                "id": os.path.splitext(arquivo)[0],
                "nome": nome,
                "arquivo": caminho_completo,
                "duracao": duracao
            })
    return trilhas

def selecionar_trilha_automatica(tema: str, nicho: str = "", api_key: Optional[str] = None) -> Optional[str]:
    """Usa Gemini para selecionar a trilha mais adequada ao tema/nicho"""
    trilhas = listar_trilhas_disponiveis()
    if not trilhas:
        return None
        
    if len(trilhas) == 1:
        return trilhas[0]["arquivo"]
        
    try:
        chave = api_key or os.environ.get("GEMINI_API_KEY")
        if not chave:
            return trilhas[0]["arquivo"]
            
        client = genai.Client(api_key=chave)
        
        opcoes = "\n".join([f"- {t['id']}: {t['nome']}" for t in trilhas])
        prompt = f"""
Você é um diretor de áudio. Escolha a melhor trilha de fundo para um vídeo.
Tema do vídeo: {tema}
Nicho: {nicho}

Trilhas disponíveis:
{opcoes}

Retorne apenas o 'id' da trilha escolhida.
"""
        resposta = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        
        id_escolhido = resposta.text.strip()
        
        for trilha in trilhas:
            if trilha["id"].lower() == id_escolhido.lower() or id_escolhido.lower() in trilha["id"].lower():
                return trilha["arquivo"]
                
        return trilhas[0]["arquivo"]
    except Exception as e:
        print(f"Erro ao selecionar trilha automaticamente: {e}")
        return trilhas[0]["arquivo"]

def obter_duracao(caminho_arquivo: str) -> float:
    """Obtém a duração de um arquivo de áudio."""
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        ffprobe_exe = os.path.join(os.path.dirname(ffmpeg_exe), "ffprobe.exe")
        if not os.path.exists(ffprobe_exe):
            ffprobe_exe = "ffprobe"
            
        cmd = [
            ffprobe_exe, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", caminho_arquivo
        ]
        saida = subprocess.check_output(cmd, text=True, stderr=subprocess.PIPE).strip()
        return float(saida)
    except Exception:
        return 0.0

def mixar_audio_com_bgm(
    caminho_narracao: str,
    caminho_bgm: str,
    caminho_saida: str,
    volume_bgm_db: float = -18.0,
    fade_in_s: float = 2.0,
    fade_out_s: float = 3.0,
    ducking: bool = True
) -> str:
    """Mixa narração com trilha de fundo usando FFmpeg"""
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    
    duracao_narracao = obter_duracao(caminho_narracao)
    inicio_fade_out = max(0.0, duracao_narracao - fade_out_s) if duracao_narracao > 0 else 0
    
    # Filtro complexo para ajustar volume, aplicar fade e mixar
    filtro = (
        f"[1:a]volume={volume_bgm_db}dB,"
        f"afade=t=in:st=0:d={fade_in_s},"
        f"afade=t=out:st={inicio_fade_out}:d={fade_out_s}[bgm];"
        f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=3"
    )
    
    cmd = [
        ffmpeg_exe, "-y",
        "-i", caminho_narracao,
        "-stream_loop", "-1",
        "-i", caminho_bgm,
        "-filter_complex", filtro,
        "-ac", "2",
        caminho_saida
    ]
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return caminho_saida
    except subprocess.CalledProcessError as e:
        erro = e.stderr.decode('utf-8', errors='ignore') if e.stderr else "Erro desconhecido"
        print(f"Erro no FFmpeg ao mixar: {erro}")
        raise RuntimeError("Falha ao mixar áudio com BGM")
