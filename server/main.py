"""자막 통화 서버 — 번호 배정, 호출/받기/거절/끊기, 자막·입력 글·WebRTC 신호 중계, AI 요청 대행."""

import random
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from . import ai  # noqa: E402  (.env를 먼저 읽은 뒤 API 키 확인)

STATIC = Path(__file__).resolve().parent.parent / "static"
app = FastAPI(title="자막 통화")

# 상대에게 그대로 전달하는 메시지 종류
RELAY_TYPES = {"caption", "message", "typing", "rtc"}


class User:
    def __init__(self, ws: WebSocket, number: str, name: str, mode: str):
        self.ws = ws
        self.number = number
        self.name = name
        self.mode = mode  # "caption"(자막 모드) | "voice"(목소리 모드)
        self.peer: "User | None" = None  # 통화 중인 상대
        self.pending: "User | None" = None  # 호출 중(아직 받기 전)인 상대

    def info(self) -> dict:
        return {"number": self.number, "name": self.name, "mode": self.mode}

    async def send(self, msg: dict) -> None:
        try:
            await self.ws.send_json(msg)
        except Exception:
            pass


users: dict[str, User] = {}


def new_number() -> str:
    while True:
        n = "010" + "".join(random.choices("0123456789", k=8))
        if n not in users:
            return n


async def end_call(user: User, reason: str) -> None:
    """통화 또는 호출 중인 상대와의 연결을 정리하고 상대에게 알린다."""
    other = user.peer or user.pending
    user.peer = user.pending = None
    if other:
        other.peer = other.pending = None
        await other.send({"type": "ended", "reason": reason})


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    me: User | None = None
    try:
        while True:
            msg = await ws.receive_json()
            t = msg.get("type")

            if t == "register":
                number = msg.get("number")
                # 새로고침 시 같은 번호를 다시 쓰고, 이미 사용 중이면 새 번호 배정
                if not (isinstance(number, str) and len(number) == 11 and number.isdigit()) or number in users:
                    number = new_number()
                mode = msg.get("mode") if msg.get("mode") in ("caption", "voice") else "caption"
                me = User(ws, number, (msg.get("name") or "이름 없음")[:20], mode)
                users[number] = me
                await me.send({"type": "registered", "number": number})
                continue

            if me is None:
                await ws.send_json({"type": "error", "message": "먼저 등록이 필요합니다."})
                continue

            if t == "call":
                target = users.get(str(msg.get("to", "")).replace("-", ""))
                if target is None or target is me:
                    await me.send({"type": "error", "message": "연결할 수 없는 번호예요."})
                elif target.peer or target.pending:
                    await me.send({"type": "error", "message": "상대방이 통화 중이에요."})
                else:
                    me.pending, target.pending = target, me
                    await target.send({"type": "incoming", "peer": me.info()})
                    await me.send({"type": "ringing", "peer": target.info()})

            elif t == "accept" and me.pending:
                caller = me.pending
                me.pending = caller.pending = None
                me.peer, caller.peer = caller, me
                await caller.send({"type": "connected", "peer": me.info(), "role": "caller"})
                await me.send({"type": "connected", "peer": caller.info(), "role": "callee"})

            elif t == "reject" and me.pending:
                await end_call(me, "rejected")

            elif t == "hangup":
                await end_call(me, "hangup")

            elif t in RELAY_TYPES and me.peer:
                await me.peer.send({**msg, "from": me.number})

    except WebSocketDisconnect:
        pass
    finally:
        if me:
            await end_call(me, "disconnected")
            if users.get(me.number) is me:
                del users[me.number]


# ---------- AI API ----------

class Line(BaseModel):
    who: str  # "me" | "peer"
    text: str


class SuggestReq(BaseModel):
    history: list[Line]
    purpose: str = ""


class RefineReq(BaseModel):
    text: str
    history: list[Line] = []


class PrepReq(BaseModel):
    purpose: str


class SummaryReq(BaseModel):
    history: list[Line]
    purpose: str = ""


def _require_ai() -> None:
    if not ai.enabled():
        raise HTTPException(503, "AI 기능이 꺼져 있어요. 서버 .env에 ANTHROPIC_API_KEY를 설정하세요.")


@app.get("/api/config")
async def config():
    return {"ai": ai.enabled()}


@app.post("/api/suggest")
async def suggest(req: SuggestReq):
    _require_ai()
    return {"suggestions": await ai.suggest(req.history, req.purpose)}


@app.post("/api/refine")
async def refine(req: RefineReq):
    _require_ai()
    return {"refined": await ai.refine(req.text, req.history)}


@app.post("/api/prep")
async def prep(req: PrepReq):
    _require_ai()
    return await ai.prep(req.purpose)


@app.post("/api/summary")
async def summary(req: SummaryReq):
    _require_ai()
    return await ai.summarize(req.history, req.purpose)


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")
