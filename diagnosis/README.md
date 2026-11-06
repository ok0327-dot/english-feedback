# 🔬 0단계 진단 실행 순서 (runbook)

판정 기준·표본·비교판은 [`../DIAGNOSIS_PLAN.md`](../DIAGNOSIS_PLAN.md) 에 **고정**돼 있다. 이 폴더는 그걸 실행하는 도구다.
산출물은 전부 `.diag/` (저장소에 올라가지 않음). 저장소 루트에서 `python3 -m diagnosis.<도구>` 로 실행한다.

| # | 누가 | 명령 / 할 일 | 막히면 |
|---|---|---|---|
| 1 | 🧑 | Drive '완료' 폴더에서 `whisper_raw.jsonl` + 녹음 5개 → 다운로드(zip) | — |
| 2 | 🤖 | `prep` — zip 풀기, 표본·강사 기록 짝 확인 (원본만으로) | ❌ 날은 표본 교체 + 변경 기록 |
| 3 | 🤖 | `items build` → `carrot_keys.json` 검토값 넣기(`items keys`) → `items show` → `items freeze` | 고정 전엔 아래 단계가 돌지 않음 |
| 4 | 🤖 | `run_gemini preflight` — V3·V4 최신 무료 Flash 한 번 고정 | 모두 무응답이면 V3·V4 제외 |
| 5 | 🤖 | `run_transcribe dry-run` → (관문) `run_transcribe run --go` — V7 귀 | 503 이면 나중에 다시 |
| 6 | 🤖 | `run_gemini run` — V1~V4, 섞인 순서, 하루 한도면 멈춤 → 다음 날 다시 | 여러 날 걸림 (정상) |
| 7 | 🤖 | `tasks build` → Claude 하위 에이전트가 V5·V7·V7′ 작업지 수행, 코덱스가 V6 (🧑 원본 전사 OpenAI 전송 동의 후) | — |
| 8 | 🤖 | `label make` → 🧑 바탕화면 `진단-라벨링/label.html` 에서 30줄 (10분) → `label score` | — |
| 9 | 🤖 | `measure` → 경계 사례·보정 표본을 코덱스가 판 이름 가린 채 판정 → 판정 규칙(설계서 5절) 적용 → 숫자만 보고 | — |

- 실행 기록부: `.diag/out/manifest.jsonl` (판·날짜·모델·지시문 지문·토큰)
- 업로드 기록: `.diag/upload_log.jsonl` (업로드·삭제·삭제 확인)
- 끝나면 `.diag/` 와 다운로드 폴더 zip 을 지울지 사용자에게 묻는다.
