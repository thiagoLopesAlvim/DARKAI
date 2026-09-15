"""
Módulo editor_video.py
Uso do MoviePy para unir o áudio com as marcações de tempo.
Gera um MP4 com telas de cores sólidas temáticas (placeholders para Fase 1) e legendas
estilizadas de alta visibilidade renderizadas diretamente via Pillow (sem ImageMagick).
"""

import os
import re
import numpy as np
from typing import Optional, Dict, Any, List, Tuple
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

load_dotenv()

# Paleta estética de cores sombrias para Canal Dark
PALETA_CORES_DARK = [
    (13, 27, 42),    # Deep Navy
    (27, 38, 59),    # Dark Slate
    (32, 14, 28),    # Dark Wine
    (21, 32, 43),    # Midnight Charcoal
    (18, 30, 24),    # Dark Forest Pine
    (35, 23, 10),    # Dark Umber
    (25, 20, 36),    # Deep Violet Night
    (30, 30, 30),    # Obsidian Grey
]

# Presets de Animação de Câmera Flow Motion (Ken Burns Dinâmico)
MOTIONS_FLOW = [
    ("zoom_in", lambda d, w, h: f"zoompan=z='min(zoom+0.0015,1.25)':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d={d}:s={w}x{h}:fps=24"),
    ("pan_right", lambda d, w, h: f"zoompan=z=1.15:x='max(0,min(iw-iw/zoom,(on/{d})*(iw-iw/zoom)))':y='(ih-ih/zoom)/2':d={d}:s={w}x{h}:fps=24"),
    ("zoom_out", lambda d, w, h: f"zoompan=z='if(lte(zoom,1.0),1.25,max(1.0,zoom-0.0015))':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d={d}:s={w}x{h}:fps=24"),
    ("pan_left", lambda d, w, h: f"zoompan=z=1.15:x='max(0,min(iw-iw/zoom,(1-(on/{d}))*(iw-iw/zoom)))':y='(ih-ih/zoom)/2':d={d}:s={w}x{h}:fps=24"),
    ("tilt_down", lambda d, w, h: f"zoompan=z=1.15:x='(iw-iw/zoom)/2':y='max(0,min(ih-ih/zoom,(on/{d})*(ih-ih/zoom)))':d={d}:s={w}x{h}:fps=24"),
    ("tilt_up", lambda d, w, h: f"zoompan=z=1.15:x='(iw-iw/zoom)/2':y='max(0,min(ih-ih/zoom,(1-(on/{d}))*(ih-ih/zoom)))':d={d}:s={w}x{h}:fps=24"),
]

_CACHE_GPU_INFO = None

def detectar_aceleracao_gpu() -> Dict[str, Any]:
    """
    Detecta se há suporte a aceleração por hardware via GPU dedicada (NVIDIA NVENC).
    Retorna metadados do dispositivo e encoder recomendado.
    """
    global _CACHE_GPU_INFO
    if _CACHE_GPU_INFO is not None:
        return _CACHE_GPU_INFO

    gpu_info = {
        "disponivel": False,
        "gpu_nome": "CPU (Sem aceleração dedicada)",
        "encoder": "libx264",
        "tipo": "cpu"
    }
    try:
        import imageio_ffmpeg
        import subprocess
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        
        # Testa se o encoder h264_nvenc funciona na prática
        cmd_teste = [
            exe, "-y", "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.2",
            "-c:v", "h264_nvenc", "-f", "null", "-"
        ]
        res = subprocess.run(cmd_teste, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=4)
        if res.returncode == 0:
            nome_gpu = "NVIDIA GeForce GPU"
            try:
                out_name = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=3
                )
                if out_name.returncode == 0 and out_name.stdout.strip():
                    nome_gpu = out_name.stdout.strip().splitlines()[0]
            except Exception:
                pass

            gpu_info = {
                "disponivel": True,
                "gpu_nome": nome_gpu,
                "encoder": "h264_nvenc",
                "tipo": "nvidia"
            }
    except Exception as e:
        print(f"[editor_video] Verificação de GPU falhou ({e}). Usando CPU.")

    _CACHE_GPU_INFO = gpu_info
    return gpu_info


def sanitizar_nome_arquivo(texto: str) -> str:
    """Converte um texto em uma string segura para nome de arquivo."""
    texto = texto.lower()
    texto = re.sub(r'[^\w\s-]', '', texto)
    return re.sub(r'[-\s]+', '_', texto).strip('_')[:50]


def obter_fonte(tamanho: int) -> ImageFont.ImageFont:
    """Obtém uma fonte do sistema Windows com fallback gracioso."""
    fontes_candidatas = [
        "C:/Windows/Fonts/arialbd.ttf",   # Arial Bold
        "C:/Windows/Fonts/arial.ttf",     # Arial
        "C:/Windows/Fonts/segoeuib.ttf",  # Segoe UI Bold
        "C:/Windows/Fonts/calibrib.ttf",  # Calibri Bold
        "arial.ttf"
    ]
    for fonte_path in fontes_candidatas:
        try:
            return ImageFont.truetype(fonte_path, tamanho)
        except Exception:
            continue
    return ImageFont.load_default()


def quebrar_linhas_texto(texto: str, draw: ImageDraw.ImageDraw, fonte: ImageFont.ImageFont, max_largura: int) -> List[str]:
    """Quebra o texto em múltiplas linhas respeitando a largura máxima."""
    palavras = texto.split()
    linhas = []
    linha_atual = []

    for palavra in palavras:
        tentativa = " ".join(linha_atual + [palavra])
        bbox = draw.textbbox((0, 0), tentativa, font=fonte)
        largura = bbox[2] - bbox[0]
        if largura <= max_largura or not linha_atual:
            linha_atual.append(palavra)
        else:
            linhas.append(" ".join(linha_atual))
            linha_atual = [palavra]

    if linha_atual:
        linhas.append(" ".join(linha_atual))
    return linhas


def carregar_e_ajustar_imagem(
    caminho_imagem: str,
    largura: int,
    altura: int,
    usar_ambient_blur: bool = True
) -> Image.Image:
    """
    Carrega uma imagem e ajusta para a resolução do vídeo.
    Se o vídeo for vertical (9:16) e a imagem for horizontal (16:9), aplica
    automaticamente o efeito Ambient Blur cinematográfico (fundo desfocado e imagem nítida ao centro).
    """
    from PIL import ImageOps, ImageFilter, ImageEnhance
    with Image.open(caminho_imagem) as img:
        img_rgb = img.convert("RGB")
        img_w, img_h = img_rgb.size

        # Caso vertical 9:16 com imagem horizontal
        if altura > largura and (img_w / img_h) > 1.1 and usar_ambient_blur:
            # 1. Fundo esticado e com desfoque gaussiano cinematográfico
            fundo = ImageOps.fit(img_rgb, (largura, altura), method=Image.Resampling.LANCZOS)
            fundo = fundo.filter(ImageFilter.GaussianBlur(radius=30))
            enhancer = ImageEnhance.Brightness(fundo)
            fundo = enhancer.enhance(0.38)  # Escurece para destacar o foco principal

            # 2. Imagem central nítida mantendo proporção original
            proporcao = img_w / img_h
            centro_w = largura
            centro_h = int(largura / proporcao)
            img_centro = img_rgb.resize((centro_w, centro_h), Image.Resampling.LANCZOS)

            # 3. Cola a imagem nítida centralizada
            y_offset = (altura - centro_h) // 2
            fundo.paste(img_centro, (0, y_offset))
            return fundo
        else:
            return ImageOps.fit(img_rgb, (largura, altura), method=Image.Resampling.LANCZOS)


def criar_frame_legenda(
    texto: str,
    largura_video: int,
    altura_video: int,
    imagem_fundo: Optional[Image.Image] = None,
    cor_bg: Tuple[int, int, int] = (13, 27, 42),
    cena_info: Optional[str] = None
) -> np.ndarray:
    """
    Cria uma imagem RGB direta sobre a imagem de fundo ou cor sólida da cena.
    Ao usar RGB em vez de RGBA, eliminamos a máscara de transparência no MoviePy,
    aumentando a velocidade de renderização em mais de 10x!
    """
    if imagem_fundo is not None:
        imagem = imagem_fundo.copy()
    else:
        imagem = Image.new("RGB", (largura_video, altura_video), cor_bg)

    draw = ImageDraw.Draw(imagem)

    is_vertical = (altura_video > largura_video)

    # Proporção da fonte baseada na resolução e formato
    if is_vertical:
        # Padrão Shorts / TikTok: fonte maior para telas verticais de celular
        tam_fonte = max(34, int(largura_video * 0.052))
    else:
        tam_fonte = max(24, int(altura_video * 0.045))

    fonte = obter_fonte(tam_fonte)
    fonte_cena = obter_fonte(max(16, int(altura_video * 0.022)))

    # Quebra o texto respeitando a margem lateral
    max_largura = int(largura_video * 0.85)
    linhas = quebrar_linhas_texto(texto.upper(), draw, fonte, max_largura)

    # Calcula altura total do bloco de texto
    altura_linhas = []
    for linha in linhas:
        bbox = draw.textbbox((0, 0), linha, font=fonte)
        altura_linhas.append(bbox[3] - bbox[1])
    espacamento = int(tam_fonte * 0.25)
    altura_total = sum(altura_linhas) + espacamento * (len(linhas) - 1)

    # Posicionamento da legenda
    if is_vertical:
        # Zona segura de Shorts (evita sobreposição com botões do YouTube/TikTok no rodapé)
        y_pos = int(altura_video * 0.62) - (altura_total // 2)
    else:
        y_pos = int(altura_video * 0.76) - (altura_total // 2)

    # Renderiza cada linha com contorno preto grosso
    for idx, linha in enumerate(linhas):
        bbox = draw.textbbox((0, 0), linha, font=fonte)
        larg_linha = bbox[2] - bbox[0]
        x_pos = (largura_video - larg_linha) // 2

        stroke_width = max(2, int(tam_fonte * 0.09))
        draw.text(
            (x_pos, y_pos),
            linha,
            font=fonte,
            fill=(255, 225, 53),  # Amarelo vibrante de alta retenção
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0)
        )
        y_pos += altura_linhas[idx] + espacamento

    # Se houver marcador de cena/prompt no topo, desenha um badge informativo
    if cena_info:
        badge_linhas = quebrar_linhas_texto(cena_info, draw, fonte_cena, int(largura_video * 0.9))
        y_badge = int(altura_video * 0.05)
        for b_linha in badge_linhas[:2]:
            b_box = draw.textbbox((0, 0), b_linha, font=fonte_cena)
            b_larg = b_box[2] - b_box[0]
            b_x = (largura_video - b_larg) // 2
            padding = 6
            draw.rectangle(
                [b_x - padding, y_badge - padding, b_x + b_larg + padding, y_badge + (b_box[3] - b_box[1]) + padding],
                fill=(10, 10, 10)
            )
            draw.text((b_x, y_badge), b_linha, font=fonte_cena, fill=(210, 210, 210))
            y_badge += (b_box[3] - b_box[1]) + 8

    return np.array(imagem)


def criar_frame_solido(cor_rgb: Tuple[int, int, int], largura: int, altura: int) -> np.ndarray:
    """Cria um frame RGB sólido."""
    return np.full((altura, largura, 3), cor_rgb, dtype=np.uint8)


def formatar_timestamp_ass(segundos: float) -> str:
    """Converte segundos para o formato H:MM:SS.cs do ASS."""
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = int(segundos % 60)
    cs = int(round((segundos - int(segundos)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def quebrar_texto_ass(texto: str, max_chars: int = 38) -> str:
    """Quebra o texto de legenda em múltiplas linhas usando \\N."""
    texto_limpo = texto.replace("{", "").replace("}", "").strip()
    palavras = texto_limpo.split()
    linhas = []
    linha_atual = []
    tam = 0
    for p in palavras:
        if tam + len(p) + 1 <= max_chars or not linha_atual:
            linha_atual.append(p)
            tam += len(p) + 1
        else:
            linhas.append(" ".join(linha_atual))
            linha_atual = [p]
            tam = len(p)
    if linha_atual:
        linhas.append(" ".join(linha_atual))
    return r"\N".join(linhas)


def renderizar_video_ffmpeg_nvenc(
    caminho_audio: str,
    dados_sincronizacao: Dict[str, Any],
    roteiro_dados: Optional[Dict[str, Any]] = None,
    aspect_ratio: str = "16:9",
    caminho_saida: Optional[str] = None,
    callback_progresso: Optional[Any] = None,
    imagens_cenas: Optional[Dict[int, str]] = None,
    forcar_cpu: bool = False,
    ativar_flow_motion: bool = True,
    transicao_duracao: float = 0.5,
    transicao_tipo: str = 'fade'
) -> str:
    """
    Renderização direta via FFmpeg com Aceleração por Hardware GPU (NVIDIA NVENC).
    Com suporte a Flow Motion Engine (animações de câmera cinematográficas estilo Google Vids/Flow).
    Renderiza vídeos Full HD em segundos (~40x a 60x mais rápido que MoviePy em CPU).
    """
    import subprocess
    import imageio_ffmpeg

    exe = imageio_ffmpeg.get_ffmpeg_exe()

    # 1. Resolução
    is_vertical = (aspect_ratio == "9:16")
    if is_vertical:
        largura, altura = 1080, 1920
    else:
        largura, altura = 1920, 1080

    cenas_ts = dados_sincronizacao.get("cenas_timestamps", [])
    legendas_ts = dados_sincronizacao.get("legendas_timestamps", [])
    duracao_total = dados_sincronizacao.get("duracao_audio") or dados_sincronizacao.get("duracao_total")

    if not duracao_total or duracao_total <= 0:
        duracao_total = 10.0

    # Nome do arquivo de saída
    if not caminho_saida:
        os.makedirs("output/videos", exist_ok=True)
        nome_base = os.path.splitext(os.path.basename(caminho_audio))[0]
        caminho_saida = os.path.join("output", "videos", f"{nome_base}_{aspect_ratio.replace(':', 'x')}.mp4")

    os.makedirs("temp/nvenc_frames", exist_ok=True)
    if ativar_flow_motion:
        os.makedirs("temp/nvenc_clips", exist_ok=True)

    # 2. Detecção e Seleção do Encoder de Hardware
    gpu_info = detectar_aceleracao_gpu()
    usar_gpu = (gpu_info.get("disponivel", False) and not forcar_cpu)

    if usar_gpu:
        encoder_args = ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "23"]
        encoder_nome = f"NVIDIA NVENC ({gpu_info.get('gpu_nome', 'GPU')})"
    else:
        encoder_args = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "23"]
        encoder_nome = "CPU libx264 (ultrafast)"

    # 3. Presets de Animação de Câmera Flow Motion (Ken Burns Dinâmico)
    MOTIONS_FLOW = [
        ("zoom_in", lambda d, w, h: f"zoompan=z='min(zoom+0.0015,1.25)':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d={d}:s={w}x{h}:fps=24"),
        ("pan_right", lambda d, w, h: f"zoompan=z=1.15:x='max(0,min(iw-iw/zoom,(on/{d})*(iw-iw/zoom)))':y='(ih-ih/zoom)/2':d={d}:s={w}x{h}:fps=24"),
        ("zoom_out", lambda d, w, h: f"zoompan=z='if(lte(zoom,1.0),1.25,max(1.0,zoom-0.0015))':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':d={d}:s={w}x{h}:fps=24"),
        ("pan_left", lambda d, w, h: f"zoompan=z=1.15:x='max(0,min(iw-iw/zoom,(1-(on/{d}))*(iw-iw/zoom)))':y='(ih-ih/zoom)/2':d={d}:s={w}x{h}:fps=24"),
        ("tilt_down", lambda d, w, h: f"zoompan=z=1.15:x='(iw-iw/zoom)/2':y='max(0,min(ih-ih/zoom,(on/{d})*(ih-ih/zoom)))':d={d}:s={w}x{h}:fps=24"),
        ("tilt_up", lambda d, w, h: f"zoompan=z=1.15:x='(iw-iw/zoom)/2':y='max(0,min(ih-ih/zoom,(1-(on/{d}))*(ih-ih/zoom)))':d={d}:s={w}x{h}:fps=24"),
    ]

    # 4. Geração dos frames ou clipes animados de cada cena
    if not cenas_ts:
        cenas_ts = [{
            "cena_id": 1,
            "start": 0.0,
            "end": duracao_total,
            "visual_prompt": "Cena 1"
        }]

    concat_lines = []
    if not ativar_flow_motion:
        concat_lines.append("ffconcat version 1.0")

    clips_gerados = []
    duracoes_clips = []

    for idx, c in enumerate(cenas_ts):
        cid = c.get("cena_id", idx + 1)
        p_img = None
        if imagens_cenas:
            p_img = imagens_cenas.get(cid) or imagens_cenas.get(str(cid))

        frame_path = os.path.join("temp", "nvenc_frames", f"frame_c{cid}_{largura}x{altura}.jpg")

        if p_img and os.path.exists(p_img):
            try:
                img_ajustada = carregar_e_ajustar_imagem(p_img, largura, altura, usar_ambient_blur=True)
                img_ajustada.save(frame_path, quality=93)
            except Exception as e:
                print(f"[editor_video] Aviso ao ajustar imagem {p_img}: {e}")
                im_cor = criar_frame_solido(PALETA_CORES_DARK[idx % len(PALETA_CORES_DARK)], largura, altura)
                Image.fromarray(im_cor).save(frame_path, quality=93)
        else:
            cor = PALETA_CORES_DARK[idx % len(PALETA_CORES_DARK)]
            im_cor = criar_frame_solido(cor, largura, altura)
            img_pill = Image.fromarray(im_cor)
            draw = ImageDraw.Draw(img_pill)
            f_badge = obter_fonte(max(18, int(altura * 0.025)))
            prompt_texto = c.get("visual_prompt", f"CENA {cid}")
            prompt_resumido = f"CENA {cid} | {prompt_texto[:70]}..." if len(prompt_texto) > 70 else f"CENA {cid} | {prompt_texto}"
            draw.text((int(largura * 0.05), int(altura * 0.05)), prompt_resumido, font=f_badge, fill=(210, 210, 210))
            img_pill.save(frame_path, quality=93)

        start = float(c.get("start", 0.0))
        end = float(c.get("end", start + 5.0))
        dur_cena = max(0.5, end - start)
        
        # Ajuste de duração para o xfade
        is_last = (idx == len(cenas_ts) - 1)
        dur_clip = dur_cena
        if transicao_duracao > 0 and ativar_flow_motion and not is_last:
            dur_clip += transicao_duracao
            
        num_frames = max(24, int(dur_clip * 24))

        if ativar_flow_motion:
            nome_m, gen_vf = MOTIONS_FLOW[idx % len(MOTIONS_FLOW)]
            vf_flow = gen_vf(num_frames, largura, altura)
            clip_path = os.path.join("temp", "nvenc_clips", f"clip_c{cid}_{nome_m}_{largura}x{altura}.mp4")

            if callback_progresso:
                prog_cena = round(0.70 + (idx / len(cenas_ts)) * 0.15, 2)
                callback_progresso(prog_cena, f"Gerando animação Flow da Cena {idx+1}/{len(cenas_ts)} ({nome_m.replace('_', ' ').title()})...")

            cmd_clip = [
                exe, "-y", "-loop", "1", "-i", frame_path,
                "-vf", vf_flow,
                *encoder_args,
                "-t", f"{dur_clip:.3f}",
                "-pix_fmt", "yuv420p",
                clip_path
            ]
            r_clip = subprocess.run(cmd_clip, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if r_clip.returncode == 0 and os.path.exists(clip_path):
                abs_clip_esc = os.path.abspath(clip_path).replace("\\", "/")
                concat_lines.append(f"file '{abs_clip_esc}'")
                clips_gerados.append(clip_path)
                duracoes_clips.append(dur_clip)
            else:
                abs_frame_esc = os.path.abspath(frame_path).replace("\\", "/")
                concat_lines.append(f"file '{abs_frame_esc}'")
                concat_lines.append(f"duration {dur_clip:.3f}")
                clips_gerados.append(frame_path)
                duracoes_clips.append(dur_clip)
        else:
            abs_frame_esc = os.path.abspath(frame_path).replace("\\", "/")
            concat_lines.append(f"file '{abs_frame_esc}'")
            concat_lines.append(f"duration {dur_clip:.3f}")
            clips_gerados.append(frame_path)
            duracoes_clips.append(dur_clip)

    if not ativar_flow_motion and len(concat_lines) >= 3:
        concat_lines.append(concat_lines[-2])

    concat_file_path = os.path.join("temp", f"concat_{aspect_ratio.replace(':', 'x')}.txt")
    with open(concat_file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(concat_lines) + "\n")

    # 5. Geração do arquivo ASS de legendas estilizadas
    ass_file_path = os.path.join("temp", f"legendas_{aspect_ratio.replace(':', 'x')}.ass")
    tem_legendas = bool(legendas_ts)

    if tem_legendas:
        tam_fonte = 58 if is_vertical else 46
        borda = 4.0 if is_vertical else 3.5
        margin_v = int(altura * 0.34) if is_vertical else int(altura * 0.12)
        max_chars = 24 if is_vertical else 38

        ass_content = [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {largura}",
            f"PlayResY: {altura}",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: DarkSubtitle,Arial,{tam_fonte},&H0035E1FF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{borda},1,2,40,40,{margin_v},1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
        ]

        for leg in legendas_ts:
            st_t = formatar_timestamp_ass(float(leg.get("start", 0.0)))
            et_t = formatar_timestamp_ass(float(leg.get("end", 1.0)))
            txt = quebrar_texto_ass(leg.get("text", "").upper(), max_chars=max_chars)
            if txt:
                ass_content.append(f"Dialogue: 0,{st_t},{et_t},DarkSubtitle,,0,0,0,,{txt}")

        with open(ass_file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(ass_content) + "\n")

    # 6. Montagem dos filtros de vídeo e pipeline FFmpeg
    rel_concat = concat_file_path.replace("\\", "/")
    rel_ass = ass_file_path.replace("\\", "/")

    usar_xfade = transicao_duracao > 0 and ativar_flow_motion and all(c.endswith('.mp4') for c in clips_gerados) and len(clips_gerados) > 1

    if usar_xfade:
        inputs_args = []
        for clip in clips_gerados:
            inputs_args.extend(["-i", clip])
        
        audio_idx = len(clips_gerados)
        inputs_args.extend(["-i", caminho_audio])
        
        filter_chains = []
        current_offset = duracoes_clips[0] - transicao_duracao
        last_out = "[0:v]"
        
        for i in range(1, len(clips_gerados)):
            out_name = f"[v{i}]" if i < len(clips_gerados) - 1 else "[outv]"
            filter_chains.append(f"{last_out}[{i}:v]xfade=transition={transicao_tipo}:duration={transicao_duracao}:offset={current_offset:.3f}{out_name}")
            last_out = out_name
            current_offset += duracoes_clips[i] - transicao_duracao
        
        filter_complex_str = ";".join(filter_chains)
        
        if tem_legendas and os.path.exists(ass_file_path):
            filter_complex_str += f";[outv]fps=24,subtitles={rel_ass}[finalv]"
            map_v = "[finalv]"
        else:
            filter_complex_str += f";[outv]fps=24[finalv]"
            map_v = "[finalv]"
            
        cmd = [
            exe, "-y",
            *inputs_args,
            "-filter_complex", filter_complex_str,
            "-map", map_v,
            "-map", f"{audio_idx}:a",
            *encoder_args,
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            caminho_saida
        ]
        motor_label = f"{encoder_nome} + Flow Motion + Xfade"
    else:
        if tem_legendas and os.path.exists(ass_file_path):
            vf_param = f"fps=24,subtitles={rel_ass}"
        else:
            vf_param = "fps=24"

        cmd = [
            exe, "-y",
            "-f", "concat", "-safe", "0", "-i", rel_concat,
            "-i", caminho_audio,
            "-vf", vf_param,
            *encoder_args,
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-shortest",
            caminho_saida
        ]
        motor_label = f"{encoder_nome} + Flow Motion" if ativar_flow_motion else encoder_nome

    print(f"[editor_video] Iniciando renderização FFmpeg ({motor_label})...")
    print(f"[editor_video] Destino: {caminho_saida} ({largura}x{altura}, {duracao_total:.1f}s)")

    if callback_progresso:
        callback_progresso(0.85, f"Iniciando renderização acelerada ({motor_label})...")

    # 6. Execução com monitoramento de progresso em tempo real
    processo = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        universal_newlines=True
    )

    ultimo_pct = -1
    for linha in processo.stderr:
        m = re.search(r"time=(\d{2}):(\d{2}):(\d{2}\.\d+)", linha)
        if m:
            h, mn, s = m.groups()
            tempo_seg = int(h) * 3600 + int(mn) * 60 + float(s)
            pct = min(1.0, tempo_seg / duracao_total)
            pct_int = int(pct * 100)
            if pct_int != ultimo_pct and (pct_int % 5 == 0 or pct_int == 100):
                ultimo_pct = pct_int
                if callback_progresso:
                    prog_global = round(0.85 + (pct * 0.14), 2)
                    callback_progresso(prog_global, f"Renderizando vídeo ({encoder_nome}): {pct_int}% ({tempo_seg:.1f}s / {duracao_total:.1f}s)")

    processo.wait()

    if processo.returncode == 0 and os.path.exists(caminho_saida) and os.path.getsize(caminho_saida) > 5000:
        sz_mb = os.path.getsize(caminho_saida) / (1024 * 1024)
        print(f"[editor_video] [OK] Vídeo renderizado com sucesso via {encoder_nome} ({sz_mb:.1f} MB): {caminho_saida}")
        if callback_progresso:
            callback_progresso(1.00, f"Renderização concluída ({sz_mb:.1f} MB) via {encoder_nome}!")
        return caminho_saida

    # Se falhar via NVENC por erro de hardware, tenta CPU via FFmpeg antes de recorrer ao MoviePy
    if usar_gpu:
        print("[editor_video] Falha no NVENC. Tentando renderização FFmpeg via CPU (libx264)...")
        return renderizar_video_ffmpeg_nvenc(
            caminho_audio=caminho_audio,
            dados_sincronizacao=dados_sincronizacao,
            roteiro_dados=roteiro_dados,
            aspect_ratio=aspect_ratio,
            caminho_saida=caminho_saida,
            callback_progresso=callback_progresso,
            imagens_cenas=imagens_cenas,
            forcar_cpu=True
        )

    raise RuntimeError(f"FFmpeg falhou com código {processo.returncode}")


def renderizar_video_moviepy(
    caminho_audio: str,
    dados_sincronizacao: Dict[str, Any],
    roteiro_dados: Optional[Dict[str, Any]] = None,
    aspect_ratio: str = "16:9",
    caminho_saida: Optional[str] = None,
    callback_progresso: Optional[Any] = None,
    imagens_cenas: Optional[Dict[int, str]] = None,
    forcar_cpu: bool = False,
    ativar_flow_motion: bool = True,
    transicao_duracao: float = 0.5,
    transicao_tipo: str = 'fade'
) -> str:
    """
    Renderiza o vídeo completo. Prioriza o motor nativo acelerado FFmpeg NVENC (10x a 60x mais rápido),
    com animação de câmera Flow Motion e fallback automático para MoviePy se necessário.
    """
    try:
        return renderizar_video_ffmpeg_nvenc(
            caminho_audio=caminho_audio,
            dados_sincronizacao=dados_sincronizacao,
            roteiro_dados=roteiro_dados,
            aspect_ratio=aspect_ratio,
            caminho_saida=caminho_saida,
            callback_progresso=callback_progresso,
            imagens_cenas=imagens_cenas,
            forcar_cpu=forcar_cpu,
            ativar_flow_motion=ativar_flow_motion,
            transicao_duracao=transicao_duracao,
            transicao_tipo=transicao_tipo
        )
    except Exception as e_nvenc:
        print(f"[editor_video] Aviso: Motor FFmpeg direto falhou ({e_nvenc}). Recorrendo ao MoviePy...")
        return _renderizar_video_moviepy_legado(
            caminho_audio=caminho_audio,
            dados_sincronizacao=dados_sincronizacao,
            roteiro_dados=roteiro_dados,
            aspect_ratio=aspect_ratio,
            caminho_saida=caminho_saida,
            callback_progresso=callback_progresso,
            imagens_cenas=imagens_cenas
        )


def _renderizar_video_moviepy_legado(
    caminho_audio: str,
    dados_sincronizacao: Dict[str, Any],
    roteiro_dados: Optional[Dict[str, Any]] = None,
    aspect_ratio: str = "16:9",
    caminho_saida: Optional[str] = None,
    callback_progresso: Optional[Any] = None,
    imagens_cenas: Optional[Dict[int, str]] = None
) -> str:
    """
    Renderizador legado MoviePy de contingência.
    """
    import moviepy as mp
    from moviepy import AudioFileClip, ImageClip, CompositeVideoClip

    if aspect_ratio == "9:16":
        largura, altura = 1080, 1920
    else:
        largura, altura = 1920, 1080

    cenas_ts = dados_sincronizacao.get("cenas_timestamps", [])
    legendas_ts = dados_sincronizacao.get("legendas_timestamps", [])
    duracao_total = dados_sincronizacao.get("duracao_audio") or dados_sincronizacao.get("duracao_total")

    audio_clip = AudioFileClip(caminho_audio)
    if not duracao_total or duracao_total <= 0:
        duracao_total = audio_clip.duration

    if not caminho_saida:
        os.makedirs("output/videos", exist_ok=True)
        nome_base = os.path.splitext(os.path.basename(caminho_audio))[0]
        caminho_saida = os.path.join("output", "videos", f"{nome_base}_{aspect_ratio.replace(':', 'x')}.mp4")

    def set_clip_time(clip, start, duration):
        if hasattr(clip, "with_start"):
            return clip.with_start(start).with_duration(duration)
        else:
            return clip.set_start(start).set_duration(duration)

    clips_cenas = []
    imagens_cenas_pil: Dict[int, Image.Image] = {}
    if imagens_cenas:
        for cid, path_img in imagens_cenas.items():
            if path_img and os.path.exists(path_img):
                try:
                    imagens_cenas_pil[int(cid)] = carregar_e_ajustar_imagem(path_img, largura, altura)
                except Exception as e:
                    print(f"[editor_video] Falha ao carregar imagem da Cena {cid}: {e}")

    if not cenas_ts:
        cenas_ts = [{"cena_id": 1, "start": 0.0, "end": duracao_total, "visual_prompt": "Cena 1"}]

    for idx, c in enumerate(cenas_ts):
        start = float(c.get("start", 0.0))
        end = float(c.get("end", duracao_total))
        duracao_cena = max(0.2, end - start)
        cena_id = c.get("cena_id", idx + 1)

        if cena_id in imagens_cenas_pil:
            frame_bg = np.array(imagens_cenas_pil[cena_id])
        else:
            cor = PALETA_CORES_DARK[idx % len(PALETA_CORES_DARK)]
            frame_bg = criar_frame_solido(cor, largura, altura)

        bg_clip = ImageClip(frame_bg)
        bg_clip = set_clip_time(bg_clip, start, duracao_cena)
        clips_cenas.append(bg_clip)

    clips_legendas = []
    for leg in legendas_ts:
        start_leg = float(leg.get("start", 0.0))
        end_leg = float(leg.get("end", start_leg + 1.0))
        duracao_leg = max(0.2, end_leg - start_leg)
        texto = leg.get("text", "").strip()
        if not texto:
            continue

        cena_id = leg.get("cena_id", 1)
        img_fundo = imagens_cenas_pil.get(cena_id)
        cor_cena = PALETA_CORES_DARK[max(0, cena_id - 1) % len(PALETA_CORES_DARK)]
        frame_legenda_rgb = criar_frame_legenda(
            texto=texto,
            largura_video=largura,
            altura_video=altura,
            imagem_fundo=img_fundo,
            cor_bg=cor_cena
        )
        leg_clip = ImageClip(frame_legenda_rgb)
        leg_clip = set_clip_time(leg_clip, start_leg, duracao_leg)
        clips_legendas.append(leg_clip)

    todos_os_clips = clips_cenas + clips_legendas
    video_final = CompositeVideoClip(todos_os_clips, size=(largura, altura))

    if hasattr(video_final, "with_duration"):
        video_final = video_final.with_duration(duracao_total)
        video_final = video_final.with_audio(audio_clip)
    else:
        video_final = video_final.set_duration(duracao_total)
        video_final = video_final.set_audio(audio_clip)

    print(f"[editor_video] Renderizando via MoviePy CPU...")
    video_final.write_videofile(
        caminho_saida,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=4
    )

    audio_clip.close()
    video_final.close()
    return caminho_saida


if __name__ == "__main__":
    print("Módulo editor_video pronto.")
