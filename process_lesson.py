"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    🗺️ 전체 프로그램 지도 (한눈에 보기)                      ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║  이 프로그램은 "전화영어 자동 피드백 시스템"의 두뇌(핵심 로직)입니다.       ║
║  매일 아침 전화영어 수업이 끝나면, 아래 7단계가 자동으로 순서대로 실행됩니다: ║
║                                                                            ║
║  [1단계] 📥 Google Drive 창고에서 오늘 녹음 파일을 가져옴                   ║
║          → 비유: 택배 기사가 창고에서 오늘 도착한 택배(녹음)를 꺼내오는 것   ║
║                                                                            ║
║  [2단계] 🎤 녹음 파일을 텍스트로 변환 (Groq Whisper)                       ║
║          → 비유: 속기사가 음성을 듣고 받아쓰기 하는 것                      ║
║                                                                            ║
║  [3단계] 🔍 받아쓰기 내용을 교정 (Groq Llama - 전처리)                     ║
║          → 비유: 교정 선생님이 속기사의 받아쓰기 오타를 잡고,               ║
║                  "이건 선생님 말, 이건 학생 말"로 구분해주는 것              ║
║                                                                            ║
║  [4단계] 🤖 교정된 내용으로 학습 피드백 생성 (Groq Llama - 피드백)          ║
║          → 비유: 영어 과외 선생님이 수업 내용을 분석하고 성적표를 써주는 것  ║
║                                                                            ║
║  [5단계] 🌐 복습 웹페이지 생성 & 인터넷에 공개 (GitHub Pages)              ║
║          → 비유: 오늘의 학습지를 인쇄해서 게시판에 붙이는 것                ║
║                                                                            ║
║  [6단계] 📧 회사 메일로 피드백 + 복습 링크 발송 (Gmail)                    ║
║          → 비유: 완성된 성적표를 우편으로 보내는 것                         ║
║                                                                            ║
║  [7단계] 📦 처리 끝난 녹음 파일을 '완료' 폴더로 이동 (Google Drive)        ║
║          → 비유: 처리된 택배를 '배송완료' 창고로 옮기는 것                  ║
║                                                                            ║
║  ⚠️ 만약 오늘 녹음 파일이 없으면? (수업 없는 날, 동기화 지연 등)           ║
║     → 에러 없이 조용히 "오늘은 할 일 없음"으로 종료됩니다.                 ║
║     → GitHub Actions 로그에 빨간 X가 뜨지 않으니 걱정 안 해도 됩니다.      ║
║                                                                            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

# ┌─────────────────────────────────────────────────────────────────────────┐
# │                         📦 도구 상자 열기                               │
# │                                                                         │
# │  아래는 이 프로그램이 사용하는 "도구(라이브러리)"들을 불러오는 부분입니다. │
# │  요리를 시작하기 전에 냄비, 칼, 도마를 꺼내놓는 것과 같습니다.           │
# │  이 부분은 수정할 일이 거의 없습니다.                                    │
# └─────────────────────────────────────────────────────────────────────────┘

import os          # 파일/폴더를 다루는 도구 (파일 삭제, 경로 확인 등)
import io          # 데이터를 메모리에 임시 저장하는 도구 (파일 다운로드 시 사용)
import sys         # 프로그램을 종료시키는 도구 (exit 등)
import json        # JSON 형식 데이터를 읽고 쓰는 도구 (API 통신에 필수)
import time        # 대기(sleep) 기능 — API 속도 제한 시 재시도 대기에 사용
import base64      # 데이터를 암호화/복호화하는 도구 (Google 인증 정보 처리)
import smtplib     # 이메일을 보내는 도구 (Gmail SMTP 서버와 통신)
import subprocess  # 터미널 명령어를 실행하는 도구 (git push 등)
import requests    # 인터넷 API에 요청을 보내는 도구 (Groq, Gemini와 통신)
import re          # 텍스트 패턴을 찾고 바꾸는 도구 (마크다운→HTML 변환에 사용)
import glob        # 파일 목록을 검색하는 도구 (복습 페이지 목록 생성에 사용)
import html as html_module  # HTML 특수문자를 안전하게 처리하는 도구
from datetime import datetime, timezone, timedelta  # 날짜/시간을 다루는 도구
from email.mime.text import MIMEText                # 이메일 본문을 만드는 도구
from email.mime.multipart import MIMEMultipart      # 이메일에 여러 형식을 담는 도구

# Google Drive와 통신하기 위한 도구들
from google.oauth2 import service_account           # Google 서비스 인증 도구
from googleapiclient.discovery import build         # Google API 연결 도구
from googleapiclient.http import MediaIoBaseDownload  # 파일 다운로드 도구


# ┌─────────────────────────────────────────────────────────────────────────┐
# │                    🔑 환경변수 (비밀 열쇠 보관함)                        │
# │                                                                         │
# │  아래는 이 프로그램이 외부 서비스에 접속하기 위한 "비밀번호/열쇠"들입니다. │
# │  실제 값은 GitHub의 Settings → Secrets에 저장되어 있고,                  │
# │  프로그램이 실행될 때 자동으로 불러와집니다.                              │
# │                                                                         │
# │  ⚠️ 중요: 이 값들을 코드에 직접 적으면 안 됩니다!                       │
# │     비밀번호를 포스트잇에 써서 모니터에 붙이는 것과 같은 보안 위험입니다. │
# │     반드시 GitHub Secrets에서만 관리하세요.                               │
# │                                                                         │
# │  🔧 값을 바꿔야 할 때:                                                  │
# │     GitHub 레포 → Settings → Secrets and variables → Actions             │
# │     → 해당 Secret 클릭 → Update                                         │
# └─────────────────────────────────────────────────────────────────────────┘

# Google Drive에 접속하기 위한 "신분증" (서비스 계정 JSON을 Base64로 변환한 것)
# → 셋업 가이드 2단계에서 만든 값입니다.
# → 바꿔야 할 때: Google Cloud Console에서 새 키 발급 → base64 변환 → Secret 업데이트
GOOGLE_CREDENTIALS = os.environ["GOOGLE_CREDENTIALS"]

# Groq Whisper API의 "출입증" (음성→텍스트 변환 서비스)
# → console.groq.com 에서 발급 (sk-... 로 시작)
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

# Google Gemini API의 "출입증" (현재 미사용 - 향후 복습 기능 등에 활용 가능)
# → aistudio.google.com/apikey 에서 발급 (AI... 로 시작)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# 이메일을 보내는 데 사용할 Gmail 주소 (예: "myname@gmail.com")
GMAIL_ADDRESS = os.environ["GMAIL_ADDRESS"].strip()

# Gmail "앱 비밀번호" (일반 비밀번호와 다름! 16자리 코드)
# → Google 계정 → 보안 → 앱 비밀번호에서 생성
# ⚠️ .strip()으로 복사 시 들어갈 수 있는 공백/특수문자 제거
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"].strip().replace('\xa0', '')

# 피드백을 받을 이메일 주소 (기본값: 민욱 님의 회사 메일)
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", "minuk-kang@skgas.co.kr")

# Google Drive에서 녹음 파일이 올라오는 폴더의 고유 ID
# → Drive 폴더 URL의 맨 뒤 긴 문자열
# → 예: https://drive.google.com/drive/folders/1aBcDeFgHiJkLmN ← 이 부분
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "")

# 처리 끝난 녹음 파일을 옮길 "완료" 폴더 ID (미설정 시 이동 건너뜀)
DRIVE_DONE_FOLDER_ID = os.environ.get("DRIVE_DONE_FOLDER_ID", "")

# GitHub Pages 복습 페이지의 기본 URL
# → 예: "https://myusername.github.io/english-feedback"
GITHUB_PAGES_URL = os.environ.get("GITHUB_PAGES_URL", "")

# 한국 표준시(KST) 설정. GitHub 서버는 영국 시간(UTC)이므로 +9시간 보정 필요
KST = timezone(timedelta(hours=9))


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  [1단계] 📥 Google Drive에서 녹음 파일 가져오기                        ║
# ║  비유: 택배 기사가 물류 창고에서 오늘 도착한 택배를 찾아오는 과정       ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def get_drive_service(readonly=True):
    """
    Google Drive "창고"에 들어가기 위한 출입증을 만드는 함수.
    readonly=True → 읽기만 가능 / False → 파일 이동/삭제도 가능
    보안을 위해 평소에는 읽기 전용만 쓰고, 파일 이동 시에만 전체 권한 사용.
    """
    # Base64로 암호화된 인증 정보를 원래 형태(JSON)로 복원
    creds_json = base64.b64decode(GOOGLE_CREDENTIALS)
    creds_dict = json.loads(creds_json)
    scopes = (
        ["https://www.googleapis.com/auth/drive.readonly"]
        if readonly
        else ["https://www.googleapis.com/auth/drive"]
    )
    credentials = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=scopes
    )
    # 출입증으로 Google Drive API에 연결
    return build("drive", "v3", credentials=credentials)


def download_latest_recording(service):
    """
    Google Drive에서 "오늘"에 올라온 가장 최신 녹음 파일을 찾아 다운로드.
    파일이 없으면 (None, None, None)을 돌려줌 → 프로그램이 조용히 종료됨.
    """
    today = datetime.now(KST).strftime("%Y-%m-%d")
    today_start = f"{today}T00:00:00+09:00"

    # 검색 조건: 오늘 생성 + 휴지통 아님 + 오디오 파일
    # 비유: "오늘 들어온 택배 중 음성 파일만 찾아주세요"
    query_parts = [
        f"createdTime >= '{today_start}'",
        "trashed = false",
        "(mimeType contains 'audio/' or mimeType contains 'video/mp4')",
    ]
    if DRIVE_FOLDER_ID:
        query_parts.append(f"'{DRIVE_FOLDER_ID}' in parents")

    results = service.files().list(
        q=" and ".join(query_parts),
        orderBy="createdTime desc",   # 최신순 정렬
        pageSize=5,
        fields="files(id, name, mimeType, createdTime)",
    ).execute()

    files = results.get("files", [])
    if not files:
        return None, None, None  # 파일 없음 → 메인 함수에서 조용히 종료

    target = files[0]  # 가장 최근 파일
    print(f"📁 파일 발견: {target['name']} ({target['createdTime']})")

    # 파일 다운로드 (비유: 택배를 트럭에 싣는 과정)
    request = service.files().get_media(fileId=target["id"])
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    # 임시 파일로 저장
    buffer.seek(0)
    ext = os.path.splitext(target["name"])[1] or ".m4a"
    local_path = f"/tmp/recording{ext}"
    with open(local_path, "wb") as f:
        f.write(buffer.read())

    print(f"✅ 다운로드 완료: {local_path} ({os.path.getsize(local_path)/1024/1024:.1f}MB)")
    return local_path, target["name"], target["id"]


def move_to_done_folder(file_id):
    """
    처리 끝난 녹음 파일을 '완료' 폴더로 이동 (보안 + 용량 관리).
    DRIVE_DONE_FOLDER_ID 미설정 시 건너뜀. 실패해도 전체 프로세스는 계속됨.
    비유: 처리된 택배를 "접수" 선반에서 "배송완료" 선반으로 옮기는 것.
    """
    if not DRIVE_DONE_FOLDER_ID:
        print("ℹ️ DRIVE_DONE_FOLDER_ID 미설정 → 파일 이동 건너뜀")
        return
    try:
        service = get_drive_service(readonly=False)  # 쓰기 권한으로 접속
        file_info = service.files().get(fileId=file_id, fields="parents").execute()
        prev_parents = ",".join(file_info.get("parents", []))
        service.files().update(
            fileId=file_id,
            addParents=DRIVE_DONE_FOLDER_ID,
            removeParents=prev_parents,
            fields="id, parents",
        ).execute()
        print(f"📦 파일을 '완료' 폴더로 이동 완료")
    except Exception as e:
        print(f"⚠️ 파일 이동 실패 (치명적이지 않음): {e}")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  [2단계] 🎤 녹음 파일을 텍스트로 변환 (Groq Whisper)                   ║
# ║  비유: 속기사에게 녹음을 주면서 "영어로 받아쓰기 해주세요"              ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def transcribe_audio(audio_path):
    """
    음성 파일 → 텍스트 변환. Groq Whisper API(무료) 사용.
    흔한 에러: API 키 만료, 파일 25MB 초과, 서버 일시 장애
    """
    print("🎤 음성 전사 중...")
    with open(audio_path, "rb") as f:
        response = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": (os.path.basename(audio_path), f)},
            data={
                "model": "whisper-large-v3",       # 가장 정확한 모델
                "language": "en",                   # 음성 언어: 영어
                "response_format": "verbose_json",  # 상세 결과 (녹음 길이 포함)
            },
            timeout=120,  # 최대 2분 대기
        )
    if response.status_code != 200:
        raise Exception(f"Groq API 오류 ({response.status_code}): {response.text}")

    result = response.json()
    transcript = result.get("text", "")
    duration = result.get("duration", 0)
    print(f"✅ 전사 완료: {len(transcript)}자, {duration:.0f}초")
    return transcript, duration


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  [3단계] 🔍 전사 내용 보정 (Groq Llama - 전처리)                      ║
# ║  비유: 교정 선생님이 속기사의 오타를 잡고 화자를 구분해주는 것          ║
# ║  왜 필요? 전화 음질 한계 + 한국인 발음 특성 → 오인식 발생              ║
# ║  💡 Groq는 Gemini보다 무료 한도가 넉넉하고 속도가 빠름!               ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def groq_llm_request(prompt, max_tokens=4096, temperature=0.3, timeout=120, system_msg=None):
    """
    Groq LLM API 호출 (Llama 3.3 70B 모델 사용).
    Gemini보다 무료 한도가 넉넉하고 응답 속도가 매우 빠름.
    429 에러 시 자동 재시도 (최대 3회).
    """
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    messages = []
    if system_msg:
        messages.append({"role": "system", "content": system_msg})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    for attempt in range(3):
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        elif response.status_code == 429:
            wait = 30 * (attempt + 1)  # 30초, 60초, 90초
            print(f"⏳ Groq 속도 제한 (429). {wait}초 대기 후 재시도... ({attempt+1}/3)")
            time.sleep(wait)
        else:
            raise Exception(f"Groq LLM 오류 ({response.status_code}): {response.text}")
    raise Exception(f"Groq LLM 재시도 초과 (429 에러 지속)")


def clean_transcript(raw_transcript):
    """
    Whisper 원본 전사를 Groq Llama로 보정: 오인식 수정 + 화자 분리.
    학생의 문법 오류는 일부러 유지 (피드백에서 교정하므로).
    보정 실패 시 → 원본 그대로 사용 (안전장치).

    ※ v2.1 업데이트: 화자 식별 규칙 강화 (Tutor/Student 뒤바뀜 방지)
    """
    print("🔍 전사 내용 보정 중...")

    # Groq Llama에게 보내는 "교정 의뢰서"
    prompt = f"""아래는 한국인 학습자와 원어민 튜터 간의 전화영어 수업을 STT(음성→텍스트)로 전사한 원본입니다.
전화 통화 특성상 음질이 완벽하지 않아 오인식이 포함되어 있을 수 있습니다.

다음 작업을 수행해주세요:

1. **전사 오류 보정**: 문맥상 맞지 않는 단어를 올바른 단어로 수정
   - 한국인 발음 특성 고려 (r/l, p/f, v/b 혼동 등)
   - 소음으로 인한 잡음 텍스트 제거
   
2. **화자 분리**: 각 발화 앞에 화자를 표시
   - [Tutor]: 원어민 튜터의 발화
   - [Student]: 한국인 학습자의 발화
   
   ⚠️ 화자 식별 핵심 규칙 (반드시 준수):
   - **[Student]는 한국인 학습자**입니다. 다음 특징으로 식별하세요:
     • 문법 오류가 있음 (예: "nearby park" → "a nearby park", "took a bicycle" → "rode a bicycle")
     • 한국 관련 이야기를 함 (부산, 서울, 한국의 날씨, 회사 등)
     • 영어가 비교적 짧고 단순한 문장 구조
     • 더듬거림, "hmm", "ah" 등 망설임이 많음
     • "teacher"라고 상대방을 부르는 쪽이 학습자
   - **[Tutor]는 원어민 튜터**입니다. 다음 특징으로 식별하세요:
     • 유창하고 자연스러운 영어 사용
     • 학습자에게 질문을 던지는 역할 (대화를 이끄는 사람)
     • 학습자의 이름을 부르는 쪽이 튜터
     • 교정, 되묻기, 리액션("That sounds nice!", "Oh really?") 등
   - **대화 흐름 규칙**: 질문한 사람과 대답한 사람은 반드시 다른 화자여야 합니다
   - 학습자의 문법 오류는 그대로 유지 (나중에 피드백에서 교정하므로)

3. **포맷**: 화자가 바뀔 때마다 줄바꿈

원본 전사:
{raw_transcript}

보정된 전사 결과만 출력해주세요. 추가 설명은 필요 없습니다."""

    try:
        cleaned = groq_llm_request(prompt, max_tokens=4096, temperature=0.3)
        print(f"✅ 전사 보정 완료: {len(cleaned)}자")
        return cleaned
    except Exception as e:
        print(f"⚠️ 전사 보정 실패 ({e}), 원본 사용")
        return raw_transcript


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  [4단계] 🤖 AI 피드백 생성 (Groq Llama - 메인 분석)                   ║
# ║  비유: 영어 과외 선생님에게 수업 녹취록 보여주며 성적표 부탁            ║
# ║                                                                        ║
# ║  🔧 이 단계가 가장 중요! 아래 prompt를 수정하면 피드백 내용이 바뀜      ║
# ║     예: "비즈니스 영어 특화" / "TOEIC Speaking 기준" 등                 ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def generate_feedback(transcript):
    """
    수업 전사 내용 → 상세 학습 피드백 생성.
    포함 항목: 수업 요약, 문법 교정, 반복 실수 패턴, 핵심 표현,
              잘한 점, 개선 포인트, 영작 연습, 유창성 점수(4항목)
    """
    print("🤖 AI 피드백 생성 중...")

    # ── 피드백 의뢰서 (이 부분을 수정하면 피드백 스타일이 바뀝니다) ──
    prompt = f"""[역할 설정]
당신은 한국인 성인 학습자를 위한 '따뜻하고 실용적인 영어 코치'입니다.
학습자의 **유창성(Fluency)**과 **정확성(Accuracy)**을 동시에 잡아주되,
너무 어려운 표현보다는 '입에 붙는 자연스러운 표현'을 우선합니다.
학습자는 비즈니스 환경(감사, 에너지 수입 등)에서 일하며 투자와 자기계발에 관심이 많은 중급(Intermediate) 수준의 전문가입니다.

[분석 지침]
아래 [전화영어 전사 내용]을 바탕으로, 다음 6가지 섹션의 피드백을 한국어로 작성해 주세요. (영어 예문은 영어로 유지)

**1. 📊 오늘의 대화 요약 (Summary)**
- 오늘 대화에서 다룬 핵심 주제를 아주 쉽고 짧게 2~3줄로 정리해 주세요.

**2. 💬 유창성 업그레이드 (Fluency & Natural Flow)**
학습자가 말한 문장 중 의미는 통하지만 더 자연스럽게 다듬을 수 있는 표현 3개를 선정하세요.
각 항목마다 3단계로 보여주세요:
- ❌ 학습자 원문 (As Said): 학습자가 실제 말한 문장
- ✅ 쉬운 자연스러운 표현 (Simple & Natural): 중학생도 아는 단어로 구성된, 원어민이 일상에서 쓰는 명확한 표현
- 💎 세련된 비즈니스 표현 (Professional): 격식 있는 자리에서 신뢰감을 주는 고급 표현
- 💡 코칭 포인트: 왜 이 표현이 더 유창하게 들리는지 뉘앙스 차이를 짧고 명확하게 설명

**3. 🔧 고질적 문법 '한 놈만 패기' (Target Grammar)**
이번 대화에서 가장 자주 반복된 문법 실수 또는 습관 **딱 1가지**만 골라주세요.
- 단순 오타가 아닌, 학습자가 **의식적으로 교정해야 할 '습관'**에 집중
- 표 형식으로 ❌ 습관적 표현 / ✅ 교정 예시를 3개 이상 정리
- 📌 핵심 규칙을 한 줄로 명확하게 정리
- 🔁 따라 읽기: 교정된 문장 3개를 소리 내어 읽을 수 있도록 별도로 정리
  (예: 🗣️ "The company doesn't allow employees to start a side business.")

**4. 📗 어휘 확장 (Vocabulary Vault)**
수업 중 튜터가 사용했거나, 맥락상 꼭 알아두면 유용한 단어 5개를 정리해 주세요.
각 단어마다:
- **단어** /발음기호/ (품사)
- 뜻: 한국어 의미
- 실전 예문: 학습자의 업무 환경(감사, LNG, 투자 등)에서 바로 쓸 수 있는 짧은 예문 1개

**5. 📝 실전 복습 챌린지 (Practice)**
오늘 교정된 표현과 문법을 활용한 영작 문제 3개를 내고, 모범 답안도 함께 제시해 주세요.
- 쉬운 문제 → 어려운 문제 순서로 배치

**6. ✨ 자신감 충전 & 내일의 미션 (Confidence & Mission)**
- ✨ **Good Job**: 오늘 수업에서 학습자가 가장 잘 표현한 문장, 또는 튜터가 긍정적으로 반응한 순간을 구체적으로 칭찬해 주세요. 어떤 점이 좋았는지 설명도 덧붙여 주세요.
- 🚀 **내일의 한 문장**: 다음 수업 시작할 때 튜터에게 바로 던질 수 있는 인사말이나 대화 시작 문장을 하나 만들어주세요. 오늘 배운 표현을 자연스럽게 활용하는 것이면 더 좋습니다.

**[성과 지표]**
마지막에 오늘의 **유창성 점수(10점 만점)**를 매기고 근거를 짧게 설명하세요.
그리고 다음 수업 때 유창성을 위해 의식적으로 시도해 볼 **'원포인트 액션 플랜'**을 제시하며 마무리하세요.

[전화영어 전사 내용]
{transcript}
"""

    feedback = groq_llm_request(
        prompt,
        max_tokens=8192,
        temperature=0.5,
        timeout=120,
        system_msg="You are a warm, practical, and encouraging English language coach for Korean adult learners."
    )
    print(f"✅ 피드백 생성 완료: {len(feedback)}자")
    return feedback


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  [5단계] 🌐 GitHub Pages 복습 페이지 생성                             ║
# ║  비유: 학습지를 인쇄해서 게시판에 붙이고,                              ║
# ║        "Gemini 선생님에게 질문하기" 버튼도 달아두는 것                  ║
# ║                                                                        ║
# ║  🔧 복습 방식 변경: review_prompt 변수의 텍스트를 수정하세요            ║
# ║  🔧 디자인 변경: CSS 내의 색상 코드(#38bdf8 등)를 수정하세요           ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def generate_review_page(transcript, feedback, filename, duration, date_str):
    """복습용 HTML 웹페이지 생성. 버튼 클릭 → 프롬프트 복사 → Gemini 열기."""
    duration_min = int(duration // 60)
    duration_sec = int(duration % 60)

    # ── Gemini 복습 대화용 프롬프트 (버튼 클릭 시 클립보드에 복사되는 내용) ──
    # 🔧 복습 방식을 바꾸려면 이 부분을 수정하세요
    review_prompt = f"""너는 나의 영어 회화 복습 파트너야. 오늘 내 전화영어 수업 내용을 기반으로 대화하면서 복습을 도와줘.

[오늘 수업 전사 내용]
{transcript}

[AI 피드백]
{feedback}

위 내용을 바탕으로:
1. 먼저 오늘 수업에서 내가 틀렸거나 어색했던 표현을 하나 골라서, 관련된 상황을 영어로 질문해줘.
2. 내가 영어로 대답하면, 자연스러운지 확인하고 더 나은 표현이 있으면 알려줘.
3. 특히 "반복 실수 패턴"에서 지적된 부분을 집중적으로 연습시켜줘.
4. 이런 식으로 오늘 배운 표현들을 하나씩 복습하자.
5. 한국어 설명은 필요할 때만 간단히, 대화는 최대한 영어로 진행해줘.

그럼 시작하자!"""

    prompt_escaped = json.dumps(review_prompt, ensure_ascii=False)
    feedback_html = _markdown_to_html(feedback)
    transcript_escaped = html_module.escape(transcript)
    filename_escaped = html_module.escape(filename)

    # HTML 페이지 전체 코드 (CSS 디자인 + JavaScript 버튼 동작 포함)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>전화영어 복습 - {date_str}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        *{{margin:0;padding:0;box-sizing:border-box}}
        body{{font-family:'Noto Sans KR',sans-serif;background:#0f0f13;color:#e4e4e7;line-height:1.75;min-height:100vh}}
        .header{{background:linear-gradient(135deg,#1a1a2e,#16213e,#0f3460);border-bottom:1px solid rgba(255,255,255,.06);padding:48px 24px 40px;text-align:center}}
        .header-date{{font-size:13px;color:#94a3b8;letter-spacing:3px;text-transform:uppercase;margin-bottom:12px}}
        .header h1{{font-size:28px;font-weight:700;color:#f1f5f9;margin-bottom:16px}}
        .header-meta{{display:flex;justify-content:center;gap:24px;font-size:14px;color:#64748b}}
        .header-meta span{{display:flex;align-items:center;gap:6px}}
        .cta-section{{text-align:center;padding:40px 24px}}
        .cta-btn{{display:inline-flex;align-items:center;gap:10px;padding:16px 36px;background:linear-gradient(135deg,#38bdf8,#818cf8);color:#fff;font-size:16px;font-weight:600;font-family:'Noto Sans KR',sans-serif;border:none;border-radius:50px;cursor:pointer;transition:all .3s;text-decoration:none;box-shadow:0 4px 24px rgba(56,189,248,.25)}}
        .cta-btn:hover{{transform:translateY(-2px);box-shadow:0 8px 32px rgba(56,189,248,.35)}}
        .cta-btn svg{{width:20px;height:20px}}
        .cta-sub{{margin-top:12px;font-size:13px;color:#64748b}}
        .toast{{position:fixed;bottom:32px;left:50%;transform:translateX(-50%) translateY(80px);background:#1e293b;color:#38bdf8;padding:14px 28px;border-radius:12px;font-size:14px;font-weight:500;border:1px solid rgba(56,189,248,.2);box-shadow:0 8px 32px rgba(0,0,0,.4);opacity:0;transition:all .4s cubic-bezier(.16,1,.3,1);z-index:1000}}
        .toast.show{{opacity:1;transform:translateX(-50%) translateY(0)}}
        .container{{max-width:720px;margin:0 auto;padding:0 24px 80px}}
        .tabs{{display:flex;gap:4px;background:#1a1a24;padding:4px;border-radius:12px;margin-bottom:32px}}
        .tab{{flex:1;padding:12px;text-align:center;font-size:14px;font-weight:500;color:#64748b;background:0 0;border:none;border-radius:8px;cursor:pointer;font-family:'Noto Sans KR',sans-serif;transition:all .2s}}
        .tab.active{{background:#262636;color:#f1f5f9}}
        .tab-content{{display:none}}.tab-content.active{{display:block}}
        .feedback h2{{font-size:18px;font-weight:700;color:#f1f5f9;margin:36px 0 16px;padding-bottom:10px;border-bottom:1px solid rgba(255,255,255,.06)}}
        .feedback h2:first-child{{margin-top:0}}
        .feedback p{{margin:8px 0;color:#cbd5e1}}
        .feedback .item{{padding:6px 0 6px 16px;border-left:2px solid #334155;margin:6px 0;color:#cbd5e1}}
        .feedback .numbered{{padding:8px 0 8px 16px;color:#cbd5e1}}
        .feedback .numbered strong{{color:#38bdf8}}
        .feedback strong{{color:#f1f5f9}}
        .feedback code{{background:#1e293b;padding:2px 8px;border-radius:4px;font-family:'JetBrains Mono',monospace;font-size:13px;color:#38bdf8}}
        .feedback table{{width:100%;border-collapse:collapse;margin:12px 0}}
        .feedback th,.feedback td{{padding:10px 14px;text-align:left;border-bottom:1px solid #262636}}
        .feedback th{{color:#94a3b8;font-weight:500;font-size:13px}}
        .feedback td{{color:#cbd5e1}}
        .arrow{{color:#38bdf8;font-weight:700}}
        .transcript{{background:#1a1a24;border-radius:12px;padding:28px;font-size:14px;line-height:2;color:#94a3b8;white-space:pre-wrap;word-break:break-word;font-family:'JetBrains Mono','Noto Sans KR',monospace}}
        .transcript .tutor{{color:#38bdf8}}
        .transcript .student{{color:#a78bfa}}
        @media(max-width:640px){{.header{{padding:32px 16px}}.header h1{{font-size:22px}}.cta-btn{{padding:14px 28px;font-size:15px}}.container{{padding:0 16px 60px}}}}
    </style>
</head>
<body>
    <div class="header">
        <div class="header-date">{date_str}</div>
        <h1>📚 전화영어 복습</h1>
        <div class="header-meta">
            <span>⏱ {duration_min}분 {duration_sec}초</span>
            <span>🎙 {filename_escaped}</span>
        </div>
    </div>
    <div class="cta-section">
        <button class="cta-btn" onclick="startReview()">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            Gemini에서 복습 대화 시작하기
        </button>
        <div class="cta-sub">클릭하면 프롬프트가 복사되고 Gemini가 열립니다</div>
    </div>
    <div class="container">
        <div class="tabs">
            <button class="tab active" onclick="switchTab('feedback')">📋 AI 피드백</button>
            <button class="tab" onclick="switchTab('transcript')">🎙 수업 전사</button>
        </div>
        <div id="tab-feedback" class="tab-content active">
            <div class="feedback">{feedback_html}</div>
        </div>
        <div id="tab-transcript" class="tab-content">
            <div class="transcript">{_colorize_transcript(transcript_escaped)}</div>
        </div>
    </div>
    <div class="toast" id="toast">✅ 프롬프트가 복사되었습니다!</div>
    <script>
        const REVIEW_PROMPT={prompt_escaped};
        function startReview(){{navigator.clipboard.writeText(REVIEW_PROMPT).then(()=>{{showToast();setTimeout(()=>window.open('https://gemini.google.com/app','_blank'),600)}}).catch(()=>{{const t=document.createElement('textarea');t.value=REVIEW_PROMPT;document.body.appendChild(t);t.select();document.execCommand('copy');document.body.removeChild(t);showToast();setTimeout(()=>window.open('https://gemini.google.com/app','_blank'),600)}})}}
        function showToast(){{const t=document.getElementById('toast');t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2500)}}
        function switchTab(n){{document.querySelectorAll('.tab').forEach((t,i)=>t.classList.toggle('active',n==='feedback'?i===0:i===1));document.querySelectorAll('.tab-content').forEach(c=>c.classList.remove('active'));document.getElementById('tab-'+n).classList.add('active')}}
    </script>
</body>
</html>"""


def _colorize_transcript(escaped_transcript):
    """화자별 색상 적용: [Tutor] → 파란색, [Student] → 보라색"""
    result = escaped_transcript
    result = result.replace("[Tutor]", '<span class="tutor">[Tutor]</span>')
    result = result.replace("[Student]", '<span class="student">[Student]</span>')
    return result


def deploy_review_page(page_html, date_str):
    """
    HTML을 docs/ 폴더에 저장 → 인덱스 갱신 → git push → GitHub Pages에 자동 배포.
    비유: 학습지를 인쇄 → 게시판 목차 갱신 → 게시판에 핀으로 꽂기.
    """
    print("🌐 복습 페이지 배포 중...")
    docs_dir = "docs"
    os.makedirs(docs_dir, exist_ok=True)

    slug = datetime.now(KST).strftime("%Y-%m-%d")
    filename = f"{slug}.html"
    filepath = os.path.join(docs_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(page_html)

    _update_index_page(docs_dir)

    # Git으로 GitHub에 업로드 (변경 기록 → 업로드)
    subprocess.run(["git", "config", "user.name", "github-actions"], check=True)
    subprocess.run(["git", "config", "user.email", "actions@github.com"], check=True)
    subprocess.run(["git", "add", "docs/"], check=True)
    subprocess.run(["git", "commit", "-m", f"📚 Add review page: {date_str}"], check=True)
    subprocess.run(["git", "push"], check=True)

    page_url = f"{GITHUB_PAGES_URL}/{filename}" if GITHUB_PAGES_URL else filename
    print(f"✅ 배포 완료: {page_url}")
    return page_url


def _update_index_page(docs_dir):
    """복습 기록 전체 목록(index.html)을 최신순으로 갱신."""
    pages = sorted(glob.glob(os.path.join(docs_dir, "2*.html")), reverse=True)
    links_html = ""
    for p in pages:
        name = os.path.basename(p).replace(".html", "")
        links_html += f'        <a href="{os.path.basename(p)}" class="link">{name}</a>\n'

    index = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>전화영어 복습 기록</title>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        *{{margin:0;padding:0;box-sizing:border-box}}
        body{{font-family:'Noto Sans KR',sans-serif;background:#0f0f13;color:#e4e4e7;min-height:100vh;padding:48px 24px}}
        h1{{text-align:center;font-size:28px;margin-bottom:40px;color:#f1f5f9}}
        .list{{max-width:480px;margin:0 auto;display:flex;flex-direction:column;gap:8px}}
        .link{{display:block;padding:16px 20px;background:#1a1a24;border-radius:10px;color:#cbd5e1;text-decoration:none;font-size:15px;transition:all .2s;border:1px solid transparent}}
        .link:hover{{background:#262636;border-color:rgba(56,189,248,.2);color:#38bdf8}}
    </style>
</head>
<body>
    <h1>📚 전화영어 복습 기록</h1>
    <div class="list">
{links_html if links_html else '        <p style="text-align:center;color:#64748b">아직 복습 기록이 없습니다.</p>'}
    </div>
</body>
</html>"""
    with open(os.path.join(docs_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(index)


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  [6단계] 📧 이메일 발송 (Gmail SMTP)                                  ║
# ║  비유: 성적표를 봉투에 넣고 우체통(Gmail)에 넣는 것                    ║
# ║  이메일에는 텍스트 버전 + HTML(예쁜) 버전 두 가지가 포함됨             ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def _markdown_to_html(md_text):
    """마크다운(## 제목, - 목록 등) → HTML 변환 도우미."""
    lines = md_text.split("\n")
    html_lines = []
    in_table = False

    for line in lines:
        if re.match(r"^\|[-\s|]+\|$", line):
            continue
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not in_table:
                html_lines.append("<table>")
                tag = "th"
                in_table = True
            else:
                tag = "td"
            row = "".join(f"<{tag}>{c}</{tag}>" for c in cells)
            html_lines.append(f"<tr>{row}</tr>")
            continue
        elif in_table:
            html_lines.append("</table>")
            in_table = False

        if line.startswith("## "):
            html_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            html_lines.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("- "):
            html_lines.append(f'<div class="item">{line[2:]}</div>')
        elif re.match(r"^\d+\.\s", line):
            content = re.sub(r"^\d+\.\s", "", line)
            num = re.match(r"^(\d+)\.", line).group(1)
            html_lines.append(f'<div class="numbered"><strong>{num}.</strong> {content}</div>')
        elif line.startswith("---"):
            continue
        elif line.strip() == "":
            html_lines.append("<br>")
        else:
            html_lines.append(f"<p>{line}</p>")

    if in_table:
        html_lines.append("</table>")

    result = "\n".join(html_lines)
    result = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", result)
    result = re.sub(r"`(.+?)`", r"<code>\1</code>", result)
    result = result.replace("→", '<span class="arrow">→</span>')
    return result


def send_email(feedback, filename, duration, review_url):
    """Gmail SMTP로 피드백 이메일 발송. 텍스트+HTML 두 버전 포함."""
    print(f"📧 이메일 발송 중... → {RECIPIENT_EMAIL}")

    today = datetime.now(KST).strftime("%Y년 %m월 %d일")
    duration_min = int(duration // 60)
    duration_sec = int(duration % 60)

    # 이메일 봉투 만들기
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📚 전화영어 피드백 - {today}"
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = RECIPIENT_EMAIL

    # 텍스트 버전 (HTML 미지원 환경용)
    text_body = f"""전화영어 피드백 - {today}
수업 길이: {duration_min}분 {duration_sec}초

{'='*50}

{feedback}

{'='*50}

🔗 Gemini로 복습 대화하기: {review_url}

이 메일은 자동 생성되었습니다.
"""

    # HTML 버전 (인라인 스타일 필수 - 이메일은 CSS 파일을 쓸 수 없음)
    feedback_lines = feedback.split("\n")
    email_feedback = ""
    in_table = False

    for line in feedback_lines:
        if re.match(r"^\|[-\s|]+\|$", line):
            continue
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not in_table:
                email_feedback += '<table style="width:100%;border-collapse:collapse;margin:12px 0">'
                tag = "th"
                style = "padding:8px 12px;text-align:left;border-bottom:2px solid #e2e8f0;color:#64748b;font-size:13px"
                in_table = True
            else:
                tag = "td"
                style = "padding:8px 12px;text-align:left;border-bottom:1px solid #f1f5f9;color:#475569"
            row = "".join(f'<{tag} style="{style}">{c}</{tag}>' for c in cells)
            email_feedback += f"<tr>{row}</tr>"
            continue
        elif in_table:
            email_feedback += "</table>"
            in_table = False

        if line.startswith("## "):
            email_feedback += f'<h2 style="color:#1e293b;border-bottom:2px solid #e2e8f0;padding-bottom:8px;margin-top:28px;font-size:17px">{line[3:]}</h2>'
        elif line.startswith("- "):
            email_feedback += f'<div style="padding:4px 0 4px 16px;border-left:3px solid #38bdf8;margin:6px 0;color:#475569">{line[2:]}</div>'
        elif re.match(r"^\d+\.\s", line):
            content = re.sub(r"^\d+\.\s", "", line)
            num = re.match(r"^(\d+)\.", line).group(1)
            email_feedback += f'<div style="padding:6px 0 6px 16px;color:#475569"><strong style="color:#38bdf8">{num}.</strong> {content}</div>'
        elif line.startswith("---"):
            continue
        elif line.strip() == "":
            email_feedback += "<br>"
        else:
            email_feedback += f'<p style="margin:6px 0;color:#475569">{line}</p>'

    if in_table:
        email_feedback += "</table>"

    email_feedback = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", email_feedback)
    email_feedback = email_feedback.replace("→", '<span style="color:#38bdf8;font-weight:700">→</span>')

    html_body = f"""<html>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;max-width:700px;margin:0 auto;padding:20px;color:#333;background:#f8fafc">
  <div style="background:linear-gradient(135deg,#1e293b,#0f3460);padding:28px;border-radius:16px;color:#fff;margin-bottom:20px">
    <h1 style="margin:0;font-size:22px">📚 전화영어 피드백</h1>
    <p style="margin:8px 0 0;opacity:.8;font-size:14px">{today} · {duration_min}분 {duration_sec}초</p>
  </div>
  <div style="text-align:center;margin:24px 0">
    <a href="{review_url}" style="display:inline-block;padding:14px 32px;background:linear-gradient(135deg,#38bdf8,#818cf8);color:#fff;text-decoration:none;border-radius:50px;font-size:15px;font-weight:600;box-shadow:0 4px 16px rgba(56,189,248,.3)">💬 Gemini에서 복습 대화 시작하기</a>
    <p style="margin-top:8px;font-size:12px;color:#94a3b8">클릭 → 프롬프트 복사 → Gemini에 붙여넣기</p>
  </div>
  <div style="background:#fff;padding:28px;border-radius:12px;border:1px solid #e2e8f0;line-height:1.8">
    {email_feedback}
  </div>
  <hr style="border:none;border-top:1px solid #e2e8f0;margin:32px 0 16px">
  <p style="color:#94a3b8;font-size:12px;text-align:center">이 메일은 GitHub Actions에 의해 자동 생성되었습니다.</p>
</body>
</html>"""

    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Gmail SMTP 서버를 통해 발송 (465 = 보안 포트)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.send_message(msg)

    print("✅ 이메일 발송 완료!")


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║                    🎬 메인 함수 (총감독)                                ║
# ║  위의 모든 단계를 순서대로 실행합니다.                                  ║
# ║  에러 처리: 파일 없음→조용히 종료(exit 0) / API 오류→빨간X(exit 1)     ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def main():
    print("=" * 50)
    print("🚀 전화영어 피드백 자동화 v2 시작")
    now = datetime.now(KST)
    print(f"📅 {now.strftime('%Y-%m-%d %H:%M KST')}")
    print("=" * 50)

    # ━━ [1단계] Google Drive에서 녹음 파일 다운로드 ━━
    service = get_drive_service()
    audio_path, filename, file_id = download_latest_recording(service)

    # 파일 없으면 조용히 종료 (exit 0 = 에러 아님 = 초록 체크마크)
    if not audio_path:
        print("ℹ️ 오늘 녹음 파일이 없습니다. 수업이 없는 날이거나 동기화 지연일 수 있습니다.")
        sys.exit(0)

    date_str = now.strftime("%Y년 %m월 %d일")

    try:
        # ━━ [2단계] 음성 → 텍스트 (Groq Whisper) ━━
        transcript_raw, duration = transcribe_audio(audio_path)
        if not transcript_raw.strip():
            print("❌ 전사 결과가 비어있습니다.")
            sys.exit(0)
        print(f"\n📝 원본 전사 (첫 200자):\n{transcript_raw[:200]}...\n")

        # ━━ [3단계] 전사 보정 (화자 분리 + 오인식 수정) ━━
        transcript = clean_transcript(transcript_raw)

        # ━━ [4단계] AI 피드백 생성 ━━
        feedback = generate_feedback(transcript)

        # ━━ [5단계] 복습 페이지 생성 & 배포 ━━
        page_html = generate_review_page(transcript, feedback, filename, duration, date_str)
        review_url = deploy_review_page(page_html, date_str)

        # ━━ [6단계] 이메일 발송 ━━
        send_email(feedback, filename, duration, review_url)

        # ━━ [7단계] 완료 파일 이동 ━━
        move_to_done_folder(file_id)

        print("\n" + "=" * 50)
        print("✅ 모든 과정이 완료되었습니다!")
        print(f"🌐 복습 페이지: {review_url}")
        print("=" * 50)

    finally:
        # 임시 녹음 파일 삭제 (에러가 나도 반드시 실행)
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)


# ┌─────────────────────────────────────────────────────────────────────────┐
# │  🏁 프로그램 시작점                                                     │
# │  Python이 이 파일을 직접 실행하면 main() 함수(총감독)가 일을 시작합니다. │
# └─────────────────────────────────────────────────────────────────────────┘
if __name__ == "__main__":
    main()
