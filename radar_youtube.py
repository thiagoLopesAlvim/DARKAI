"""
Módulo radar_youtube.py
Responsável por garimpar, monitorar e sugerir pautas e nichos de alta retenção no YouTube
para canais Dark, adaptados para o perfil e linha editorial do canal do criador.
"""

import os
import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()


NICHOS_DARK = [
    {
        "id": "curiosidades_fatos",
        "nome": "Curiosidades & Fatos Fascinantes",
        "emoji": "🌟",
        "descricao": "Fatos chocantes, 'Você sabia?', fenômenos estranhos do mundo e estatísticas que parecem mentira.",
        "potencial_ctr": "Viral Máximo (12% - 18%)",
        "publico": "Amplo, jovens e adultos no TikTok, Shorts e YouTube longo viciados em dopamina rápida."
    },
    {
        "id": "tecnologia_ia",
        "nome": "Tecnologia, IA & O Futuro",
        "emoji": "💡",
        "descricao": "Avanços chocantes de Inteligência Artificial, robôs humanoides, chips neurais e como será 2050.",
        "potencial_ctr": "Altíssimo (10% - 16%)",
        "publico": "Entusiastas de inovação, tecnologia, trabalho do futuro e ficção que virou realidade."
    },
    {
        "id": "ciencia_universo",
        "nome": "Ciência, Universo & Espaço",
        "emoji": "🔬",
        "descricao": "Buracos negros, paradoxo de Fermi, física quântica simples, abismos oceânicos e mistérios da Terra.",
        "potencial_ctr": "Muito Alto (9% - 15%)",
        "publico": "Pessoas com mente científica curiosa, fãs de documentários espaciais e astronomia."
    },
    {
        "id": "historias_reais",
        "nome": "Histórias Reais & Casos Extraordinários",
        "emoji": "📜",
        "descricao": "Acontecimentos históricos inacreditáveis, personagens esquecidos, sobreviventes extremos e enigmas.",
        "potencial_ctr": "Alto (8% - 14%)",
        "publico": "Amantes de boas narrativas, storytelling imersivo e lições humanas marcantes."
    },
    {
        "id": "psicologia_comportamento",
        "nome": "Psicologia & Truques Mentais",
        "emoji": "🧠",
        "descricao": "Vieses cognitivos, linguagem corporal, efeitos psicológicos que nos controlam e testes mentais.",
        "potencial_ctr": "Altíssimo (10% - 15%)",
        "publico": "Interessados em autodesenvolvimento, mente humana, persuasão e curiosidades comportamentais."
    },
    {
        "id": "negocios_imperios",
        "nome": "Negócios, Bilionários & Impérios",
        "emoji": "💰",
        "descricao": "Como marcas gigantes dominaram o mundo, os maiores golpes financeiros e a queda de milionários.",
        "potencial_ctr": "Alto (8% - 13%)",
        "publico": "Empreendedores, curiosos sobre riqueza, finanças e bastidores corporativos."
    },
    {
        "id": "arquivos_secretos",
        "nome": "Arquivos Secretos & Mistérios",
        "emoji": "📁",
        "descricao": "Documentos desclassificados, operações militares clandestinas e mistérios reais não resolvidos.",
        "potencial_ctr": "Muito Alto (9% - 14%)",
        "publico": "Fãs de investigação, conspirações geopolíticas e arquivos confidenciais."
    }
]


class PautaViral(BaseModel):
    tema: str = Field(description="Título do vídeo com alto apelo de CTR para o YouTube")
    nicho_id: str = Field(description="Identificador do nicho a que pertence")
    nicho_nome: str = Field(description="Nome amigável do nicho")
    hook_inicial: str = Field(description="Frase de gancho visceral para prender o espectador nos primeiros 5 segundos")
    revelacao_chave: str = Field(description="O clímax ou revelação perturbadora que garante retenção até o final")
    ctr_estimado: str = Field(description="Estimativa de taxa de cliques (ex: '10.5% CTR')")


class ListaPautasVirais(BaseModel):
    pautas: List[PautaViral] = Field(description="Lista de 4 a 6 ideias virais para canal dark sem rosto")


def obter_nichos_dark() -> List[Dict[str, str]]:
    """Retorna o catálogo de nichos lucrativos de canais Dark / Faceless."""
    return NICHOS_DARK


def obter_pautas_fallback(nicho_id: str = "todos") -> List[Dict[str, Any]]:
    """Gera pautas curadas manualmente com garantia de alta retenção no YouTube Brasil."""
    todas = [
        {
            "tema": "O Que os Satélites da Guerra Fria Realmente Fotografaram no Deserto de Nevada?",
            "nicho_id": "arquivos_secretos",
            "nicho_nome": "Arquivos Secretos & Conspirações",
            "hook_inicial": "Em 1974, um satélite espião enviou fotografias que o Pentágono ordenou que fossem destruídas em 24 horas.",
            "revelacao_chave": "A descoberta de uma estrutura subterrânea em formato de espiral que emite calor sem fonte de energia aparente.",
            "ctr_estimado": "11.2% CTR"
        },
        {
            "tema": "A Fossa das Marianas: O Ponto Mais Profundo Onde o Som Não Deveria Existir",
            "nicho_id": "oceanos_e_abismos",
            "nicho_nome": "Oceanos & Abismos Profundos",
            "hook_inicial": "A 11 mil metros de profundidade, microfones de titânio captaram um ruído metálico que desafia todas as leis da física.",
            "revelacao_chave": "O registro sísmico revelou que a vibração respondia aos impulsos de sonar da expedição.",
            "ctr_estimado": "13.4% CTR"
        },
        {
            "tema": "O Diário Não Editado do Caso Dyatlov: As Anotações Que Foram Apagadas",
            "nicho_id": "crimes_e_enigmas",
            "nicho_nome": "Casos Reais & Enigmas Forenses",
            "hook_inicial": "Durante seis décadas, nos disseram que foi uma avalanche. Mas as últimas 3 páginas do diário contam uma história aterradora.",
            "revelacao_chave": "Testemunhos de caçadores locais revelando que as tendas foram cortadas de fora para dentro.",
            "ctr_estimado": "10.8% CTR"
        },
        {
            "tema": "A Cidade Subterrânea de Derinkuyu e o Alerta Para o Fim dos Tempos",
            "nicho_id": "historia_proibida",
            "nicho_nome": "História Oculta & Relíquias Proibidas",
            "hook_inicial": "Em 1963, um homem derrubou a parede de sua casa na Turquia e encontrou um labirinto para 20 mil pessoas.",
            "revelacao_chave": "As portas de pedra gigantes só podiam ser trancadas pelo lado de dentro para conter algo que vinha da superfície.",
            "ctr_estimado": "9.7% CTR"
        },
        {
            "tema": "O Sinal WOW! e a Transmissão de Resposta Que a NASA Ocultou em 1977",
            "nicho_id": "espaco_e_anomalias",
            "nicho_nome": "Espaço Profundo & Paradoxo de Fermi",
            "hook_inicial": "O telescópio Big Ear recebeu 72 segundos de um sinal artificial. O que poucos sabem é que houve um segundo sinal.",
            "revelacao_chave": "A frequência continha um padrão binário idêntico ao mapa estelar da nossa própria galáxia.",
            "ctr_estimado": "12.0% CTR"
        }
    ]

    if nicho_id != "todos":
        filtradas = [p for p in todas if p["nicho_id"] == nicho_id]
        return filtradas if filtradas else todas

    return todas


def pesquisar_pautas_virais(
    nicho_id: str = "todos",
    perfil_canal: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Utiliza a inteligência do Gemini para garimpar e sugerir ideias e temas virais
    em alta no YouTube, adaptados à identidade e linha editorial do canal.
    """
    chave = api_key or os.getenv("GEMINI_API_KEY", "").strip()

    if not chave or "sua_chave" in chave.lower():
        return obter_pautas_fallback(nicho_id)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=chave)

        nicho_texto = "mistérios gerais, conspirações e histórias dark de alta retenção"
        if nicho_id != "todos":
            for n in NICHOS_DARK:
                if n["id"] == nicho_id:
                    nicho_texto = f"nicho específico: {n['nome']} ({n['descricao']})"
                    break

        info_canal = ""
        if perfil_canal:
            info_canal = f"""
Perfil do Canal:
- Nome: {perfil_canal.get('nome_canal', 'Canal Dark')}
- Tom: {perfil_canal.get('tom', 'Sombrio e investigativo')}
- Persona: {perfil_canal.get('persona', 'Narrador imersivo')}
"""

        prompt = f"""
Você é o estrategista sênior de algoritmos do YouTube e TikTok, especialista número 1 em Canais Dark / Canais Sem Rosto (Faceless Channels) no Brasil.
Lembre-se: canal Dark significa que o criador NÃO aparece na câmera, mas o tema foca no que está VIRALIZANDO AGORA, com ganchos viscerais, narrativas dinâmicas e altíssima retenção!
Pesquise e formule 5 ideias de pautas VIRALIZÁVEIS de alta retenção (watch-time) e CTR explosivo em Português do Brasil (PT-BR).

Foco temático: {nicho_texto}
{info_canal}

Regras para cada pauta:
1. 'tema': Título altamente magnético com apelo de clique irresistível (ex: 'O Que a IA Descobriu Que os Cientistas Não Querem Divulgar', '7 Fatos Que Vão Fazer Você Duvidar da Realidade').
2. 'nicho_id': O identificador do nicho.
3. 'nicho_nome': Nome amigável do nicho.
4. 'hook_inicial': Frase de abertura de 5 segundos que prende o cérebro do espectador antes que ele consiga passar o vídeo.
5. 'revelacao_chave': O fato chocante ou conclusão que obriga a pessoa a assistir até o último segundo.
6. 'ctr_estimado': Previsão realista de CTR (ex: '12.4% CTR').
Retorne em formato JSON estrito conforme o schema.
"""
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ListaPautasVirais,
            temperature=0.7
        )

        modelo = os.getenv("GEMINI_MODEL", "gemini-3.6-flash").strip()
        modelos_tentar = [modelo, "gemini-3.6-flash", "gemini-3-flash-preview", "gemini-flash-latest"]
        
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
            return obter_pautas_fallback(nicho_id)

        dados = json.loads(resposta.text)
        pautas = dados.get("pautas", [])
        return pautas if pautas else obter_pautas_fallback(nicho_id)

    except Exception as e:
        print(f"[radar_youtube] Erro ao consultar Gemini ({e}). Usando pautas de contingência.")
        return obter_pautas_fallback(nicho_id)
