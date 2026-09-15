# -*- coding: utf-8 -*-
import os, sys
from dotenv import load_dotenv
load_dotenv()

import banco_dados
from gerador_imagens import gerar_imagem_gemini_nano_banana
from gerador_audio import sintetizar_audio_edge_tts
from radar_youtube import obter_nichos_dark, pesquisar_pautas_virais

def testar_banco_e_perfil():
    print('[TEST 1/4] Testando Perfil do Canal e Historico no SQLite...')
    banco_dados.inicializar_banco()
    perfil = {
        'nome_canal': 'Arquivos Secretos BR',
        'nicho_principal': 'Arquivos Secretos',
        'tom_narrativo': 'Sombrio, conspiratorio e investigativo',
        'persona_narrador': 'Narrador documental'
    }
    banco_dados.salvar_perfil_canal(perfil)
    obtido = banco_dados.obter_perfil_canal()
    assert obtido['nome_canal'] == perfil['nome_canal']
    
    pauta = {
        'tema': 'O Incidente Secreto da Ilha da Trindade',
        'nicho_id': 'arquivos_secretos',
        'hook_inicial': 'Em 1958, a Marinha do Brasil registrou algo inexplicable.',
        'revelacao_chave': 'O dossie oficial permaneceu secreto.',
        'status': 'planejado'
    }
    banco_dados.salvar_pauta_historico(pauta)
    hist = banco_dados.listar_pautas_historico(5)
    assert len(hist) >= 1
    print(' -> SQLite Perfil e Pautas: SUCESSO!')

def testar_radar_youtube():
    print('[TEST 2/4] Testando Radar de Nichos e Pautas do YouTube...')
    nichos = obter_nichos_dark()
    assert len(nichos) >= 5
    perfil = banco_dados.obter_perfil_canal()
    pautas = pesquisar_pautas_virais(nicho_id='oceanos_e_abismos', perfil_canal=perfil)
    assert len(pautas) >= 1
    assert 'tema' in pautas[0]
    print(f' -> Radar YouTube: SUCESSO! ({len(pautas)} pautas geradas)')

def testar_audio_neural_ptbr():
    print('[TEST 3/4] Testando Audio Neural Brasileiro (Edge-TTS pt-BR-AntonioNeural)...')
    os.makedirs('output/audios', exist_ok=True)
    caminho = os.path.join('output', 'audios', 'teste_unitario_ptbr.mp3')
    if os.path.exists(caminho):
        os.remove(caminho)
    texto = 'Bem-vindos aos arquivos proibidos. O que voce vai ouvir a seguir mudara sua percepcao.'
    sucesso = sintetizar_audio_edge_tts(texto, caminho, voz='pt-BR-AntonioNeural')
    assert sucesso is True
    assert os.path.exists(caminho)
    assert os.path.getsize(caminho) > 5000
    print(' -> Audio Neural PT-BR: SUCESSO!')

def testar_nano_banana():
    print('[TEST 4/4] Testando Google Nano Banana (gemini-3.1-flash-image)...')
    os.makedirs('output/imagens', exist_ok=True)
    caminho = os.path.join('output', 'imagens', 'teste_unitario_banana.jpg')
    if os.path.exists(caminho):
        os.remove(caminho)
    prompt = 'Dark documentary shot, secret underground bunker entrance concealed in foggy forest, 8k'
    sucesso = gerar_imagem_gemini_nano_banana(prompt, caminho, aspect_ratio='16:9')
    assert sucesso is True
    assert os.path.exists(caminho)
    assert os.path.getsize(caminho) > 10000
    print(' -> Google Nano Banana: SUCESSO!')

if __name__ == '__main__':
    print('=' * 60)
    print('INICIANDO SUITE DE TESTES AUTOMATIZADOS DARKAI')
    print('=' * 60)
    testar_banco_e_perfil()
    testar_radar_youtube()
    testar_audio_neural_ptbr()
    testar_nano_banana()
    print('=' * 60)
    print('TODOS OS 4 TESTES FORAM APROVADOS COM SUCESSO TOTAL!')
    print('=' * 60)
