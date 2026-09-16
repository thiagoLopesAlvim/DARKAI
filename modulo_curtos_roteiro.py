"""
Módulo modulo_curtos_roteiro.py
Gerador de Roteiros, Storyboard e Prompts para o Módulo de VÍDEOS CURTOS (Estilo Flow / Multi-Nicho).

Diferenciais deste módulo:
1. Sem limitação de nicho: Suporta humor, nonsense, animais, fábulas, curiosidades, pessoas, etc.
2. Foco em retenção no TikTok / YouTube Shorts: Hook obrigatório de 0 a 3s.
3. Geração de fichas de Personagens Âncora (9:16) para manter consistência no Flow.
4. Prompts de imagem prontos para o Flow (Nano Banana 2 / Flux) em 9:16.
5. Prompts de animação (Image-to-Video) com diálogos embutidos para o Flow.
"""

import os
import json
import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# Gêneros e estilos populares para vídeos curtos virais
GENEROS_CURTOS = {
    "humor_nonsense": {
        "nome": "Humor & Situações Absurdas / Nonsense",
        "emoji": "🤪",
        "descricao": "Personagens inusitados (animais, frutas, bebês, objetos) vivendo dramas cômicos, discussões rápidas e piadas visuais.",
        "tom": "engraçado, sarcástico, dinâmico e inesperado",
        "estilo_visual": "3d glossy character, vibrant studio lighting, Pixar/Dreamworks style, expressive faces, 9:16 vertical"
    },
    "animais_estilosos": {
        "nome": "Animais com Atitude / Fofura",
        "emoji": "🐶",
        "descricao": "Cães ou gatos fazendo atividades humanas (skate, cozinha, escritório) com estilo cativante e áudio ASMR ou cômico.",
        "tom": "divertido, cativante, fofo e impressionante",
        "estilo_visual": "photorealistic, hyperdetailed animal fur, GoPro angle, cinematic natural light, 9:16 vertical"
    },
    "conversa_direta": {
        "nome": "Gancho Direto / 'Falando com Você'",
        "emoji": "💬",
        "descricao": "Um personagem ou pessoa falando diretamente para a câmera nos primeiros 3s criando curiosidade íntima ou suspense.",
        "tom": "íntimo, curioso, intrigante e persuasivo",
        "estilo_visual": "close-up portrait, shallow depth of field, authentic eye contact, cinematic lighting, 9:16 vertical"
    },
    "curiosidade_chocante": {
        "nome": "Curiosidade Chocante / Fato Rápido",
        "emoji": "⚡",
        "descricao": "Uma revelação inacreditável explicada em menos de 50 segundos com visual impactante e ritmo frenético.",
        "tom": "urgente, chocante, misterioso e informativo",
        "estilo_visual": "cinematic hyperrealistic documentary, dramatic shadows, macro details, 8k resolution, 9:16 vertical"
    },
    "fabulas_licoes": {
        "nome": "Fábulas Modernas & Histórias Rápidas",
        "emoji": "📖",
        "descricao": "Uma pequena narrativa com moral, reviravolta surpreendente ou teste moral contada com personagens marcantes.",
        "tom": "reflexivo, emocionante, dramático com reviravolta",
        "estilo_visual": "fantasy cinematic, volumetric fog, magical soft glow, rich color palette, 9:16 vertical"
    },
    "livre_customizado": {
        "nome": "Personalizado / Qualquer Nicho",
        "emoji": "✨",
        "descricao": "Crie exatamente o que imaginar para qualquer tema, nicho ou linha editorial sem nenhuma restrição.",
        "tom": "adaptado ao tema do criador",
        "estilo_visual": "high quality 3d/cinematic, 9:16 vertical"
    }
}


# ==============================================================================
# 📋 MODELOS DE DADOS ESTRUTURADOS (PYDANTIC)
# ==============================================================================

class PersonagemAncora(BaseModel):
    id: str = Field(description="Identificador único (ex: 'personagem_1', 'bebe_pera')")
    nome: str = Field(description="Nome ou descrição resumida do personagem/objeto")
    descricao_visual: str = Field(description="Descrição detalhada das características físicas, cores e expressões que devem se manter imutáveis")
    prompt_imagem_ancora: str = Field(description="Prompt em inglês para gerar a imagem âncora isolada (9:16, fundo neutro ou estúdio, foco total no personagem)")


class CenaCurta(BaseModel):
    numero: int = Field(description="Número sequencial da cena (iniciando em 1)")
    duracao_segundos: float = Field(description="Duração estimada da cena animada (normalmente entre 3.0 e 7.0 segundos)")
    descricao_acao: str = Field(description="O que acontece visualmente nesta cena (movimentos, reações)")
    personagens_presentes: List[str] = Field(description="Lista dos nomes dos personagens que aparecem nesta cena")
    dialogo_fala: Optional[str] = Field(default="", description="Fala ou diálogo exato proferido nesta cena (caso haja narração ou fala de personagem)")
    prompt_imagem_cena: str = Field(description="Prompt em inglês para gerar a imagem base 9:16 desta cena no Flow (cenário + personagens)")
    prompt_animacao_flow: str = Field(description="Prompt em inglês para o comando Image-to-Video no Flow (movimento de câmera, gestos, expressões e ação)")


class RoteiroCurto(BaseModel):
    titulo: str = Field(description="Título atrativo do vídeo curto")
    genero: str = Field(description="Gênero ou estilo escolhido")
    tema_central: str = Field(description="Tema central abordado")
    hook_inicial: str = Field(description="Frase e impacto dos primeiros 3 segundos para reter a audiência imediatamente")
    personagens_ancora: List[PersonagemAncora] = Field(description="Fichas de personagens para manter a consistência no Flow")
    cenas: List[CenaCurta] = Field(description="Lista de cenas sequenciais que compõem o vídeo curto")
    cta_final: str = Field(description="Chamada para ação no final (ex: 'Siga para a parte 2', 'Comente o que você faria')")
    sugestao_trilha: str = Field(description="Sugestão de estilo musical de fundo ou ritmo sonoro")


# ==============================================================================
# 🤖 MOTOR DE GERAÇÃO COM GOOGLE GEMINI
# ==============================================================================

def gerar_roteiro_curto(
    tema: str,
    genero_id: str = "humor_nonsense",
    instrucoes_extras: Optional[str] = None,
    qtd_cenas: int = 5,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Gera um roteiro estruturado para vídeo curto (9:16) no formato do Google Flow.
    Gera personagens âncora, prompts de imagem base e prompts de animação (image-to-video).
    """
    chave = api_key or os.environ.get("GEMINI_API_KEY")
    if not chave:
        raise ValueError("Chave GEMINI_API_KEY não configurada. Defina no .env ou passe como argumento.")

    from google import genai
    client = genai.Client(api_key=chave)

    genero_info = GENEROS_CURTOS.get(genero_id, GENEROS_CURTOS["livre_customizado"])

    prompt_sistema = f"""
Você é um diretor e roteirista de elite especialista em VÍDEOS CURTOS VIRAIS para TikTok, YouTube Shorts e Instagram Reels, usando ferramentas de IA como GOOGLE FLOW (Nano Banana 2) e Image-to-Video.

Sua missão é criar o roteiro completo e as instruções técnicas de um vídeo curto baseado no seguinte briefing:
- TEMA: {tema}
- GÊNERO/ESTILO: {genero_info['nome']} ({genero_info['descricao']})
- TOM DESEJADO: {genero_info['tom']}
- ESTILO VISUAL DE REFERÊNCIA: {genero_info['estilo_visual']}
- NÚMERO DE CENAS: {qtd_cenas} cenas (duração total ideal entre 25s e 55s)
- INSTRUÇÕES ADICIONAIS: {instrucoes_extras or 'Nenhuma. Seja criativo, dinâmico e focado em alta retenção!'}

DIRETRIZES FUNDAMENTAIS DO MÉTODO (VÍDEO VIRAL / FLOW):
1. **HOOK PODEROSO (0 a 3 segundos)**: A primeira cena DEVE conter um gancho visual ou verbal que prenda imediatamente o espectador. Não comece devagar!
2. **PERSONAGENS ÂNCORA**: Se houver personagens ou objetos principais, crie uma ficha clara com prompt em inglês para gerar uma imagem âncora isolada (full body, neutral background, 9:16) para que o criador possa usar no Flow e garantir consistência visual.
3. **PROMPTS DE IMAGEM 9:16**: Para cada cena, forneça um prompt detalhado em INGLÊS no formato 9:16 vertical, mencionando iluminação, texturas, posição dos personagens e enquadramento cinematográfico vertical.
4. **PROMPTS DE ANIMAÇÃO PARA O FLOW (IMAGE-TO-VIDEO)**: No Flow, a imagem estática é animada. Forneça o comando em inglês detalhando o movimento de câmera (ex: subtle zoom-in, camera pan), a ação física do personagem (ex: hands waving, blinking eyes, shocked expression) e inclua a FALA/DIÁLOGO exata que o personagem deve dizer (ou a narração correspondente).
5. **RITMO**: As cenas devem ser rápidas (3 a 6 segundos cada), com transição dinâmica entre elas.
6. **CTA / PUNCHLINE**: O final deve ter uma reviravolta engraçada/surpreendente ou uma chamada para seguir/comentar.

IMPORTANTE: Responda ESTRITAMENTE em formato JSON compatível com a estrutura especificada.
"""

    modelo = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    
    resposta = client.models.generate_content(
        model=modelo,
        contents=prompt_sistema,
        config={
            "response_mime_type": "application/json",
            "response_schema": RoteiroCurto,
            "temperature": 0.8
        }
    )

    try:
        dados = json.loads(resposta.text)
    except Exception:
        # Fallback de limpeza caso venha com markdown codeblock
        texto_limpo = re.sub(r"^```json\s*", "", resposta.text.strip(), flags=re.MULTILINE)
        texto_limpo = re.sub(r"```$", "", texto_limpo, flags=re.MULTILINE).strip()
        dados = json.loads(texto_limpo)

    # Salva uma cópia do roteiro gerado
    os.makedirs(os.path.join("output", "curtos", "projetos"), exist_ok=True)
    nome_sanitizado = re.sub(r'[^\w\-_\.]', '_', dados.get("titulo", "roteiro_curto"))[:40]
    caminho_salvo = os.path.join("output", "curtos", "projetos", f"{nome_sanitizado}.json")
    with open(caminho_salvo, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    dados["_caminho_arquivo"] = caminho_salvo
    return dados


def listar_projetos_curtos_salvos() -> List[Dict[str, Any]]:
    """Lista todos os roteiros de vídeos curtos salvos na pasta output/curtos/projetos/"""
    pasta = os.path.join("output", "curtos", "projetos")
    if not os.path.exists(pasta):
        return []
    
    projetos = []
    for arq in os.listdir(pasta):
        if arq.endswith(".json"):
            caminho = os.path.join(pasta, arq)
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    conteudo = json.load(f)
                    projetos.append({
                        "arquivo": arq,
                        "caminho": caminho,
                        "titulo": conteudo.get("titulo", arq),
                        "genero": conteudo.get("genero", "Não especificado"),
                        "qtd_cenas": len(conteudo.get("cenas", [])),
                        "hook": conteudo.get("hook_inicial", "")
                    })
            except Exception:
                pass
    return projetos
