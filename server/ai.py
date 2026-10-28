"""대화형 AI(Claude API) — 통화 준비, 답변 추천, 짧은 말 다듬기, 통화 요약."""

import os
from typing import Literal

from anthropic import AsyncAnthropic
from pydantic import BaseModel

MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-5-5")  # 빠른 응답·낮은 비용을 위한 경량 모델
MAX_LINES = 30  # 요청마다 최근 대화만 전송

_client: AsyncAnthropic | None = None


def enabled() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic()
    return _client


def _transcript(history) -> str:
    lines = history[-MAX_LINES:]
    return "\n".join(f"{'나' if l.who == 'me' else '상대'}: {l.text}" for l in lines) or "(아직 대화 없음)"


async def _ask(system: str, prompt: str, schema: type[BaseModel], max_tokens: int = 2000):
    resp = await client().messages.parse(
        model=MODEL,
        max_tokens=max_tokens,
        output_config={"effort": "low"},
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_format=schema,
    )
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise RuntimeError("AI 응답을 받지 못했어요.")
    return resp.parsed_output


BASE = (
    "너는 청각장애인이 자막으로 통화하도록 돕는 보조 AI다. "
    "'나'는 청각장애인 사용자, '상대'는 통화 상대방이다. "
    "통화 기록은 음성 인식 결과라 오타가 있을 수 있다."
)


# ---------- 통화 중: 답변 3개 추천 ----------

class Suggestions(BaseModel):
    suggestions: list[str]


async def suggest(history, purpose: str = "") -> list[str]:
    prompt = (
        (f"통화 목적: {purpose}\n" if purpose else "")
        + f"통화 기록:\n{_transcript(history)}\n\n"
        "상대의 마지막 말에 '나'가 바로 보낼 수 있는 답변 3개를 만들어라. "
        "서로 방향이 다르게(예: 수락·질문·보류), 각 25자 이내의 짧은 존댓말로. "
        "기록에 없는 구체적 정보(이름, 번호 등)는 지어내지 마라."
    )
    out = await _ask(BASE, prompt, Suggestions, 1000)
    return [s.strip() for s in out.suggestions if s.strip()][:3]


# ---------- 통화 중: 짧은 말 다듬기 ----------

class Refined(BaseModel):
    refined: str


async def refine(text: str, history) -> str:
    prompt = (
        f"최근 대화:\n{_transcript(history[-6:])}\n\n"
        f"'나'가 입력한 말: {text}\n\n"
        "단어 나열, 조사 생략, 한국수어식 어순으로 쓴 입력을 통화 상대에게 말하듯 자연스러운 존댓말 한 문장으로 바꿔라. "
        "뜻을 바꾸거나 입력에 없는 정보를 추가하지 마라. 이미 자연스러운 문장이면 그대로 돌려줘라."
    )
    out = await _ask(BASE, prompt, Refined, 500)
    return out.refined.strip()


# ---------- 통화 전: 통화 준비 도우미 ----------

class QA(BaseModel):
    question: str
    answer: str


class Prep(BaseModel):
    greeting: str
    qa: list[QA]


async def prep(purpose: str) -> dict:
    prompt = (
        f"통화 목적: {purpose}\n\n"
        "이 통화를 시작할 첫인사 한 문장(자막으로 통화한다는 안내 포함)과, "
        "상대가 물어볼 만한 질문 6~8개와 각각에 '나'가 보낼 답변(30자 이내 존댓말)을 만들어라. "
        "사용자만 아는 정보(이름, 생년월일, 예약 번호 등)는 답변에 [이름]처럼 대괄호 빈칸으로 남겨라."
    )
    out = await _ask(BASE, prompt, Prep, 2000)
    return out.model_dump()


# ---------- 통화 후: 요약과 목적 달성 여부 ----------

class Summary(BaseModel):
    summary: list[str]
    goal: Literal["달성", "일부 달성", "미달성", "판단 어려움"]
    goal_reason: str


async def summarize(history, purpose: str = "") -> dict:
    prompt = (
        (f"통화 목적: {purpose}\n" if purpose else "통화 목적: (설정 안 함)\n")
        + f"통화 기록:\n{_transcript(history)}\n\n"
        "날짜·시간·장소·인원·금액 등 확정된 핵심 정보만 3~5줄로 요약하라. "
        "기록에 없는 내용은 추측하지 말고, 인식 오류가 의심되는 부분은 '(불확실)'로 표시하라. "
        "통화 목적이 있으면 달성 여부와 이유를 한 문장으로 판단하라. 목적이 없으면 '판단 어려움'."
    )
    out = await _ask(BASE, prompt, Summary, 1500)
    return out.model_dump()
