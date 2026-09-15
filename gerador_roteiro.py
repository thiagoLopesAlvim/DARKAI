"""
Módulo gerador_roteiro.py
Integração com a API Google Gemini para geração de roteiros de vídeos para Canal Dark.
Retorna um JSON estruturado com título, descrição, tags e cenas divididas com narração e prompts visuais.
"""

import os
import json
import re
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

class Cena(BaseModel):
    cena_id: int = Field(description="Identificador sequencial da cena, iniciando em 1")
    visual_prompt: str = Field(description="Descrição visual cinematográfica detalhada para geração da imagem na Fase 2")
    narracao: str = Field(description="Texto da narração que será falada pelo narrador nesta cena")

class RoteiroVideo(BaseModel):
    titulo: str = Field(description="Título cativante de alta retenção e CTR para o YouTube")
    descricao: str = Field(description="Descrição para o YouTube com sinopse e hashtags")
    tags: List[str] = Field(description="Lista de 5 a 10 tags estratégicas para o algoritmo do YouTube")
    cenas: List[Cena] = Field(description="Lista de cenas que compõem o vídeo em ordem sequencial")


class PerguntaAprofundamento(BaseModel):
    id: str = Field(description="Identificador curto da questão (ex: angulo_narrativo, teoria_principal)")
    pergunta: str = Field(description="Pergunta clara e instigante para direcionar a história")
    opcoes: List[str] = Field(description="Lista com 3 ou 4 opções criativas de resposta")

class ListaPerguntas(BaseModel):
    perguntas: List[PerguntaAprofundamento] = Field(description="Lista de 2 a 3 perguntas estratégicas para aprofundar o roteiro")


def sanitizar_nome_arquivo(texto: str) -> str:
    """Converte um texto em uma string segura para nome de arquivo."""
    texto = texto.lower()
    texto = re.sub(r'[^\w\s-]', '', texto)
    return re.sub(r'[-\s]+', '_', texto).strip('_')[:50]


def gerar_perguntas_aprofundamento(
    tema: str,
    duracao_minutos: float = 3.0,
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Gera 2 a 3 perguntas estratégicas com Gemini para aprofundar o roteiro
    e coletar preferências do usuário antes da geração final.
    """
    chave = api_key or os.getenv("GEMINI_API_KEY", "").strip()

    # Perguntas padrão de alta qualidade para Dark Channel
    fallback_perguntas = [
        {
            "id": "angulo_narrativo",
            "pergunta": f"Qual atmosfera e ângulo narrativo você prefere para '{tema}'?",
            "opcoes": [
                "Investigação forense e desclassificação de arquivos confidenciais",
                "Terror psicológico e suspense com relatos em primeira pessoa",
                "Teorias da conspiração e acobertamento governamental militar",
                "Misticismo sombrio e fenômenos inexplicáveis pela ciência"
            ]
        },
        {
            "id": "teoria_principal",
            "pergunta": "Qual elemento de impacto deve ser o clímax da revelação?",
            "opcoes": [
                "Uma gravação de áudio ou documento vazado que contradiz a história oficial",
                "O testemunho perturbador da última pessoa que presenciou o fato",
                "A descoberta recente de pistas físicas que reabriram o caso",
                "Um padrão sinistro de desaparecimentos semelhantes ao redor do globo"
            ]
        },
        {
            "id": "tom_desfecho",
            "pergunta": "Como o vídeo deve concluir a experiência do espectador?",
            "opcoes": [
                "Final aberto, deixando uma pergunta inquietante que força comentários",
                "Revelação da teoria mais perturbadora e plausível",
                "Alerta direto ao espectador sobre os perigos ainda presentes hoje"
            ]
        }
    ]

    if not chave or "sua_chave" in chave.lower():
        return fallback_perguntas

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=chave)
        prompt = f"""
Você é um estrategista sênior de retenção para canais Dark do YouTube.
O criador quer produzir um vídeo de aproximadamente {duracao_minutos} minutos sobre o tema:
"{tema}"

Crie de 2 a 3 perguntas estratégicas com opções de resposta para que o criador defina o tom, a revelação principal ou o foco investigativo antes de redigirmos o roteiro completo.
Retorne no formato JSON especificado.
"""
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ListaPerguntas,
            temperature=0.7
        )
        modelos_tentar = [os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip(), "gemini-3-flash-preview", "gemini-flash-latest"]
        resposta = None
        for mod in modelos_tentar:
            try:
                resposta = client.models.generate_content(
                    model=mod,
                    contents=prompt,
                    config=config
                )
                if resposta and resposta.text:
                    break
            except Exception:
                continue

        if not resposta or not resposta.text:
            return fallback_perguntas

        dados = json.loads(resposta.text)
        return dados.get("perguntas", fallback_perguntas)
    except Exception as e:
        print(f"[gerador_roteiro] Erro ao obter perguntas do Gemini ({e}). Usando padrão.")
        return fallback_perguntas


def gerar_roteiro_mock(tema: str, duracao_minutos: float = 2.0) -> Dict[str, Any]:
    """Retorna um roteiro simulado escalado conforme a duração solicitada."""
    # Determina quantidade de cenas proporcional ao tempo
    if duracao_minutos <= 1.5:
        qtd_cenas = 3
    elif duracao_minutos <= 3.5:
        qtd_cenas = 6
    elif duracao_minutos <= 6.0:
        qtd_cenas = 8
    elif duracao_minutos <= 9.0:
        qtd_cenas = 12
    else:
        qtd_cenas = 15

    cenas_base = [
        ("Cinematic dark atmospheric shot, dim candle light in an old dusty archive, ominous shadows, 8k resolution",
         f"Você já parou para pensar no que realmente aconteceu quando o mundo ouviu falar sobre {tema} pela primeira vez? A versão que nos contaram esconde um abismo de segredos perturbadores."),
        ("Vintage classified documents scattered across a dark wooden table, red stamp saying TOP SECRET, dramatic low key lighting",
         "Durante décadas, testemunhas oculares foram sistematicamente desacreditadas. Arquivos confidenciais foram deliberadamente transferidos para instalações de alta segurança sem qualquer registro oficial."),
        ("Mysterious silhouette of a figure standing in heavy fog under an old streetlamp, dark noir aesthetic, cold color grading",
         "Mas alguns fragmentos conseguiram escapar da censura. Relatos gravados em fitas magnéticas antigas revelam detalhes cronológicos que desafiam toda a lógica científica estabelecida."),
        ("Old computer terminal glowing green in a dark abandoned military bunker, flickering monochrome monitor",
         "Registros de radar e frequências de rádio captadas na mesma noite registraram anomalias sem precedentes. Operadores civis foram instruídos a desligar os equipamentos imediatamente."),
        ("Ancient stone hallway underground with heavy iron locked doors, torches casting long eerie shadows",
         "As pistas apontam para algo muito mais profundo do que uma simples coincidência. Quem estava no comando das operações ordenou silêncio absoluto sob pena de corte marcial imediata."),
        ("Slow zoom in on an ancient locked vault door inside a stone basement, mysterious glow from the edges, suspenseful atmosphere",
         "O que você acabou de ouvir é apenas a ponta do iceberg. A verdadeira pergunta que ecoa até os dias de hoje não é apenas o que ocorreu, mas quem permitiu que continuasse em segredo absoluto.")
    ]

    cenas = []
    for i in range(qtd_cenas):
        prompt_vis, narr = cenas_base[i % len(cenas_base)]
        cenas.append({
            "cena_id": i + 1,
            "visual_prompt": f"{prompt_vis} (Shot {i+1})",
            "narracao": f"Cena {i+1}: {narr}"
        })

    return {
        "titulo": f"O Terrível Segredo Oculto: {tema.title()}",
        "descricao": f"Descubra a verdade oculta sobre {tema}. O que foi deliberadamente escondido durante décadas?\n\n#misterio #canaldark #curiosidades #documentario",
        "tags": ["mistério", "canal dark", "fatos desconhecidos", "segredos", "histórias reais", "investigação", tema],
        "cenas": cenas
    }


def gerar_roteiro(
    tema: str,
    duracao_minima_minutos: float = 2.0,
    respostas_usuario: Optional[Dict[str, str]] = None,
    perfil_canal: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None,
    salvar: bool = True
) -> Dict[str, Any]:
    """
    Gera um roteiro estruturado para o tema fornecido utilizando a API do Google Gemini,
    calibrando a contagem de palavras e número de cenas para atingir a duração mínima estipulada.
    
    Args:
        tema: Assunto ou ideia central do vídeo.
        duracao_minima_minutos: Tempo mínimo estimado do vídeo em minutos (ex: 2.0, 5.0, 8.0).
        respostas_usuario: Preferências de direção narrativa respondidas no modal interativo.
        api_key: Chave da API do Google Gemini (se None, lê de GEMINI_API_KEY).
        model_name: Nome do modelo (padrão: gemini-2.5-flash).
        salvar: Se True, salva o JSON em output/roteiros/.
        
    Returns:
        Dicionário com o roteiro estruturado contendo titulo, descricao, tags e cenas.
    """
    chave = api_key or os.getenv("GEMINI_API_KEY", "").strip()
    modelo = model_name or os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

    # Cálculo da cadência de fala (~140 palavras/minuto em português)
    total_palavras_alvo = max(120, int(duracao_minima_minutos * 140))
    
    # Determinação da quantidade ideal de cenas
    if duracao_minima_minutos <= 1.5:
        qtd_cenas = 4
    elif duracao_minima_minutos <= 3.5:
        qtd_cenas = 6
    elif duracao_minima_minutos <= 5.5:
        qtd_cenas = 8
    elif duracao_minima_minutos <= 8.5:
        qtd_cenas = 12
    else:
        qtd_cenas = 16

    palavras_por_cena = max(25, int(total_palavras_alvo / qtd_cenas))

    # Formatação de respostas customizadas do usuário se houver
    bloco_diretrizes_usuario = ""
    if respostas_usuario:
        linhas = [f"- {chave}: {valor}" for chave, valor in respostas_usuario.items() if valor]
        if linhas:
            bloco_diretrizes_usuario = "PREFERÊNCIAS E DIRETRIZES DO CRIADOR (OBRIGATÓRIO INCORPORAR NA NARRATIVA):\n" + "\n".join(linhas) + "\n"

    # Se o perfil do canal for fornecido, injeta a identidade editorial
    bloco_perfil_canal = ""
    if perfil_canal:
        bloco_perfil_canal = f"""
IDENTIDADE EDITORIAL DO CANAL:
- Nome do Canal: {perfil_canal.get('nome_canal', 'Canal Dark')}
- Nicho Principal: {perfil_canal.get('nicho', 'Mistérios & Curiosidades Sombrias')}
- Tom do Narrador: {perfil_canal.get('tom', 'Sombrio, investigativo, sério e imersivo')}
- Persona: {perfil_canal.get('persona', 'Narrador investigativo de alta retenção')}
Adapte o vocabulário, o ritmo e as revelações para manter a coerência de identidade deste canal.
"""

    # Se a chave não estiver configurada ou for um placeholder, usa mock seguro
    if not chave or "sua_chave" in chave.lower():
        print(f"[gerador_roteiro] Chave GEMINI_API_KEY não configurada. Usando gerador simulado para '{tema}'.")
        roteiro_dict = gerar_roteiro_mock(tema, duracao_minutos=duracao_minima_minutos)
    else:
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=chave)

            prompt = f"""
Você é o roteirista principal de um dos maiores e mais assistidos canais Dark do YouTube.
Sua especialidade são vídeos de alta retenção (watch-time superior a 70%) sobre mistérios, casos reais, história oculta, curiosidades sombrias e suspense investigativo.

TEMA DO VÍDEO: {tema}
DURAÇÃO MÍNIMA ALVO: {duracao_minima_minutos:.1f} minutos
META TOTAL DE PALAVRAS DA NARRAÇÃO: No mínimo {total_palavras_alvo} palavras
ESTRUTURA DE CENAS: Divida a história em EXATAMENTE {qtd_cenas} cenas numeradas sequencialmente de 1 a {qtd_cenas}.

{bloco_perfil_canal}
{bloco_diretrizes_usuario}
DIRETRIZES TÉCNICAS E DE ENGAJAMENTO:
1. Comece com um HOOK magnético nos primeiros 5 segundos da Cena 1, gerando curiosidade imediata e prendendo a atenção.
2. IDIOMA RIGOROSO: O campo 'narracao' DEVE ser EXCLUSIVAMENTE em Português do Brasil (PT-BR) nativo e natural. NUNCA coloque narração em inglês, palavras sem tradução ou jargões em língua estrangeira no campo 'narracao'. O campo 'visual_prompt' deve ser em inglês (para a IA de imagem), mas o campo 'narracao' é 100% PT-BR para o narrador.
3. Cada uma das {qtd_cenas} cenas DEVE conter uma narração densa e imersiva de aproximadamente {palavras_por_cena} a {palavras_por_cena + 25} palavras. Não crie frases curtas telegráficas.
4. Cada cena deve ter:
   - 'visual_prompt': Descrição visual cinematográfica ultra-detalhada em INGLÊS (estilo Cinematic dark atmospheric, 8k, photorealistic, volumetric lighting, moody color grade), pronta para envio à IA geradora de imagens.
   - 'narracao': O texto exato em PORTUGUÊS DO BRASIL a ser falado pelo narrador, com tom solene, misterioso, envolvente e fluido.
5. Crie um título altamente atraente (CTR alto) e tags estratégicas para o algoritmo do YouTube.

Retorne EXCLUSIVAMENTE o JSON estruturado conforme o esquema solicitado.
"""

            config = types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=RoteiroVideo,
                temperature=0.7,
                system_instruction="Você é um roteirista profissional de Canal Dark. Produza respostas precisas em formato JSON válido."
            )

            modelos_tentar = [modelo, "gemini-3-flash-preview", "gemini-flash-latest"]
            resposta = None
            ultimo_erro = None
            for mod in modelos_tentar:
                if not mod:
                    continue
                try:
                    resposta = client.models.generate_content(
                        model=mod,
                        contents=prompt,
                        config=config
                    )
                    if resposta and resposta.text:
                        print(f"[gerador_roteiro] Roteiro gerado com sucesso via modelo: {mod}")
                        break
                except Exception as e_mod:
                    ultimo_erro = e_mod
                    print(f"[gerador_roteiro] Modelo {mod} indisponível ou com cota diária esgotada ({e_mod}). Tentando modelo alternativo...")

            if not resposta or not resposta.text:
                raise ultimo_erro or RuntimeError("Nenhum modelo Gemini respondeu.")

            roteiro_dict = json.loads(resposta.text)

        except Exception as e:
            print(f"[gerador_roteiro] Erro ao chamar API do Gemini ({e}). Recorrendo ao roteiro de contingência.")
            roteiro_dict = gerar_roteiro_mock(tema, duracao_minutos=duracao_minima_minutos)
            roteiro_dict["_aviso_fallback"] = str(e)

    # Salva o arquivo JSON se solicitado
    if salvar:
        os.makedirs("output/roteiros", exist_ok=True)
        slug = sanitizar_nome_arquivo(tema)
        caminho_arquivo = os.path.join("output", "roteiros", f"{slug}_roteiro.json")
        with open(caminho_arquivo, "w", encoding="utf-8") as f:
            json.dump(roteiro_dict, f, ensure_ascii=False, indent=2)
        roteiro_dict["_caminho_arquivo"] = caminho_arquivo
        print(f"[gerador_roteiro] Roteiro salvo com sucesso em: {caminho_arquivo}")

    return roteiro_dict


if __name__ == "__main__":
    tema_teste = "O Triângulo das Bermudas e as Desaparições Sem Explicação"
    perguntas = gerar_perguntas_aprofundamento(tema_teste, duracao_minutos=3.0)
    print("Perguntas geradas:", json.dumps(perguntas, indent=2, ensure_ascii=False))
    resultado = gerar_roteiro(tema_teste, duracao_minima_minutos=3.0)
    print(f"Roteiro gerado com {len(resultado.get('cenas', []))} cenas.")

