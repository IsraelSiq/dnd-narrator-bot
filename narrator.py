"""
Narrator module with improved character history generation.
Uses Gemini API with proper prompting to avoid repeating the archetype.
"""

import os
import logging
import hashlib
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import google.genai, fall back to requests-based approach
try:
    from google import genai
    from google.genai.types import GenerateContentConfig, SafetySetting, HarmCategory, HarmBlockThreshold
    GEMINI_SDK_AVAILABLE = True
    logger.info("Gemini SDK available")
except ImportError:
    GEMINI_SDK_AVAILABLE = False
    logger.info("Gemini SDK not available, will use REST fallback")
    genai = None

# Configuration
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Temperature for creative generation (higher = more creative/varied)
CREATIVE_TEMPERATURE = 0.9
STORY_TEMPERATURE = 0.8


def _get_gemini_client():
    """Get Gemini client, preferring SDK but falling back to REST."""
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not configured")
        return None, "no_key"
    
    if GEMINI_SDK_AVAILABLE and genai:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            logger.info("Using Gemini SDK")
            return client, "sdk"
        except Exception as e:
            logger.warning(f"Gemini SDK init failed: {e}, trying REST")
    
    # REST fallback
    try:
        import requests
        logger.info("Using Gemini REST API")
        return requests, "rest"
    except ImportError:
        logger.error("No requests library for REST fallback")
        return None, "no_rest"


def generate_character_history(archetype: str, character_name: str, character_class: str) -> str:
    """
    Generate a UNIQUE character backstory based on the archetype.
    
    CRITICAL: This function must NOT simply repeat or paraphrase the archetype.
    It must create an original narrative with:
    - Specific events from the character's past
    - Relationships with NPCs (family, mentors, rivals)
    - Concrete locations and organizations
    - Personal motivations and goals
    - Conflicts and turning points
    
    Args:
        archetype: Brief description of the character concept (e.g., "ó©©©o caç©©do procurando redenç©£o")
        character_name: The character's name
        character_class: D&D class (e.g., "Paladino", "Mago")
    
    Returns:
        A unique, detailed backstory (150-250 words)
    """
    client, client_type = _get_gemini_client()
    
    if not client:
        logger.error("No Gemini client available")
        return _generate_offline_history(archetype, character_name, character_class)
    
    # CRITICAL PROMPT IMPROVEMENTS:
    # 1. Explicitly forbid repeating the archetype
    # 2. Require specific narrative elements
    # 3. Use high temperature for creativity
    # 4. Provide clear examples of what NOT to do
    
    system_instruction = """VocÅª Ø um mestre de RPG criando hist—rias de personagem ¥NICAS e DETALHADAS.

REGRA CRê¢¢ICA: NUNCA repita, parafraeie ou apenas descreva o arquØ©ipo fornecido.
Em vez disso, CRIE uma narrativa original com eventos especÌ©ficos.

Elementos OBRIGAT—RIOS na hist—ria:
1. Pelo menos 2 NPCs com nomes (familiares, mentores, rivais, aliados)
2. Pelo menos 2 locais especÌ©ficos (cidades, regiíµ¥s, construçıµØ¥s)
3. Um evento de virada especÌ©fico (traiç©£o, perda, descoberta, juramento)
4. Uma organizaç©£o ou grupo (guilda, templo, exØ©rcito, corte)
5. Motivaç©£o pessoal concreta (vinganç©£, redenç©£o, poder, proteç©£o)

ESTRUTURA:
- Comece com a origem (onde nasceu, famÌ©lia)
- Descreva 2-3 eventos formativos da juventude
- Inclua um conflito ou perda significativa
- Termine com o objetivo atual do personagem

TOM: Narrativo, em 3a pessoa, 150-250 palavras.

EXEMPLO DO QUE NÃµ FAZER:
"Este Ø um guerreiro caÌ©do que busca redenç©£o." (ISSO Ø REPETIR O ARQUê¢¢IPO!)

EXEMPLO DO QUE FAZER:
"Nascido nas ruas de Baldur's Gate, Kael era filho de um ferreiro e uma clØ©riga de Tyr..."
"""
    
    user_prompt = f"""Crie a hist—ria de fundo para:
- Nome: {character_name}
- Classe: {character_class}
- ArquØ©ipo: {archetype}

Importante: O arquØ©ipo acima Ø apenas o CONCEITO. Sua tarefa Ø criar uma hist—ria COMPLETA e ¥NICA,
nÆ£O descrever o arquØ©ipo. Invente NPCs, locais, eventos e motivaçıµØ¥s especÌ©ficas.

Hist—ria:"""
    
    try:
        if client_type == "sdk":
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_prompt,
                config=GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=CREATIVE_TEMPERATURE,
                    top_p=0.95,
                    max_output_tokens=500,
                    safety_settings=[
                        SafetySetting(category=HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=HarmBlockThreshold.BLOCK_NONE),
                        SafetySetting(category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=HarmBlockThreshold.BLOCK_NONE),
                    ]
                )
            )
            result = response.text.strip()
        else:  # REST
            import requests
            headers = {"Content-Type": "application/json"}
            params = {"key": GEMINI_API_KEY}
            payload = {
                "contents": [{"parts": [{"text": user_prompt}]}],
                "generationConfig": {
                    "temperature": CREATIVE_TEMPERATURE,
                    "topP": 0.95,
                    "maxOutputTokens": 500,
                },
                "systemInstruction": {"parts": [{"text": system_instruction}]},
                "safetySettings": [
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                ]
            }
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
            resp = requests.post(url, headers=headers, params=params, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            result = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        
        # VALIDAÇªO: Verificar se nÆ£o estÆ¡ apenas repetindo o arquØ©ipo
        archetype_words = set(archetype.lower().split())
        result_words = set(result.lower().split())
        
        # Se mais de 60% das palavras do arquØ©tipo estiverem no resultado, Ø suspeito
        overlap = len(archetype_words & result_words) / max(len(archetype_words), 1)
        if overlap > 0.6 and len(archetype_words) > 3:
            logger.warning(f"History may be repeating archetype (overlap: {overlap:.2f}). Regenerating...")
            # Tentar novamente com temperatura ainda mais alta
            return generate_character_history_retry(archetype, character_name, character_class, temperature=1.0)
        
        logger.info(f"Generated character history for {character_name} ({len(result)} chars)")
        return result
        
    except Exception as e:
        logger.error(f"Gemini generation failed: {e}")
        return _generate_offline_history(archetype, character_name, character_class)


def generate_character_history_retry(archetype: str, character_name: str, character_class: str, temperature: float = 1.0) -> str:
    """Retry with even higher temperature if first attempt was too similar to archetype."""
    client, client_type = _get_gemini_client()
    
    if not client:
        return _generate_offline_history(archetype, character_name, character_class)
    
    system_instruction = f"""Crie uma hist—ria COMPLETAMENTE DIFERENTE do arquØ©ipo.
ArquØ©ipo fornecido: "{archetype}"
NUNCA use essas palavras na resposta.
Invente NPCs, locais e eventos do zero."""
    
    user_prompt = f"""Personagem: {character_name} ({character_class})
Crie uma hist—ria ¥NICA com nomes especÌ©ficos, locais e eventos.
NÆ£O descreva o arquØ©ipo, crie narrativa original."""
    
    try:
        if client_type == "sdk":
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_prompt,
                config=GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=temperature,
                    top_p=0.95,
                    max_output_tokens=500,
                )
            )
            return response.text.strip()
        else:
            import requests
            headers = {"Content-Type": "application/json"}
            params = {"key": GEMINI_API_KEY}
            payload = {
                "contents": [{"parts": [{"text": user_prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "topP": 0.95,
                    "maxOutputTokens": 500,
                },
                "systemInstruction": {"parts": [{"text": system_instruction}]},
            }
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
            resp = requests.post(url, headers=headers, params=params, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        logger.error(f"Retry failed: {e}")
        return _generate_offline_history(archetype, character_name, character_class)


def _generate_offline_history(archetype: str, character_name: str, character_class: str) -> str:
    """
    Fallback offline generator - creates varied templates to avoid repetition.
    Uses character name hash to select different templates deterministically.
    """
    # Hash the character name to get consistent but varied results
    name_hash = int(hashlib.md5(character_name.encode()).hexdigest(), 16)
    template_idx = name_hash % 5  # 5 different templates
    
    # Templates com variaç©£o baseada no nome
    templates = [
        f"{character_name} cresceu nas terras fronteiriç©£s, onde aprendeu que a sobrevivÅªncia depende de astÙ©cia e coragem. "
        f"Seu mentor, o velho {['Theron', 'Aldric', 'Gareth', 'Draven', 'Silas'][name_hash % 5]}, ensinou-lhe os caminhos do(a) {character_class}. "
        f"Ap—s perder sua famÌ©lia para um ataque de criaturas das sombras, {character_name} jurou proteger os inocentes.",
        
        f"Nascido(a) na cidade mercantil de {['Porto Vermelho', 'Valepedra', 'Torre Alta', 'MarØ©lia', 'Ferroforte'][name_hash % 5]}, "
        f"{character_name} descobriu seu talento para o(a) {character_class} ainda jovem. "
        f"Treinou sob tutela da guilda local atØ© que uma traiç©£o o(a) forç©©u a fugir. Agora busca justiç©£.",
        
        f"Ó© filho(a) de uma linhagem antiga de {character_class}s, mas rejeitou as tradiçıµØ¥s da famÌ©lia. "
        f"{['Sua irmÆ£', 'Seu irmÆ£o', 'Sua mÆ£e', 'Seu pai', 'Sua tia'][name_hash % 5]}, {['Lyra', 'Morgana', 'Elena', 'Cassandra', 'Seraphina'][name_hash % 5]}, "
        f"ainda tenta convencÅª-lo(a) a voltar. {character_name}, porØ©m, trilha seu pr—prio caminho.",
        
        f"Durante a guerra dos {['TrÅªs Reinos', 'Cinco ExØ©rcitos', 'Sete Mares', 'Dois S—is', 'Quatro Ventos'][name_hash % 5]}, "
        f"{character_name} serviu como {character_class} no exØ©rcito. "
        f"Testemunhou horrores que o(a) marcaram para sempre. Desertou e agora vaga pelo mundo buscando redenç©£o.",
        
        f"{character_name} era um(a) {['estudante', 'artesÆ£o', 'comerciante', 'soldado', 'caç©©dor'][name_hash % 5]} comum "
        f"atØ© o dia em que encontrou um artefato antigo nas ruÌ©nas de {['Valmora', 'Drakmoor', 'Shadowfen', 'Ironhold', 'Windmere'][name_hash % 5]}. "
        f"O objeto despertou poderes latentes, transformando-o(a) no(a) {character_class} que Ø hoje."
    ]
    
    history = templates[template_idx]
    logger.info(f"Generated offline history for {character_name} (template {template_idx})")
    return history


def generate_scene_description(context: str, action: str) -> str:
    """Generate atmospheric scene description based on current context and player action."""
    client, client_type = _get_gemini_client()
    
    if not client:
        return _generate_offline_scene(context, action)
    
    system_instruction = """VocÅª Ø o narrador de uma aventura de RPG. Descreva cenas de forma imersiva e atmosfØ©rica.
Use descriçıµØ¥s sensoriais (visÆ£o, sons, cheiros, texturas).
Mantenha o mistØ©rio quando apropriado.
Escreva em 3a pessoa, 100-200 palavras."""
    
    user_prompt = f"""Contexto atual: {context}
Aç©£o do jogador: {action}

Descreva a cena resultante de forma imersiva:"""
    
    try:
        if client_type == "sdk":
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=user_prompt,
                config=GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=STORY_TEMPERATURE,
                    top_p=0.9,
                    max_output_tokens=400,
                )
            )
            return response.text.strip()
        else:
            import requests
            headers = {"Content-Type": "application/json"}
            params = {"key": GEMINI_API_KEY}
            payload = {
                "contents": [{"parts": [{"text": user_prompt}]}],
                "generationConfig": {
                    "temperature": STORY_TEMPERATURE,
                    "topP": 0.9,
                    "maxOutputTokens": 400,
                },
                "systemInstruction": {"parts": [{"text": system_instruction}]},
            }
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
            resp = requests.post(url, headers=headers, params=params, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as e:
        logger.error(f"Scene generation failed: {e}")
        return _generate_offline_scene(context, action)


def _generate_offline_scene(context: str, action: str) -> str:
    """Offline fallback for scene generation."""
    scenes = [
        "O ambiente se transforma ao seu redor. Sombras danç©£am nas paredes enquanto o ar fica carregado de expectativa.",
        "VocÅª sente uma presenç©£a antiga observando. O silÅªncio Ø quebrado apenas pelo som distante de algo se movendo.",
        "A atmosfera muda drasticamente. Uma brisa fria traz consigo o cheiro de algo esquecido hÆ¡ muito tempo.",
        "Luzes tremulam no horizonte. Algo estÆ¡ para acontecer, e vocÅª Ø o centro disso tudo.",
        "O chÆ£o treme levemente. Forç©£s antigas despertam, respondendo ao seu chamado."
    ]
    
    idx = int(hashlib.md5((context + action).encode()).hexdigest(), 16) % len(scenes)
    return scenes[idx]