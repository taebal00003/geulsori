# 자막 통화 — 청각장애인을 위한 AI 자막·음성 변환 통화 서비스

인공지능서비스개발II 11조 팀 프로젝트 (기획서 6장 시스템 구조 기준)

## 구조
| 경로 | 내용 |
|---|---|
| `server/main.py` | FastAPI 서버: 11자리 번호 배정, 호출·받기·거절·끊기, WebSocket(`/ws`) 중계(자막·입력 글·입력 중 표시·WebRTC 신호), AI REST API |
| `server/ai.py` | Claude API: 통화 준비(`/api/prep`), 답변 3개 추천(`/api/suggest`), 짧은 말 다듬기(`/api/refine`), 요약·목적 달성(`/api/summary`) |
| `static/index.html` | 프론트엔드 단일 파일: 설정·홈·발신/수신·통화·종료 화면, STT/TTS(Web Speech API), 직접 말하기(WebRTC), 중요 정보 강조 |

## 실행
```bash
pip install -r requirements.txt
cp .env.example .env   # ANTHROPIC_API_KEY 입력 (없으면 AI 기능만 꺼짐)
python -m uvicorn server.main:app --port 8000
```
- PC 크롬에서 `http://localhost:8000` 접속 (localhost는 마이크 허용됨)
- 휴대폰 테스트: `ngrok http 8000`으로 만든 HTTPS 주소로 접속 (휴대폰 브라우저는 HTTPS에서만 마이크 허용)

## Render 배포
1. [render.com](https://render.com)에 GitHub 계정으로 가입
2. **New → Blueprint** → 이 저장소 선택 (`render.yaml` 설정이 자동 적용)
3. `ANTHROPIC_API_KEY` 값 입력 후 **Apply**
4. 배포가 끝나면 `https://geulsori.onrender.com` 같은 HTTPS 주소로 접속

무료 플랜은 15분 정도 접속이 없으면 잠들어 첫 접속에 30초~1분이 걸린다.

## WebSocket 메시지
| 보냄 | 받음 |
|---|---|
| `register {name, mode, number?}` | `registered {number}` |
| `call {to}` | 발신자 `ringing {peer}` / 수신자 `incoming {peer}` |
| `accept` / `reject` / `hangup` | `connected {peer, role}` / `ended {reason}` |
| `caption {text, final}` · `message {text}` · `typing {on}` · `rtc {data}` | 상대에게 그대로 중계 (+`from`) |
