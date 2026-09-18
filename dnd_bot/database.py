"""
database.py — Gerencia sessões, personagens e histórico de ações
"""

import sqlite3
import json
from contextlib import contextmanager
from datetime import datetime


class Database:
    def __init__(self, path: str):
        self.path = path
        self._init()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessoes (
                    chat_id     INTEGER PRIMARY KEY,
                    contexto    TEXT    NOT NULL,
                    criada_em   TEXT    NOT NULL,
                    atualizada_em TEXT  NOT NULL
                );

                CREATE TABLE IF NOT EXISTS personagens (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL,
                    chat_id     INTEGER NOT NULL,
                    nome        TEXT    NOT NULL,
                    classe      TEXT    NOT NULL,
                    raca        TEXT    NOT NULL,
                    atributos   TEXT    NOT NULL,  -- JSON
                    historia    TEXT    NOT NULL,
                    criado_em   TEXT    NOT NULL,
                    UNIQUE(user_id, chat_id)
                );

                CREATE TABLE IF NOT EXISTS acoes (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id      INTEGER NOT NULL,
                    chat_id      INTEGER NOT NULL,
                    acao         TEXT    NOT NULL,
                    resultado    TEXT    NOT NULL,
                    feita_em     TEXT    NOT NULL
                );
            """)

    # ── Sessões ──────────────────────────────────────────────────────────────

    def criar_sessao(self, chat_id: int, contexto: str):
        agora = datetime.now().isoformat()
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO sessoes (chat_id, contexto, criada_em, atualizada_em)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    contexto=excluded.contexto,
                    criada_em=excluded.criada_em,
                    atualizada_em=excluded.atualizada_em
            """, (chat_id, contexto, agora, agora))
            # Limpa personagens e ações da sessão anterior
            conn.execute("DELETE FROM personagens WHERE chat_id=?", (chat_id,))
            conn.execute("DELETE FROM acoes WHERE chat_id=?", (chat_id,))

    def obter_sessao(self, chat_id: int) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM sessoes WHERE chat_id=?", (chat_id,)
            ).fetchone()
            return dict(row) if row else None

    def atualizar_contexto(self, chat_id: int, novo_contexto: str):
        with self._conn() as conn:
            conn.execute("""
                UPDATE sessoes SET contexto=?, atualizada_em=?
                WHERE chat_id=?
            """, (novo_contexto, datetime.now().isoformat(), chat_id))

    # ── Personagens ──────────────────────────────────────────────────────────

    def salvar_personagem(
        self, user_id: int, chat_id: int,
        nome: str, classe: str, raca: str,
        atributos: dict, historia: str
    ):
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO personagens
                    (user_id, chat_id, nome, classe, raca, atributos, historia, criado_em)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, chat_id) DO UPDATE SET
                    nome=excluded.nome, classe=excluded.classe,
                    raca=excluded.raca, atributos=excluded.atributos,
                    historia=excluded.historia
            """, (
                user_id, chat_id, nome, classe, raca,
                json.dumps(atributos, ensure_ascii=False),
                historia, datetime.now().isoformat()
            ))

    def obter_personagem(self, user_id: int, chat_id: int) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM personagens WHERE user_id=? AND chat_id=?",
                (user_id, chat_id)
            ).fetchone()
            if not row:
                return None
            p = dict(row)
            p["atributos"] = json.loads(p["atributos"])
            return p

    def listar_jogadores(self, chat_id: int) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM personagens WHERE chat_id=?", (chat_id,)
            ).fetchall()
            result = []
            for r in rows:
                p = dict(r)
                p["atributos"] = json.loads(p["atributos"])
                result.append(p)
            return result

    # ── Ações / Histórico ─────────────────────────────────────────────────────

    def registrar_acao(self, user_id: int, chat_id: int, acao: str, resultado: str):
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO acoes (user_id, chat_id, acao, resultado, feita_em)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, chat_id, acao, resultado, datetime.now().isoformat()))

    def historico_recente(self, chat_id: int, limite: int = 10) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT a.*, p.nome FROM acoes a
                JOIN personagens p ON a.user_id=p.user_id AND a.chat_id=p.chat_id
                WHERE a.chat_id=?
                ORDER BY a.id DESC LIMIT ?
            """, (chat_id, limite)).fetchall()
            return [dict(r) for r in reversed(rows)]
