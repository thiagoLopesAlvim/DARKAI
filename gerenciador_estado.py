"""
Módulo gerenciador_estado.py
Responsável pela persistência e sincronização de estado thread-safe em disco (temp/estado_pipeline.json).
Garante que o progresso, logs, roteiro, áudio e vídeo sobrevivam a recarregamentos de página (F5) no Streamlit.
Otimizado para Windows com retry loop contra travamentos de arquivo.
"""

import os
import json
import time
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List

CAMINHO_ESTADO = os.path.join("temp", "estado_pipeline.json")
_lock = threading.Lock()

ESTADO_PADRAO = {
    "status": "idle",  # "idle" | "running" | "completed" | "error"
    "etapa_atual": "",  # "roteiro" | "audio" | "sync" | "video" | "completo"
    "progresso_valor": 0.0,
    "progresso_texto": "Aguardando início...",
    "tema": "Os 5 Lugares Mais Misteriosos Onde Pessoas Simplesmente Desapareceram",
    "duracao_minima": 3.0,
    "voz_tipo": "neural_ptbr",  # "neural_ptbr" | "clonada" | "propria" | "padrao"
    "voice_id": "pt-BR-AntonioNeural",
    "roteiro": None,
    "audio_path": None,
    "sync_dados": None,
    "imagens_cenas": {},
    "estilo_visual": "dark_cinematic",
    "provedor_imagem": "gemini",
    "aspect_ratio_imagem": "16:9",
    "biblia_visual": None,
    "gpu_info": None,
    "flow_motion_ativo": True,
    "video_path": None,
    "youtube_dados": None,
    "shorts_gerados": [],
    "logs": [],
    "erro": None,
    "atualizado_em": ""
}


def inicializar_diretorio():
    """Garante a existência da pasta temp."""
    os.makedirs("temp", exist_ok=True)


def obter_estado() -> Dict[str, Any]:
    """Lê o estado persistido do arquivo JSON com tolerância a leituras concorrentes."""
    inicializar_diretorio()
    with _lock:
        if not os.path.exists(CAMINHO_ESTADO):
            estado = dict(ESTADO_PADRAO)
            estado["atualizado_em"] = datetime.now().isoformat()
            try:
                with open(CAMINHO_ESTADO, "w", encoding="utf-8") as f:
                    json.dump(estado, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"[gerenciador_estado] Erro ao criar estado inicial: {e}")
            return estado

        for _ in range(5):
            try:
                with open(CAMINHO_ESTADO, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                time.sleep(0.04)

        # Fallback se leitura falhar temporariamente
        return dict(ESTADO_PADRAO)


def salvar_estado(novo_estado: Dict[str, Any]):
    """Salva o estado no arquivo JSON com retry loop seguro para Windows."""
    inicializar_diretorio()
    novo_estado["atualizado_em"] = datetime.now().isoformat()
    conteudo = json.dumps(novo_estado, ensure_ascii=False, indent=2)

    with _lock:
        for _ in range(5):
            try:
                with open(CAMINHO_ESTADO, "w", encoding="utf-8") as f:
                    f.write(conteudo)
                return
            except Exception as e:
                time.sleep(0.05)
        print(f"[gerenciador_estado] Falha ao persistir estado após 5 tentativas.")


def atualizar_progresso(valor: float, texto: str, etapa: Optional[str] = None):
    """Atualiza o progresso percentual e mensagem descritiva."""
    estado = obter_estado()
    estado["progresso_valor"] = round(float(valor), 2)
    estado["progresso_texto"] = texto
    if etapa:
        estado["etapa_atual"] = etapa
    
    timestamp = datetime.now().strftime("%H:%M:%S")
    estado["logs"].append(f"[{timestamp}] [{int(valor * 100)}%] {texto}")
    salvar_estado(estado)


def adicionar_log(mensagem: str):
    """Adiciona uma mensagem de log com timestamp."""
    estado = obter_estado()
    timestamp = datetime.now().strftime("%H:%M:%S")
    estado["logs"].append(f"[{timestamp}] {mensagem}")
    salvar_estado(estado)


def definir_status(status: str, erro: Optional[str] = None, etapa: Optional[str] = None):
    """Atualiza o status de execução ('idle', 'running', 'completed', 'error')."""
    estado = obter_estado()
    estado["status"] = status
    if erro is not None:
        estado["erro"] = erro
    if etapa is not None:
        estado["etapa_atual"] = etapa
    salvar_estado(estado)


def definir_dados(
    tema: Optional[str] = None,
    roteiro: Optional[Dict[str, Any]] = None,
    audio_path: Optional[str] = None,
    sync_dados: Optional[Dict[str, Any]] = None,
    imagens_cenas: Optional[Dict[int, str]] = None,
    video_path: Optional[str] = None,
    youtube_dados: Optional[Dict[str, Any]] = None,
    duracao_minima: Optional[float] = None,
    voz_tipo: Optional[str] = None,
    voice_id: Optional[str] = None,
    shorts_gerados: Optional[List[Dict[str, Any]]] = None,
    provedor_imagem: Optional[str] = None,
    estilo_visual: Optional[str] = None,
    aspect_ratio_imagem: Optional[str] = None,
    biblia_visual: Optional[Dict[str, Any]] = None,
    gpu_info: Optional[Dict[str, Any]] = None,
    **kwargs
):
    """Atualiza os artefatos de dados no estado de forma thread-safe."""
    estado = obter_estado()
    if tema is not None:
        estado["tema"] = tema
    if duracao_minima is not None:
        estado["duracao_minima"] = float(duracao_minima)
    if voz_tipo is not None:
        estado["voz_tipo"] = voz_tipo
    if voice_id is not None:
        estado["voice_id"] = voice_id
    if roteiro is not None:
        estado["roteiro"] = roteiro
    if audio_path is not None:
        estado["audio_path"] = audio_path
    if sync_dados is not None:
        estado["sync_dados"] = sync_dados
    if imagens_cenas is not None:
        # Mescla caso já existam imagens cadastradas
        atuais = estado.get("imagens_cenas", {}) or {}
        atuais.update(imagens_cenas)
        estado["imagens_cenas"] = atuais
    if video_path is not None:
        estado["video_path"] = video_path
    if youtube_dados is not None:
        estado["youtube_dados"] = youtube_dados
    if shorts_gerados is not None:
        estado["shorts_gerados"] = shorts_gerados
    if provedor_imagem is not None:
        estado["provedor_imagem"] = provedor_imagem
    if estilo_visual is not None:
        estado["estilo_visual"] = estilo_visual
    if aspect_ratio_imagem is not None:
        estado["aspect_ratio_imagem"] = aspect_ratio_imagem
    if biblia_visual is not None:
        estado["biblia_visual"] = biblia_visual
    if gpu_info is not None:
        estado["gpu_info"] = gpu_info

    # Qualquer argumento adicional passado via kwargs é persistido
    for k, v in kwargs.items():
        if v is not None:
            estado[k] = v

    salvar_estado(estado)


def esta_em_execucao() -> bool:
    """Verifica se há processamento ativo."""
    estado = obter_estado()
    return estado.get("status") == "running"


def resetar_estado(manter_tema: bool = True) -> Dict[str, Any]:
    """Restaura o estado para os padrões limpos."""
    estado_atual = obter_estado()
    tema_antigo = estado_atual.get("tema", ESTADO_PADRAO["tema"])
    
    novo_estado = dict(ESTADO_PADRAO)
    if manter_tema and tema_antigo:
        novo_estado["tema"] = tema_antigo
    novo_estado["logs"] = [f"[{datetime.now().strftime('%H:%M:%S')}] Sessão reiniciada."]
    salvar_estado(novo_estado)
    return novo_estado
