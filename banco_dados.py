"""
Módulo banco_dados.py
Gerencia a base de dados SQLite local (database/darkai.db) para histórico de vídeos gerados,
métricas de produção, minutagem e registros de publicação no YouTube.
"""

import os
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any, List

CAMINHO_BANCO = os.path.join("database", "darkai.db")


def obter_conexao() -> sqlite3.Connection:
    """Cria e retorna conexão com o banco SQLite."""
    os.makedirs(os.path.dirname(CAMINHO_BANCO), exist_ok=True)
    conn = sqlite3.connect(CAMINHO_BANCO)
    conn.row_factory = sqlite3.Row
    return conn


def inicializar_banco():
    """Cria a tabela de histórico de vídeos caso ainda não exista e aplica migrações."""
    with obter_conexao() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS videos_historico (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tema TEXT NOT NULL,
                titulo TEXT NOT NULL,
                descricao TEXT,
                tags TEXT,
                duracao_segundos REAL DEFAULT 0.0,
                aspect_ratio TEXT DEFAULT '16:9',
                voz_tipo TEXT DEFAULT 'padrao',
                voice_id TEXT,
                qtd_cenas INTEGER DEFAULT 0,
                caminho_video TEXT,
                caminho_audio TEXT,
                caminho_roteiro TEXT,
                youtube_url TEXT,
                youtube_status TEXT,
                tamanho_mb REAL DEFAULT 0.0,
                is_short INTEGER DEFAULT 0,
                video_origem_id INTEGER,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS perfil_canal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_canal TEXT NOT NULL,
                nicho_principal TEXT NOT NULL,
                tom_narrativo TEXT,
                persona_narrador TEXT,
                atualizado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historico_pautas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tema TEXT NOT NULL,
                nicho_id TEXT,
                hook_inicial TEXT,
                revelacao_chave TEXT,
                status TEXT DEFAULT 'planejado',
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Migração defensiva para bancos já criados
        cursor.execute("PRAGMA table_info(videos_historico)")
        colunas = [info[1] for info in cursor.fetchall()]
        if "is_short" not in colunas:
            cursor.execute("ALTER TABLE videos_historico ADD COLUMN is_short INTEGER DEFAULT 0")
        if "video_origem_id" not in colunas:
            cursor.execute("ALTER TABLE videos_historico ADD COLUMN video_origem_id INTEGER")
        conn.commit()


def salvar_video_historico(dados: Dict[str, Any]) -> int:
    """
    Insere ou atualiza um registro de vídeo no banco de dados.
    
    Args:
        dados: Dicionário contendo tema, titulo, descricao, tags, is_short, etc.
        
    Returns:
        ID do registro criado.
    """
    inicializar_banco()
    
    # Tratamento das tags para formato string
    tags = dados.get("tags", [])
    tags_str = ", ".join(tags) if isinstance(tags, list) else str(tags or "")

    caminho_video = dados.get("caminho_video") or dados.get("video_path")
    caminho_audio = dados.get("caminho_audio") or dados.get("audio_path")
    aspect = dados.get("aspect_ratio", "16:9")
    is_short = 1 if (dados.get("is_short") or aspect == "9:16") else 0
    origem_id = dados.get("video_origem_id")
    
    tamanho_mb = 0.0
    if caminho_video and os.path.exists(caminho_video):
        tamanho_mb = round(os.path.getsize(caminho_video) / (1024 * 1024), 2)

    with obter_conexao() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO videos_historico (
                tema, titulo, descricao, tags, duracao_segundos,
                aspect_ratio, voz_tipo, voice_id, qtd_cenas,
                caminho_video, caminho_audio, caminho_roteiro,
                youtube_url, youtube_status, tamanho_mb,
                is_short, video_origem_id, criado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            dados.get("tema", ""),
            dados.get("titulo", "Sem título"),
            dados.get("descricao", ""),
            tags_str,
            float(dados.get("duracao_segundos", 0.0)),
            aspect,
            dados.get("voz_tipo", "padrao"),
            dados.get("voice_id", ""),
            int(dados.get("qtd_cenas", 0)),
            caminho_video,
            caminho_audio,
            dados.get("caminho_roteiro", ""),
            dados.get("youtube_url", ""),
            dados.get("youtube_status", ""),
            tamanho_mb,
            is_short,
            origem_id,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        return cursor.lastrowid


def listar_historico(limite: int = 50, busca: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retorna lista de vídeos gerados ordenados pelo mais recente."""
    inicializar_banco()
    with obter_conexao() as conn:
        cursor = conn.cursor()
        if busca and busca.strip():
            termo = f"%{busca.strip()}%"
            cursor.execute("""
                SELECT * FROM videos_historico
                WHERE tema LIKE ? OR titulo LIKE ? OR tags LIKE ?
                ORDER BY id DESC LIMIT ?
            """, (termo, termo, termo, limite))
        else:
            cursor.execute("""
                SELECT * FROM videos_historico
                ORDER BY id DESC LIMIT ?
            """, (limite,))
        
        linhas = cursor.fetchall()
        return [dict(linha) for linha in linhas]


def excluir_registro(id_registro: int) -> bool:
    """Exclui um vídeo do histórico SQLite pelo ID."""
    inicializar_banco()
    with obter_conexao() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM videos_historico WHERE id = ?", (id_registro,))
        conn.commit()
        return cursor.rowcount > 0


def obter_metricas_gerais() -> Dict[str, Any]:
    """Calcula estatísticas consolidadas da produção de vídeos e shorts."""
    inicializar_banco()
    with obter_conexao() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COUNT(*) as total_videos,
                COALESCE(SUM(duracao_segundos), 0) as total_segundos,
                COALESCE(SUM(tamanho_mb), 0) as total_tamanho_mb,
                COUNT(CASE WHEN youtube_url IS NOT NULL AND youtube_url != '' THEN 1 END) as total_youtube,
                COUNT(CASE WHEN voz_tipo = 'clonada' THEN 1 END) as total_voz_clonada,
                COUNT(CASE WHEN is_short = 1 OR aspect_ratio = '9:16' THEN 1 END) as total_shorts
            FROM videos_historico
        """)
        row = cursor.fetchone()
        
        total_segundos = row["total_segundos"]
        total_minutos = round(total_segundos / 60, 1)
        total_horas = round(total_segundos / 3600, 2)

        return {
            "total_videos": row["total_videos"],
            "total_minutos": total_minutos,
            "total_horas": total_horas,
            "total_tamanho_mb": round(row["total_tamanho_mb"], 2),
            "total_youtube": row["total_youtube"],
            "total_voz_clonada": row["total_voz_clonada"],
            "total_shorts": row["total_shorts"]
        }


def obter_perfil_canal() -> Dict[str, Any]:
    """Retorna o perfil do canal cadastrado ou valores padrão."""
    inicializar_banco()
    with obter_conexao() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM perfil_canal ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        if row:
            return dict(row)
        return {
            "nome_canal": "Meu Canal Dark",
            "nicho_principal": "Arquivos Secretos & Conspirações",
            "tom_narrativo": "Sombrio, investigativo, sério e imersivo",
            "persona_narrador": "Investigador documental de arquivos antigos"
        }


def salvar_perfil_canal(dados: Dict[str, Any]):
    """Salva ou atualiza a identidade e nicho do canal."""
    inicializar_banco()
    with obter_conexao() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO perfil_canal (nome_canal, nicho_principal, tom_narrativo, persona_narrador, atualizado_em)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            dados.get("nome_canal", "Meu Canal Dark"),
            dados.get("nicho_principal", "Arquivos Secretos & Conspirações"),
            dados.get("tom_narrativo", "Sombrio e investigativo"),
            dados.get("persona_narrador", "Narrador documental")
        ))
        conn.commit()


def salvar_pauta_historico(pauta: Dict[str, Any]) -> int:
    """Registra uma pauta selecionada no histórico do canal."""
    inicializar_banco()
    with obter_conexao() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO historico_pautas (tema, nicho_id, hook_inicial, revelacao_chave, status)
            VALUES (?, ?, ?, ?, ?)
        """, (
            pauta.get("tema", ""),
            pauta.get("nicho_id", ""),
            pauta.get("hook_inicial", ""),
            pauta.get("revelacao_chave", ""),
            pauta.get("status", "planejado")
        ))
        conn.commit()
        return cursor.lastrowid


def listar_pautas_historico(limite: int = 20) -> List[Dict[str, Any]]:
    """Lista as últimas pautas registradas para acompanhamento editorial."""
    inicializar_banco()
    with obter_conexao() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM historico_pautas ORDER BY id DESC LIMIT ?", (limite,))
        return [dict(r) for r in cursor.fetchall()]


def salvar_curto_historico(dados: Dict[str, Any]) -> int:
    """Salva um vídeo curto montado na tabela de histórico."""
    dados_padronizados = {
        "tema": dados.get("tema", dados.get("titulo", "Vídeo Curto")),
        "titulo": dados.get("titulo", "Vídeo Curto"),
        "descricao": dados.get("descricao", "Short montado via Módulo Vídeos Curtos"),
        "tags": dados.get("tags", "shorts,viral,tiktok"),
        "duracao_segundos": dados.get("duracao_segundos", 0.0),
        "aspect_ratio": "9:16",
        "voz_tipo": "flow",
        "qtd_cenas": dados.get("qtd_cenas", 0),
        "caminho_video": dados.get("caminho_video", ""),
        "caminho_audio": "",
        "caminho_roteiro": dados.get("caminho_roteiro", ""),
        "tamanho_mb": dados.get("tamanho_mb", 0.0),
        "is_short": 1
    }
    return salvar_video_historico(dados_padronizados)


def listar_curtos_historico(limite: int = 50) -> List[Dict[str, Any]]:
    """Lista todos os vídeos curtos gerados no banco."""
    inicializar_banco()
    with obter_conexao() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM videos_historico WHERE is_short = 1 ORDER BY id DESC LIMIT ?", (limite,))
        return [dict(r) for r in cursor.fetchall()]


if __name__ == "__main__":
    inicializar_banco()
    print("Banco SQLite inicializado em:", CAMINHO_BANCO)
    print("Métricas atuais:", obter_metricas_gerais())

