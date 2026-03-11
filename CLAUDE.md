# CLAUDE.md

## 프로젝트 개요

전화영어 자동 피드백 시스템. 매일 GitHub Actions로 실행되는 단일 스크립트 Python 파이프라인으로, 전화영어 수업 녹음을 처리하여 맞춤형 피드백을 제공한다.

## 아키텍처

전체 파이프라인은 `process_lesson.py` (~1140줄) 하나에 담겨 있으며, 8단계를 순서대로 실행한다:

1. **녹음 다운로드** - Google Drive에서 오늘 녹음 파일 가져오기 (`download_latest_recording`)
2. **음성 텍스트 변환** - Groq Whisper API로 받아쓰기 (`transcribe_audio`)
3. **대본 교정** - Gemini LLM으로 오타 수정 및 화자 구분 (`clean_transcript`)
4. **피드백 생성** - Gemini LLM으로 학습 피드백 작성 (`generate_feedback`)
5. **복습 웹페이지 생성** - 정적 HTML 생성 및 GitHub Pages 배포 (`generate_review_page`, `deploy_review_page`)
6. **이메일 발송** - Gmail SMTP로 피드백 + 복습 링크 전송 (`send_email`)
7. **파일 이동** - 처리 완료된 녹음을 Drive '완료' 폴더로 이동 (`move_to_done_folder`)
8. **처리 기록** - `docs/processed.txt`에 파일 ID 기록하여 중복 방지 (`save_processed_id`, `commit_processed_record`)

진입점: `main()` (1070번째 줄), `if __name__ == "__main__"`으로 호출.

## 저장소 구조

```
process_lesson.py     # 메인 파이프라인 스크립트 (모든 로직이 이 파일 하나에 있음)
requirements.txt      # Python 의존성 (google-api, requests)
docs/                 # GitHub Pages 출력 디렉토리
  index.html          # 복습 페이지 목록 (자동 생성)
  YYYY-MM-DD.html     # 날짜별 복습 페이지 (자동 생성)
  processed.txt       # 처리 완료된 Google Drive 파일 ID 목록
.github/workflows/
  english-feedback.yml   # 메인 워크플로우: 월~금 KST 09:10, 10:00 실행
  delete-review.yml      # 수동 워크플로우: 날짜 지정하여 복습 페이지 삭제
gitignore             # 참고: ".gitignore"가 아닌 "gitignore"로 되어 있음
```

## 개발 방법

### 로컬 실행

```bash
pip install -r requirements.txt
# 아래 환경변수를 먼저 설정해야 함
python process_lesson.py
```

### 필수 환경변수 (GitHub Secrets에 저장)

| 변수명 | 용도 |
|---|---|
| `GOOGLE_CREDENTIALS` | Google 서비스 계정 JSON을 Base64로 인코딩한 값 |
| `GROQ_API_KEY` | Groq API 키 (Whisper 음성 변환용) |
| `GEMINI_API_KEY` | Google Gemini API 키 (텍스트 교정 + 피드백 생성용) |
| `GMAIL_ADDRESS` | 발신용 Gmail 주소 |
| `GMAIL_APP_PASSWORD` | Gmail 앱 비밀번호 (16자리 코드) |
| `RECIPIENT_EMAIL` | 피드백 수신 이메일 주소 |
| `DRIVE_FOLDER_ID` | Google Drive 녹음 파일 소스 폴더 ID |
| `DRIVE_DONE_FOLDER_ID` | Google Drive '완료' 폴더 ID |
| `GITHUB_PAGES_URL` | GitHub Pages 복습 사이트 기본 URL |

### CI/CD

- **메인 워크플로우** (`.github/workflows/english-feedback.yml`): 월~금 UTC 00:10, 01:00 (KST 09:10, 10:00) 스케줄 실행. `workflow_dispatch`도 지원. 동시성 그룹으로 중복 실행 방지.
- **삭제 워크플로우** (`.github/workflows/delete-review.yml`): 수동 트리거로 날짜를 지정해 복습 페이지를 삭제하고 `index.html`을 재생성.

두 워크플로우 모두 `github-actions` 봇으로 `master`에 커밋 및 푸시한다.

## 핵심 규칙

- **언어**: 주석과 문서는 한국어, 코드 식별자(함수명/변수명)는 영어.
- **단일 파일 구조**: 모든 로직이 `process_lesson.py`에 있음. 모듈이나 패키지 없음.
- **LLM 폴백**: `llm_request()`는 Gemini를 먼저 시도하고, API 키가 없으면 Groq LLM으로 대체.
- **멱등성**: 처리된 파일 ID를 `docs/processed.txt`에 기록하여 중복 처리 방지.
- **안전한 종료**: 새 녹음 파일이 없으면 에러 없이 조용히 종료.
- **HTML 생성**: 복습 페이지와 인덱스는 Python 문자열로 직접 생성 (템플릿 엔진 미사용).
- **Git 연동**: `subprocess`로 git 명령어를 실행하여 생성된 페이지를 커밋/푸시.

## 커밋하면 안 되는 파일

- `.env` 또는 API 키/인증 정보가 포함된 모든 파일
- `*.json` (인증 파일)
- `*.m4a`, `*.mp3`, `*.wav` (오디오 파일)
- `__pycache__/`, `*.pyc`

## 테스트

자동화된 테스트는 없음. 변경사항 검증 방법:
1. 코드를 주의 깊게 읽고 검토
2. 가능하면 브랜치에서 `workflow_dispatch`로 수동 실행하여 테스트
3. 배포 후 GitHub Actions 로그 확인
