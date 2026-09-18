"""
narrator.py — Toda a inteligência do jogo via Gemini
"""

import json
import logging
import os
import random
import re
import urllib.parse
import urllib.request
import asyncio

try:
    import google.generativeai as genai
    from google.generativeai import types as gtypes
except Exception:  # O modo offline também cobre incompatibilidade do SDK.
    genai = None
    gtypes = None


log = logging.getLogger(__name__)


SYSTEM_PROMPT = """Você é um Mestre de RPG experiente e criativo especializado em D&D 5e.
Você narra aventuras épicas, dramáticas e imersivas em português do Brasil.
Seu estilo é cinematográfico, com descrições vívidas e tensão dramática adequada.
Sempre mantenha a consistência com o contexto da aventura e as escolhas dos jogadores.
Seja justo, mas desafiador. Recompense a criatividade.
Quando houver falha crítica (dado 1), o resultado deve ser catastrófico e cômico/dramático.
Quando houver sucesso crítico (dado 20), o resultado deve ser épico e memorável."""


class Narrator:
    def __init__(self, api_key: str):
        self.api_key = api_key or ""
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        self.model = None
        self.image_model = None
        self.provider_status = "offline"
        if api_key and genai is not None:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=SYSTEM_PROMPT
            )
            self.image_model = genai.GenerativeModel(
                os.getenv("GEMINI_IMAGE_MODEL", "imagen-3.0-generate-002")
            )
            self.provider_status = f"gemini:{self.model_name}"
        elif self.api_key:
            self.provider_status = f"gemini-rest:{self.model_name}"
        else:
            log.warning("Gemini indisponível; usando o narrador offline.")
        log.info("Narrador configurado: provedor=%s, imagens=%s",
                 self.provider_status,
                 os.getenv("IMAGE_PROVIDER", "pollinations"))

    # ── Iniciar aventura ──────────────────────────────────────────────────────

    async def iniciar_aventura(self, chat_id: int) -> dict:
        prompt = """Crie o início de uma aventura D&D original e envolvente.
Retorne APENAS um JSON válido (sem markdown):
{
  "titulo": "Nome épico da aventura",
  "narrativa": "Narração de abertura imersiva com 3-4 parágrafos",
  "contexto": "Resumo técnico do estado atual (localização, ameaças, objetivos, elementos do cenário)"
}"""
        aventuras = [
            {
                "titulo": "As Cinzas do Farol Antigo",
                "narrativa": "Uma luz azul desperta no farol abandonado durante a tempestade. Pegadas recentes e correntes quebradas indicam que algo despertou sob as ruínas.",
                "contexto": "Localização: Farol Antigo. Ameaça: presença desconhecida sob as ruínas. Objetivo: investigar a luz azul.",
            },
            {
                "titulo": "O Juramento da Floresta Sombria",
                "narrativa": "A floresta silencia quando uma árvore ancestral começa a sangrar seiva dourada. Um corvo deixa aos seus pés uma chave marcada com o brasão de um reino desaparecido.",
                "contexto": "Localização: clareira da Floresta Sombria. Ameaça: maldição na árvore ancestral. Objetivo: descobrir a origem da chave.",
            },
            {
                "titulo": "A Cripta sob a Cidade",
                "narrativa": "Na praça central, a terra afunda e revela degraus que descem para uma cripta esquecida. De lá vem o som de sinos, embora a cidade não tenha uma torre.",
                "contexto": "Localização: praça da cidade. Ameaça: cripta recém-aberta e sinos sobrenaturais. Objetivo: explorar as ruínas.",
            },
            {
                "titulo": "O Tremor da Montanha Vermelha",
                "narrativa": "Um tremor racha a encosta e expõe uma porta de obsidiana. Símbolos antigos brilham quando vocês se aproximam, como se a montanha reconhecesse seus nomes.",
                "contexto": "Localização: encosta da Montanha Vermelha. Ameaça: porta selada e magia antiga. Objetivo: descobrir o que está despertando.",
            },
        ]
        return await self._generate_json(prompt, random.choice(aventuras))

    # ── Criar personagem ──────────────────────────────────────────────────────

    async def criar_personagem(
        self, nome: str, classe: str, raca: str, detalhes: str = ""
    ) -> dict:
        prompt = f"""Crie uma ficha D&D 5e para:
Nome: {nome} | Classe: {classe} | Raça: {raca}
Detalhes fornecidos pelo jogador: {detalhes or "nenhum; invente uma origem coerente"}

Retorne APENAS JSON válido (sem markdown):
{{
  "atributos": {{
    "Força": <8-18>,
    "Destreza": <8-18>,
    "Constituição": <8-18>,
    "Inteligência": <8-18>,
    "Sabedoria": <8-18>,
    "Carisma": <8-18>
  }},
  "historia": "História de origem em 2-3 frases"
}}

Regras obrigatórias de D&D 5e:
- A classe não concede bônus ou penalidade de atributo; use-a apenas para
  escolher atributos recomendados e escrever a história.
- Aplique somente os bônus raciais padrão da raça escolhida.
- Não crie penalizadores raciais.
Humano: +1 em todos; Elfo: +2 Destreza, +1 Inteligência; Anão: +2 Constituição,
+1 Sabedoria; Halfling: +2 Destreza, +1 Carisma; Tiefling: +1 Inteligência,
+2 Carisma; Meio-Orc: +2 Força, +1 Constituição.
Distribua valores-base entre 8 e 15 e retorne os valores finais após os bônus.
Use os detalhes do jogador para adaptar a história, os atributos recomendados e
a personalidade, sem alterar as regras de bônus raciais."""
        atributos_base = {
            "Força": 12, "Destreza": 12, "Constituição": 12,
            "Inteligência": 12, "Sabedoria": 11, "Carisma": 11,
        }
        bonus_racial = {
            "Humano": {"Força": 1, "Destreza": 1, "Constituição": 1, "Inteligência": 1, "Sabedoria": 1, "Carisma": 1},
            "Elfo": {"Destreza": 2, "Inteligência": 1},
            "Anão": {"Constituição": 2, "Sabedoria": 1},
            "Halfling": {"Destreza": 2, "Carisma": 1},
            "Tiefling": {"Inteligência": 1, "Carisma": 2},
            "Meio-Orc": {"Força": 2, "Constituição": 1},
        }
        for atributo, bonus in bonus_racial.get(raca, {}).items():
            atributos_base[atributo] += bonus

        return await self._generate_json(prompt, {
            "atributos": atributos_base,
            "historia": (
                f"{nome} cresceu entre histórias sobre fronteiras perigosas e "
                f"aprendeu a sobreviver usando sua vocação de {classe}. "
                f"Agora, a origem {raca} de {nome} o conduz até esta aventura. "
                f"Seus traços marcantes são: {detalhes or 'curiosidade e cautela'}."
            ),
        })

    # ── Avaliar dificuldade da ação ───────────────────────────────────────────

    async def avaliar_acao(self, sessao: dict, acao: str) -> dict:
        """
        Pede ao Gemini para avaliar a ação ANTES de narrar:
        - Qual atributo usar (se não detectado automaticamente)
        - CD (Classe de Dificuldade): 5=fácil, 10=médio, 15=difícil, 20=muito difícil, 25=quase impossível
        - Se precisa de teste ou é automático
        """
        prompt = f"""CONTEXTO DA AVENTURA:
{sessao['contexto']}

AÇÃO DO JOGADOR: "{acao}"

Analise esta ação e retorne APENAS JSON válido (sem markdown):
{{
  "precisa_teste": true ou false,
  "atributo": "Força|Destreza|Constituição|Inteligência|Sabedoria|Carisma",
  "cd": <5 a 25>,
  "justificativa": "Por que este atributo e esta CD (1 frase curta)"
}}

Se a ação for trivial (andar, falar normalmente, pegar objeto em cima de uma mesa), precisa_teste=false.
Se for arriscada ou habilidosa, precisa_teste=true com CD proporcional ao risco."""
        fallback = {
            "precisa_teste": True,
            "atributo": "Destreza",
            "cd": 12,
            "justificativa": "A ação envolve risco e exige atenção ou habilidade.",
        }
        simples = re.search(
            r"\b(and(?:o|ar|ei|e)|caminh(?:o|ar|ando)|"
            r"observo|olho|espero|escuto|ouço|falo|converso|"
            r"pego|sigo|avanço|avanco|avançar|avancar|"
            r"aproximo|aproximo-me|entro|saio)\b",
            acao.lower(),
        )
        if simples and not re.search(
            r"\b(escond|furt|arrom|lutar|atacar|convencer|persuad|"
            r"investigar|procurar|examinar|perceber|saltar|escalar|"
            r"desarmar|conjurar|enganar)\w*",
            acao.lower(),
        ):
            fallback["precisa_teste"] = False
            fallback["justificativa"] = "Ação simples de deslocamento ou interação, sem teste."
        resultado = await self._generate_json(prompt, fallback)
        if simples and not re.search(
            r"\b(escond|furt|arrom|lutar|atacar|convencer|persuad|"
            r"investigar|procurar|examinar|perceber|saltar|escalar|"
            r"desarmar|conjurar|enganar)\w*",
            acao.lower(),
        ):
            resultado["precisa_teste"] = False
            resultado["justificativa"] = "Ação simples de deslocamento ou interação, sem teste."
        return resultado

    # ── Narrar ação com resultado do dado ────────────────────────────────────

    async def narrar_acao_com_dado(
        self,
        sessao: dict,
        personagem: dict,
        jogadores: list,
        acao: str,
        teste: dict | None = None   # resultado do dice.realizar_teste(), ou None se não houve teste
    ) -> dict:
        jogadores_str = ", ".join(
            f"{j['nome']} ({j['classe']} {j['raca']})" for j in jogadores
        ) or "Nenhum outro jogador"

        atributos_str = ", ".join(
            f"{k}: {v}" for k, v in personagem["atributos"].items()
        )

        # Monta o bloco do teste pra passar pro Gemini
        if teste:
            if teste["critico_sucesso"]:
                resultado_dado = f"SUCESSO CRÍTICO (dado 20 natural)! Narrar resultado ÉPICO e extraordinário."
            elif teste["falha_critica"]:
                resultado_dado = f"FALHA CRÍTICA (dado 1 natural)! Narrar resultado DESASTROSO, dramático e possivelmente cômico."
            elif teste["sucesso"]:
                resultado_dado = f"SUCESSO (rolou {teste['total']} vs CD {teste['dificuldade']}). Narrar resultado positivo."
            else:
                resultado_dado = f"FALHA (rolou {teste['total']} vs CD {teste['dificuldade']}). Narrar consequência negativa ou obstáculo."
        else:
            resultado_dado = "Ação simples sem teste, narrar normalmente."

        prompt = f"""CONTEXTO DA AVENTURA:
{sessao['contexto']}

PERSONAGEM AGINDO:
Nome: {personagem['nome']} | Classe: {personagem['classe']} | Raça: {personagem['raca']}
Atributos: {atributos_str}

OUTROS JOGADORES: {jogadores_str}

AÇÃO: "{acao}"
RESULTADO DO DADO: {resultado_dado}

Continue a aventura a partir EXATAMENTE do contexto fornecido. Não reinicie a
história, não troque a localização sem justificativa e não mencione cenas de
outras aventuras. Narre o resultado de forma cinematográfica e imersiva
respeitando EXATAMENTE o resultado do dado.
Retorne APENAS JSON válido (sem markdown):
{{
  "narrativa": "Narração do resultado (2-3 parágrafos vívidos e dramáticos)",
  "novo_contexto": "Contexto atualizado da aventura após esta ação",
  "sugestoes": ["Sugestão 1 coerente com a situação", "Sugestão 2", "Sugestão 3"]
}}"""

        contexto_atual = sessao["contexto"].strip()
        numero_acao = len(re.findall(r"(?:Última ação|Ação registrada):", contexto_atual)) + 1
        local_atual = self._localizacao_atual(contexto_atual)
        proximo_estado = (
            f"Localização: {local_atual}. "
            f"Progressão: ação {numero_acao} concluída por {personagem['nome']}; "
            f"pista ou consequência revelada após tentar {acao}. "
            "A ameaça continua ativa e o próximo passo depende das escolhas do grupo."
        )
        fallback = {
            "narrativa": (
                f"Em {local_atual}, {personagem['nome']} age e altera o rumo da cena. "
                f"A tentativa de {acao} revela uma nova pista e provoca uma "
                "consequência imediata: o ambiente reage, e o perigo se aproxima. "
                "O grupo agora precisa decidir como explorar essa mudança."
            ),
            "novo_contexto": proximo_estado,
            "sugestoes": [
                "Examino os sinais recentes na área.",
                "Avanço com o grupo mantendo a guarda.",
                "Procuro uma pista que ajude a entender a ameaça.",
            ],
        }
        return await self._generate_json(prompt, fallback)

    # ── Sugerir ações para o personagem ──────────────────────────────────────

    async def sugerir_acoes(self, sessao: dict, personagem: dict) -> dict:
        """Gera sugestões de ação personalizadas com base nos atributos e contexto."""
        atributos_str = ", ".join(
            f"{k}: {v}" for k, v in personagem["atributos"].items()
        )
        prompt = f"""CONTEXTO DA AVENTURA:
{sessao['contexto']}

PERSONAGEM:
Nome: {personagem['nome']} | Classe: {personagem['classe']} | Raça: {personagem['raca']}
Atributos: {atributos_str}

Sugira 5 ações criativas e coerentes com o contexto atual da aventura E com os pontos fortes
deste personagem (prefira ações que usem os atributos mais altos).

Retorne APENAS JSON válido (sem markdown):
{{
  "sugestoes": [
    {{"acao": "Descrição da ação", "atributo": "Atributo usado", "cd": 12, "risco": "baixo|médio|alto"}},
    {{"acao": "...", "atributo": "...", "cd": 10, "risco": "..."}},
    {{"acao": "...", "atributo": "...", "cd": 15, "risco": "..."}},
    {{"acao": "...", "atributo": "...", "cd": 8,  "risco": "..."}},
    {{"acao": "...", "atributo": "...", "cd": 18, "risco": "..."}}
  ]
}}"""
        local_atual = self._localizacao_atual(sessao["contexto"])
        return await self._generate_json(prompt, {
            "sugestoes": [
                {"acao": f"Examino os sinais em {local_atual}.", "atributo": "Sabedoria", "cd": 10, "risco": "baixo"},
                {"acao": "Avanço com a arma preparada.", "atributo": "Destreza", "cd": 12, "risco": "médio"},
                {"acao": "Procuro a origem da ameaça atual.", "atributo": "Inteligência", "cd": 14, "risco": "médio"},
                {"acao": "Tento chamar quem está por perto.", "atributo": "Carisma", "cd": 10, "risco": "baixo"},
                {"acao": "Abro à força o acesso bloqueado.", "atributo": "Força", "cd": 15, "risco": "alto"},
            ]
        })

    # ── Gerar cena (imagem) ───────────────────────────────────────────────────

    async def gerar_cena(self, sessao: dict) -> dict:
        prompt_desc = f"""Com base neste contexto de aventura D&D:
{sessao['contexto']}

Retorne APENAS JSON válido (sem markdown):
{{
  "descricao": "Descrição visual cinematográfica da cena atual em português (2-3 frases)",
  "image_prompt": "Epic fantasy D&D scene, [detailed scene in English], dramatic lighting, detailed illustration, fantasy art style"
}}"""
        contexto = sessao.get("contexto", "").strip()
        local = self._localizacao_atual(contexto)
        progresso = self._progresso_atual(contexto)
        dados = await self._generate_json(prompt_desc, {
            "descricao": (
                f"A cena atual se passa em {local}. Esta é a etapa {progresso} "
                "da aventura; o ambiente mostra a consequência mais recente da "
                "ação do grupo e permanece em estado de alerta."
            ),
            "image_prompt": (
                "Current D&D fantasy adventure scene at "
                f"{local}. Context: {contexto}. Cinematic lighting, "
                "detailed fantasy illustration, no lighthouse unless the context mentions one."
            ),
        })

        imagem_bytes = None
        try:
            if self.image_model is None or gtypes is None:
                raise RuntimeError("modelo de imagem Gemini indisponível")
            resp_img = await self.image_model.generate_content_async(
                dados["image_prompt"],
                generation_config=gtypes.GenerationConfig(
                    response_modalities=["IMAGE"]
                )
            )
            for part in resp_img.candidates[0].content.parts:
                if part.inline_data:
                    imagem_bytes = part.inline_data.data
                    break
        except Exception as e:
            log.warning("Imagem indisponível: %s", e)
            if os.getenv("IMAGE_PROVIDER", "pollinations").lower() == "pollinations":
                try:
                    encoded = urllib.parse.quote(dados["image_prompt"], safe="")
                    url = (
                        "https://image.pollinations.ai/prompt/" + encoded
                        + "?width=1024&height=768&nologo=true"
                    )
                    imagem_bytes = await asyncio.to_thread(
                        lambda: urllib.request.urlopen(url, timeout=45).read()
                    )
                    log.info("Imagem da cena gerada pelo fallback Pollinations")
                except Exception as fallback_error:
                    log.warning("Fallback de imagem indisponível: %s", fallback_error)

        return {"descricao": dados["descricao"], "imagem_bytes": imagem_bytes}

    @staticmethod
    def _localizacao_atual(contexto: str) -> str:
        """Obtém a localização mais recente, inclusive no fallback offline."""
        locais = re.findall(r"Localização:\s*([^.;]+)", contexto, flags=re.IGNORECASE)
        return locais[-1].strip() if locais else (
            contexto.split(".")[0].strip() or "a localização atual da aventura"
        )

    @staticmethod
    def _progresso_atual(contexto: str) -> int:
        etapas = re.findall(r"(?:Progressão: ação|ação registrada:)\s*(\d+)", contexto, flags=re.IGNORECASE)
        return int(etapas[-1]) if etapas else 0

    # ── Util ──────────────────────────────────────────────────────────────────

    async def _generate_json(self, prompt: str, fallback: dict) -> dict:
        if self.model is None and not self.api_key:
            return fallback
        try:
            if self.model is not None:
                resposta = await self.model.generate_content_async(prompt)
                return self._parse_json(resposta.text)
            return await self._generate_json_rest(prompt)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            log.warning("Resposta inválida do Gemini; usando fallback: %s", exc)
        except Exception as exc:
            log.warning("Falha ao consultar Gemini; usando fallback: %s", exc)
        return fallback

    async def _generate_json_rest(self, prompt: str) -> dict:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{urllib.parse.quote(self.model_name, safe='')}:generateContent"
            f"?key={urllib.parse.quote(self.api_key, safe='')}"
        )
        payload = json.dumps({
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        def call():
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))

        response = await asyncio.to_thread(call)
        text = response["candidates"][0]["content"]["parts"][0]["text"]
        return self._parse_json(text)

    def _parse_json(self, text: str) -> dict:
        clean = re.sub(r"```(?:json)?|```", "", text).strip()
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if match:
            clean = match.group()
        return json.loads(clean)
