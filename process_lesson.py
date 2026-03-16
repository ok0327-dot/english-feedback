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
║  [3단계] 🔍 받아쓰기 내용을 교정 (Gemini - 전처리)                         ║
║          → 비유: 교정 선생님이 속기사의 받아쓰기 오타를 잡고,               ║
║                  "이건 선생님 말, 이건 학생 말"로 구분해주는 것              ║
║                                                                            ║
║  [4단계] 🤖 교정된 내용으로 학습 피드백 생성 (Gemini - 피드백)              ║
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
║  [8단계] 📋 처리 완료 기록 저장 (GitHub에 기록)                            ║
║          → 비유: 택배 수령 대장에 "처리 완료" 도장 찍는 것                  ║
║          → 다음 실행 시 이 기록을 확인하여 중복 처리를 방지합니다.          ║
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

# Google Gemini API의 "출입증" (텍스트 보정 + 피드백 생성에 사용, 미설정 시 Groq로 대체)
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


def extract_lesson_date(filename):
    """
    녹음 파일명에서 실제 수업 날짜를 추출하는 함수.
    예: "전화영어_025180304_20260304080041.m4a" → datetime(2026, 3, 4)
    파일명에서 YYYYMMDD 패턴(20XX로 시작하는 8자리)을 찾아 수업 날짜로 사용.
    파싱 실패 시 None 반환 → 호출부에서 현재 시간으로 대체.
    """
    match = re.search(r'(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])', filename)
    if match:
        try:
            lesson_date = datetime(
                int(match.group(1)), int(match.group(2)), int(match.group(3)),
                tzinfo=KST
            )
            print(f"📅 파일명에서 수업 날짜 추출: {lesson_date.strftime('%Y-%m-%d')}")
            return lesson_date
        except ValueError:
            pass
    print(f"⚠️ 파일명에서 날짜를 추출할 수 없어 현재 날짜를 사용합니다: {filename}")
    return None


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


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  📋 처리 완료 기록 (중복 처리 방지 — 멱등성 보장)                      ║
# ║  비유: 택배 수령 대장에 "이 택배는 이미 처리함" 도장 찍는 것            ║
# ║                                                                        ║
# ║  왜 필요?                                                               ║
# ║  - FolderSync가 같은 파일을 새 ID로 재업로드해도 중복 방지              ║
# ║  - '완료' 폴더 이동이 실패해도 중복 방지                                ║
# ║                                                                        ║
# ║  작동 원리:                                                             ║
# ║  docs/processed.txt에 "파일ID|파일명" 형태로 한 줄씩 기록.              ║
# ║  다음 실행 시 파일 ID와 파일명 모두 확인 → 둘 중 하나만 일치해도 건너뜀.║
# ║  이 파일은 git push로 GitHub에 저장되므로 다음 실행에서도 유지됨.       ║
# ╚══════════════════════════════════════════════════════════════════════════╝

PROCESSED_FILE = "docs/processed.txt"


def load_processed_records():
    """
    처리 완료 기록을 읽어옴. (file_ids 세트, filenames 세트) 튜플 반환.
    기존 형식(ID만)과 새 형식(ID|파일명) 모두 호환.
    """
    ids = set()
    names = set()
    if not os.path.exists(PROCESSED_FILE):
        return ids, names
    with open(PROCESSED_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if "|" in line:
                file_id, filename = line.split("|", 1)
                ids.add(file_id.strip())
                names.add(filename.strip())
            else:
                ids.add(line)
    return ids, names


def save_processed_id(file_id, filename=""):
    """처리 완료된 파일 ID와 파일명을 기록에 추가."""
    os.makedirs(os.path.dirname(PROCESSED_FILE), exist_ok=True)
    with open(PROCESSED_FILE, "a") as f:
        f.write(f"{file_id}|{filename}\n")
    print(f"📋 처리 완료 기록 추가: {file_id} ({filename})")


def is_already_processed(file_id, filename=""):
    """
    이 파일이 이미 처리되었는지 확인.
    파일 ID 또는 파일명 중 하나라도 일치하면 중복으로 판단.
    → FolderSync가 같은 파일을 새 ID로 재업로드해도 파일명으로 잡아냄.
    """
    processed_ids, processed_names = load_processed_records()
    if file_id in processed_ids:
        print(f"ℹ️ 이미 처리된 파일입니다 (ID: {file_id[:20]}...). 건너뜁니다.")
        return True
    if filename and filename in processed_names:
        print(f"ℹ️ 이미 처리된 파일명입니다 ({filename}). 건너뜁니다.")
        return True
    return False


def commit_processed_record():
    """처리 기록(processed.txt)을 GitHub에 저장. 복습 페이지 배포와 별도로 실행."""
    try:
        subprocess.run(["git", "config", "user.name", "github-actions"], check=True)
        subprocess.run(["git", "config", "user.email", "actions@github.com"], check=True)
        subprocess.run(["git", "add", PROCESSED_FILE], check=True)
        # 변경사항이 없으면 commit이 실패하므로, 실패해도 무시
        result = subprocess.run(
            ["git", "commit", "-m", "📋 Update processed records"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            subprocess.run(["git", "push"], check=True)
            print("✅ 처리 기록 저장 완료")
        else:
            print("ℹ️ 처리 기록 변경 없음 (이미 최신)")
    except Exception as e:
        print(f"⚠️ 처리 기록 저장 실패 (치명적이지 않음): {e}")


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
    세그먼트별 타임스탬프를 함께 반환하여 화자 분리 정확도를 높임.
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
                "response_format": "verbose_json",  # 상세 결과 (세그먼트 타임스탬프 포함)
                # verbose_json 기본값이 segment이므로 별도 지정 불필요
            },
            timeout=120,  # 최대 2분 대기
        )
    if response.status_code != 200:
        raise Exception(f"Groq API 오류 ({response.status_code}): {response.text}")

    result = response.json()
    transcript = result.get("text", "")
    duration = result.get("duration", 0)
    segments = result.get("segments", [])
    print(f"✅ 전사 완료: {len(transcript)}자, {duration:.0f}초, {len(segments)}개 세그먼트")
    return transcript, duration, segments


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  [3단계] 🔍 전사 내용 보정 (Gemini - 전처리)                          ║
# ║  비유: 교정 선생님이 속기사의 오타를 잡고 화자를 구분해주는 것          ║
# ║  왜 필요? 전화 음질 한계 + 한국인 발음 특성 → 오인식 발생              ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def gemini_request(prompt, max_tokens=4096, temperature=0.3, timeout=120, system_msg=None, thinking_budget=2048):
    """
    Google Gemini API 호출 (Gemini 2.5 Flash 모델 사용).
    전사 보정 및 피드백 생성에 사용.
    429 에러 시 자동 재시도 (최대 3회).
    thinking_budget: 추론에 사용할 최대 토큰 수 (maxOutputTokens에 포함됨)
    """
    if not GEMINI_API_KEY:
        raise Exception("GEMINI_API_KEY 미설정")

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json",
    }

    # 요청 페이로드 구성
    # Gemini 2.5 Flash는 thinking 모델이라 추론 토큰도 maxOutputTokens에 포함됨
    # → 추론 토큰을 제한하여 실제 출력에 충분한 토큰을 확보
    payload = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
            "thinkingConfig": {"thinkingBudget": thinking_budget},
        },
    }

    # system_msg가 있으면 systemInstruction 추가
    if system_msg:
        payload["system_instruction"] = {
            "parts": [{"text": system_msg}]
        }

    for attempt in range(3):
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        if response.status_code == 200:
            result = response.json()
            candidates = result.get("candidates", [])
            if not candidates:
                block_reason = result.get("promptFeedback", {}).get("blockReason", "알 수 없음")
                raise Exception(f"Gemini 응답 없음 (차단 사유: {block_reason})")
            if candidates[0].get("finishReason") == "SAFETY":
                raise Exception("Gemini 안전 필터에 의해 응답 차단됨")
            if candidates[0].get("finishReason") == "MAX_TOKENS":
                print("⚠️ Gemini 출력이 토큰 한도에 도달하여 잘렸을 수 있습니다.")
            return candidates[0]["content"]["parts"][0]["text"]
        elif response.status_code == 429:
            wait = 30 * (attempt + 1)  # 30초, 60초, 90초
            print(f"⏳ Gemini 속도 제한 (429). {wait}초 대기 후 재시도... ({attempt+1}/3)")
            time.sleep(wait)
        else:
            raise Exception(f"Gemini API 오류 ({response.status_code}): {response.text}")
    raise Exception(f"Gemini API 재시도 초과 (429 에러 지속)")


def groq_llm_request(prompt, max_tokens=4096, temperature=0.3, timeout=120, system_msg=None):
    """
    Groq LLM API 호출 (Llama 3.3 70B 모델 사용).
    Gemini 실패 시 백업용으로 사용.
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
            wait = 30 * (attempt + 1)
            print(f"⏳ Groq 속도 제한 (429). {wait}초 대기 후 재시도... ({attempt+1}/3)")
            time.sleep(wait)
        else:
            raise Exception(f"Groq LLM 오류 ({response.status_code}): {response.text}")
    raise Exception(f"Groq LLM 재시도 초과 (429 에러 지속)")


def llm_request(prompt, max_tokens=4096, temperature=0.3, timeout=120, system_msg=None, thinking_budget=2048):
    """
    LLM 호출 (Gemini 우선, 실패 시 Groq로 자동 전환).
    무료 한도 초과, 네트워크 오류 등 Gemini 장애 시에도 파이프라인이 중단되지 않음.
    thinking_budget: Gemini 추론 토큰 한도 (Groq fallback 시에는 미사용)
    """
    try:
        result = gemini_request(prompt, max_tokens, temperature, timeout, system_msg, thinking_budget)
        print("  (🟢 Gemini)")
        return result
    except Exception as e:
        print(f"⚠️ Gemini 실패 ({e}), Groq로 대체 실행...")
        result = groq_llm_request(prompt, max_tokens, temperature, timeout, system_msg)
        print("  (🟡 Groq fallback)")
        return result


def _format_segments_with_gaps(segments):
    """
    Whisper 세그먼트를 타임스탬프 + 침묵 구간 표시 형식으로 변환.
    침묵(gap)이 1.5초 이상이면 화자 전환 가능성이 높으므로 표시해줌.
    비유: 대화 녹취에 "여기서 잠깐 멈춤" 메모를 달아주는 것.
    """
    if not segments:
        return ""

    lines = []
    for i, seg in enumerate(segments):
        start = seg.get("start", 0)
        end = seg.get("end", 0)
        text = seg.get("text", "").strip()
        if not text:
            continue

        # 이전 세그먼트와의 침묵 구간 계산
        if i > 0:
            prev_end = segments[i - 1].get("end", 0)
            gap = start - prev_end
            if gap >= 1.5:
                lines.append(f"  --- ({gap:.1f}초 침묵 — 화자 전환 가능성 높음) ---")

        lines.append(f"[{start:.1f}s ~ {end:.1f}s] {text}")

    return "\n".join(lines)


def clean_transcript(raw_transcript, segments=None):
    """
    Whisper 원본 전사를 Gemini로 보정: 오인식 수정 + 화자 분리.
    학생의 문법 오류는 일부러 유지 (피드백에서 교정하므로).
    보정 실패 시 → 원본 그대로 사용 (안전장치).

    ※ v2.2 업데이트: 세그먼트 타임스탬프 기반 화자 분리 강화
      - 침묵 구간(gap)을 화자 전환 단서로 활용
      - LLM이 텍스트 내용 + 시간 정보를 함께 분석
    """
    print("🔍 전사 내용 보정 중...")

    # 세그먼트 타임스탬프 정보를 텍스트로 변환
    segments_text = _format_segments_with_gaps(segments) if segments else ""

    # Gemini에게 보내는 "교정 의뢰서"
    prompt = f"""아래는 한국인 학습자와 원어민 튜터 간의 전화영어 수업을 STT(음성→텍스트)로 전사한 원본입니다.
전화 통화 특성상 음질이 완벽하지 않아 오인식이 포함되어 있을 수 있습니다.

다음 작업을 **반드시 아래 순서대로** 수행해주세요:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## STEP 1: 전체 대화 맥락 파악 (먼저 읽고 생각하기)

결과를 출력하기 전에, 전사 전체를 끝까지 읽고 다음을 파악하세요:
- **대화 주제**: 오늘 수업에서 무슨 이야기를 했는가? (여행, 주말, 업무, 취미 등)
- **대화 흐름**: 누가 질문하고 누가 대답하는 패턴인가?
- **영어 실력 차이**: 어떤 발화들이 문법적으로 완벽하고, 어떤 발화들에 실수가 있는가?
- **역할 구조**: 전화영어 수업은 "튜터가 질문 → 학생이 대답 → 튜터가 리액션/추가질문"의 패턴이 반복됨

이 맥락을 바탕으로 화자를 배정하세요. 개별 문장만 보지 말고 대화 전체 흐름을 고려하세요.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## STEP 2: 전사 오류 보정

- 문맥상 맞지 않는 단어를 올바른 단어로 수정
- 한국인 발음 특성 고려 (r/l, p/f, v/b, th/s 혼동 등)
- 소음으로 인한 잡음 텍스트 제거

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## STEP 3: 화자 분리

각 발화 앞에 [Tutor] 또는 [Student]를 표시하세요.

⚠️ **화자 식별 규칙 (우선순위 순)**:

🥇 **1순위 — 영어 실수 여부 (가장 강력한 단서)**:
   - **영문법 실수가 있는 쪽이 [Student]입니다** (이것이 가장 확실한 판별 기준!)
   - 관사 누락/오용 (a/an/the), 전치사 오류, 시제 불일치, 어색한 어순 등
   - 더듬거림, "hmm", "ah", "uh" 등 망설임이 많은 쪽
   - 문법적으로 완벽하고 유창한 쪽이 [Tutor]입니다

🥈 **2순위 — 대화 맥락과 역할**:
   - 질문을 던지며 대화를 이끄는 쪽 → [Tutor]
   - 질문에 대답하는 쪽 → [Student]
   - 리액션/칭찬("That sounds nice!", "Oh really?", "Good job!") → [Tutor]
   - 교정하거나 되묻는 쪽("You mean...?", "Did you say...?") → [Tutor]
   - 한국 관련 자기 이야기를 하는 쪽 → [Student]
   - "teacher"라고 부르는 쪽 → [Student], 이름을 부르는 쪽 → [Tutor]

🥉 **3순위 — 타임스탬프 기반 화자 전환**:
   - 세그먼트 사이 **1.5초 이상 침묵**이 있으면 화자가 바뀔 가능성이 높음
   - 전화 통화는 한 사람이 말하면 다른 사람이 듣는 구조
   - 짧은 침묵(0.5초 미만)은 같은 화자의 쉼

📌 **일관성 검증**:
   - 한번 [Student]로 판단한 화자의 영어 수준이 갑자기 유창해지면 화자를 잘못 배정한 것!
   - 질문한 사람과 대답한 사람은 반드시 다른 화자여야 함
   - 학습자의 문법 오류는 그대로 유지 (나중에 피드백에서 교정하므로)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
## 출력 포맷
- 화자가 바뀔 때마다 줄바꿈
- 타임스탬프는 최종 결과에 포함하지 마세요"""

    # 세그먼트 타임스탬프가 있으면 추가 (화자 분리의 핵심 단서)
    if segments_text:
        prompt += f"""

📊 세그먼트별 타임스탬프 (화자 분리 참고용):
{segments_text}

"""
    prompt += f"""
원본 전사:
{raw_transcript}

보정된 전사 결과만 출력해주세요. 추가 설명은 필요 없습니다."""

    try:
        cleaned = llm_request(prompt, max_tokens=8192, temperature=0.3, thinking_budget=2048)
        print(f"✅ 전사 보정 완료: {len(cleaned)}자")
        return cleaned
    except Exception as e:
        print(f"⚠️ 전사 보정 실패 ({e}), 원본 사용")
        return raw_transcript


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  [3.5단계] 🔍 화자 라벨 검증 (Gemini - 2차 검토)                      ║
# ║  비유: 교정 선생님이 화자 분리 결과를 다시 한번 점검하는 것             ║
# ║                                                                        ║
# ║  왜 필요?                                                               ║
# ║  - 1차 전사 보정에서 [Tutor]↔[Student] 라벨이 바뀌는 경우가 간헐 발생  ║
# ║  - 2차 검증으로 화자 일관성을 확보한 뒤 피드백을 생성해야 정확          ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def verify_speaker_labels(transcript):
    """
    화자 라벨 검증: [Tutor]↔[Student]가 뒤바뀐 구간을 찾아 교정.
    전사 보정(3단계) 결과를 입력받아, 화자만 재검토한 결과를 반환.
    """
    print("🔍 화자 라벨 검증 중...")

    prompt = f"""아래는 전화영어 수업의 전사 내용입니다. [Tutor]와 [Student] 라벨이 올바른지 검증해주세요.

## 검증 기준

1. **영어 실력 일관성**: [Student]로 표시된 발화가 갑자기 완벽한 문법으로 유창해지거나, [Tutor]로 표시된 발화에 문법 실수가 많으면 라벨이 바뀐 것
2. **대화 흐름**: 질문→대답 쌍에서 같은 화자가 질문과 대답을 모두 하고 있으면 오류
3. **역할 일관성**: [Tutor]는 수업을 이끌고 교정하는 역할, [Student]는 대답하고 연습하는 역할
4. **한국 관련 자기 이야기**: 한국 생활/업무를 자기 경험으로 말하는 쪽은 [Student]

## 작업

- 라벨이 올바르면 그대로 출력
- 라벨이 바뀐 구간이 있으면 교정하여 출력
- 전사 텍스트 자체는 수정하지 말고, [Tutor]/[Student] 라벨만 점검
- 추가 설명 없이 교정된 전사 결과만 출력

[전사 내용]
{transcript}"""

    try:
        verified = llm_request(prompt, max_tokens=8192, temperature=0.2, thinking_budget=2048)
        print(f"✅ 화자 검증 완료: {len(verified)}자")
        return verified
    except Exception as e:
        print(f"⚠️ 화자 검증 실패 ({e}), 원본 사용")
        return transcript


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  [4단계] 🤖 AI 피드백 생성 (Gemini - 메인 분석)                       ║
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
    # ※ 역할 설정은 system_msg에만 포함 (프롬프트와 중복 방지)
    system_msg = """당신은 한국인 성인 학습자를 위한 '따뜻하고 실용적인 영어 코치'입니다.
학습자의 유창성(Fluency)과 정확성(Accuracy)을 동시에 잡아주되,
너무 어려운 표현보다는 '입에 붙는 자연스러운 표현'을 우선합니다.
학습자는 비즈니스 환경(감사, 에너지 수입 등)에서 일하며 투자와 자기계발에 관심이 많은 중급(Intermediate) 수준의 전문가입니다.

⚠️ 중요 규칙:
- 전사 내용에 **실제로 있는 [Student] 발화만** 인용하세요. 없는 문장을 만들어내지 마세요.
- 각 섹션은 서로 다른 관점을 다뤄야 합니다. 같은 예문을 여러 섹션에서 반복하지 마세요.
- 표준 영어만 가르치세요. 비표준 표현(funner 등)은 포함하지 마세요."""

    prompt = f"""아래 [전화영어 전사 내용]을 분석하여 6가지 섹션의 피드백을 한국어로 작성해 주세요.
(영어 예문은 영어로 유지)

**1. 📊 오늘의 대화 요약 (Summary)**
- 오늘 **구체적으로** 무슨 주제를 다뤘는지 2~3줄로 정리 (예: "business travel의 장단점에 대해 읽고 토론", "주말 계획에 대해 자유 대화")
- "다양한 주제를 다뤘다" 같은 뻔한 요약은 금지

**2. 💬 유창성 업그레이드 (Fluency & Natural Flow)**
[Student]가 실제 말한 문장 중, 의미는 통하지만 더 자연스럽게 다듬을 수 있는 표현 **3개**를 선정하세요.
⚠️ 반드시 전사 내용에서 [Student]의 실제 발화를 **정확히 인용**하세요.
각 항목마다:
- ❌ 학습자 원문 (As Said): [Student]가 실제 말한 문장을 그대로 인용
- ✅ 자연스러운 표현 (Natural): 원어민이 일상에서 쓰는 쉽고 명확한 표현
- 💎 비즈니스 표현 (Professional): 격식 있는 자리에서 쓸 수 있는 고급 표현
- 💡 코칭 포인트: 뉘앙스 차이를 짧고 명확하게 설명

**3. 🔧 고질적 문법 '한 놈만 패기' (Target Grammar)**
⚠️ 이 섹션은 2번(유창성)과 **완전히 다른 관점**입니다.
- 2번은 "어색한 표현 → 자연스러운 표현"으로 바꾸는 것
- 3번은 **문법 규칙 위반** (관사 a/the 누락, 전치사 오류, 시제 불일치, 주어-동사 수일치 등)에 집중
이번 대화에서 [Student]가 반복한 문법 실수 **딱 1가지 패턴**만 골라주세요.
- 전사 내용에서 해당 문법 오류가 나타난 실제 문장 3개 이상을 인용
- 각각 ❌ 원문 / ✅ 교정 예시를 표로 정리
- 📌 핵심 규칙을 한 줄로 정리
- 🔁 따라 읽기: 교정된 문장 3개를 별도로 정리 (🗣️ "...")

**4. 📗 어휘 확장 (Vocabulary Vault)**
수업 중 등장했거나 맥락상 유용한 **표준 영어** 단어 5개:
- **단어** /발음기호/ (품사)
- 뜻: 한국어 의미
- 실전 예문: 학습자의 업무 환경에서 바로 쓸 수 있는 짧은 예문 1개

**5. 📝 실전 복습 챌린지 (Practice)**
오늘 배운 표현과 문법을 활용한 영작 문제 3개 + 모범 답안.
- 한국어 상황 설명 → 영작 요구 형식으로 출제
- 쉬운 문제 → 어려운 문제 순서

**6. ✨ 자신감 충전 & 내일의 미션 (Confidence & Mission)**
- ✨ **Good Job**: [Student]가 가장 잘 표현한 문장을 **전사에서 정확히 인용**하고, 왜 좋았는지 설명
- 🚀 **내일의 한 문장**: 다음 수업 시작 시 튜터에게 던질 수 있는 대화 시작 문장 (오늘 배운 표현 활용)

**[성과 지표]**
유창성 점수(10점 만점) + 근거 + 다음 수업 '원포인트 액션 플랜'.

[전화영어 전사 내용]
{transcript}
"""

    feedback = llm_request(
        prompt,
        max_tokens=12288,
        temperature=0.5,
        timeout=120,
        system_msg=system_msg,
        thinking_budget=2048
    )
    print(f"✅ 피드백 생성 완료: {len(feedback)}자")
    return feedback


# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  [4.5단계] 📝 피드백 품질 검토 (Gemini - 2차 검토)                    ║
# ║  비유: 작성된 성적표를 선임 선생님이 한번 더 검토하는 것               ║
# ║                                                                        ║
# ║  검토 항목: 인용 정확성, 화자 혼동, 내용 누락, 표현 자연스러움         ║
# ╚══════════════════════════════════════════════════════════════════════════╝

def review_feedback(transcript, feedback):
    """
    생성된 피드백을 전사 원문과 대조하여 품질을 검토하고 개선.
    잘못된 인용, 화자 혼동, 누락된 학습 포인트 등을 보완.
    """
    print("📝 피드백 품질 검토 중...")

    prompt = f"""당신은 영어 학습 피드백의 품질 검토자입니다.
아래 [전사 내용]과 [피드백 초안]을 비교하여, 피드백을 개선해주세요.

## 검토 기준

1. **인용 정확성**: 피드백에서 [Student] 발화로 인용한 문장이 전사 내용에 실제로 존재하는가? 없는 문장을 인용했다면 실제 문장으로 교체
2. **화자 혼동**: [Tutor]의 발화를 [Student]의 발화로 잘못 인용한 부분이 없는가? 문법이 완벽한 문장을 학생 실수로 지적하고 있다면 화자 혼동 가능성이 높음
3. **내용 누락**: 학생의 주요 실수나 잘한 점 중 빠진 것이 없는가?
4. **표현 자연스러움**: 한국어 설명이 학습자 입장에서 이해하기 쉬운가?
5. **섹션 중복**: 같은 예문이 여러 섹션에서 반복되지 않는가?

## 작업

- 위 기준에 따라 피드백을 수정·보완하여 **완성본**을 출력
- 형식과 구조는 원본 피드백의 6개 섹션을 그대로 유지
- 추가 설명이나 검토 메모 없이, 개선된 피드백 본문만 출력

[전사 내용]
{transcript}

[피드백 초안]
{feedback}"""

    try:
        reviewed = llm_request(prompt, max_tokens=12288, temperature=0.3, thinking_budget=2048)
        print(f"✅ 피드백 검토 완료: {len(reviewed)}자")
        return reviewed
    except Exception as e:
        print(f"⚠️ 피드백 검토 실패 ({e}), 원본 사용")
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


def deploy_review_page(page_html, date_str, lesson_date=None):
    """
    HTML을 docs/ 폴더에 저장 → 인덱스 갱신 → git push → GitHub Pages에 자동 배포.
    비유: 학습지를 인쇄 → 게시판 목차 갱신 → 게시판에 핀으로 꽂기.
    lesson_date가 주어지면 해당 날짜로 파일명 생성, 없으면 현재 날짜 사용.
    """
    print("🌐 복습 페이지 배포 중...")
    docs_dir = "docs"
    os.makedirs(docs_dir, exist_ok=True)

    slug = (lesson_date or datetime.now(KST)).strftime("%Y-%m-%d")
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
    """복습 기록 전체 목록(index.html)을 최신순으로 갱신. 숨기기 버튼 포함."""

    pages = sorted(glob.glob(os.path.join(docs_dir, "2*.html")), reverse=True)

    items_html = ""
    for p in pages:
        name = os.path.basename(p).replace(".html", "")
        items_html += f'        <div class="item" data-date="{name}"><a href="{os.path.basename(p)}" class="link">{name}</a><button class="del-btn" onclick="hideReview(\'{name}\',this)" title="숨기기">✕</button></div>\n'

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
        .item{{display:flex;align-items:center;gap:8px}}
        .link{{flex:1;display:block;padding:16px 20px;background:#1a1a24;border-radius:10px;color:#cbd5e1;text-decoration:none;font-size:15px;transition:all .2s;border:1px solid transparent}}
        .link:hover{{background:#262636;border-color:rgba(56,189,248,.2);color:#38bdf8}}
        .del-btn{{width:40px;height:40px;background:#1a1a24;border:1px solid transparent;border-radius:10px;color:#64748b;font-size:16px;cursor:pointer;transition:all .2s;flex-shrink:0}}
        .del-btn:hover{{background:#2a1a1e;border-color:rgba(239,68,68,.3);color:#ef4444}}
        .restore{{display:none;text-align:center;margin-top:16px;max-width:480px;margin-left:auto;margin-right:auto}}
        .restore a{{color:#64748b;font-size:13px;cursor:pointer;text-decoration:underline;text-underline-offset:3px}}
        .restore a:hover{{color:#94a3b8}}
        .toast{{position:fixed;bottom:32px;left:50%;transform:translateX(-50%) translateY(80px);background:#1e293b;color:#38bdf8;padding:14px 28px;border-radius:12px;font-size:14px;font-weight:500;border:1px solid rgba(56,189,248,.2);box-shadow:0 8px 32px rgba(0,0,0,.4);opacity:0;transition:all .4s cubic-bezier(.16,1,.3,1);z-index:1000}}
        .toast.show{{opacity:1;transform:translateX(-50%) translateY(0)}}
    </style>
</head>
<body>
    <h1>📚 전화영어 복습 기록</h1>
    <div class="list" id="list">
{items_html if items_html else '        <p style="text-align:center;color:#64748b">아직 복습 기록이 없습니다.</p>'}
    </div>
    <div class="restore" id="restore"><a onclick="restoreAll()">숨긴 항목 다시 보기</a></div>
    <div class="toast" id="toast"></div>
    <script>
    function getHidden(){{return JSON.parse(localStorage.getItem('hidden_reviews')||'[]')}}
    function setHidden(arr){{localStorage.setItem('hidden_reviews',JSON.stringify(arr))}}
    function hideReview(date,btn){{if(!confirm(date+' 복습 기록을 숨길까요?'))return;const h=getHidden();if(!h.includes(date))h.push(date);setHidden(h);btn.closest('.item').style.display='none';updateRestore();showToast('숨김 처리됨')}}
    function restoreAll(){{if(!confirm('숨긴 항목을 모두 다시 표시할까요?'))return;setHidden([]);document.querySelectorAll('.item').forEach(el=>el.style.display='');updateRestore();showToast('모두 복원됨')}}
    function updateRestore(){{document.getElementById('restore').style.display=getHidden().length?'block':'none'}}
    function applyHidden(){{const h=getHidden();document.querySelectorAll('.item').forEach(el=>{{if(h.includes(el.dataset.date))el.style.display='none'}});updateRestore()}}
    function showToast(msg){{const t=document.getElementById('toast');t.textContent=msg;t.className='toast show';setTimeout(()=>t.classList.remove('show'),3000)}}
    applyHidden();
    </script>
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

    # ━━ [중복 체크] 이미 처리한 파일인지 확인 (ID + 파일명 이중 체크) ━━
    if is_already_processed(file_id, filename):
        print("✅ 이미 처리 완료된 파일입니다. 중복 실행 방지로 종료합니다.")
        sys.exit(0)

    # 파일명에서 실제 수업 날짜 추출 (동기화 지연으로 다른 날 처리될 때 대비)
    lesson_date = extract_lesson_date(filename)
    date_str = (lesson_date or now).strftime("%Y년 %m월 %d일")

    try:
        # ━━ [2단계] 음성 → 텍스트 (Groq Whisper) ━━
        transcript_raw, duration, segments = transcribe_audio(audio_path)
        if not transcript_raw.strip():
            print("❌ 전사 결과가 비어있습니다.")
            sys.exit(0)
        print(f"\n📝 원본 전사 (첫 200자):\n{transcript_raw[:200]}...\n")

        # ━━ [3단계] 전사 보정 (화자 분리 + 오인식 수정) ━━
        transcript = clean_transcript(transcript_raw, segments)

        # ━━ [3.5단계] 화자 라벨 검증 (Tutor↔Student 뒤바뀜 방지) ━━
        transcript = verify_speaker_labels(transcript)

        # ━━ [4단계] AI 피드백 생성 ━━
        feedback = generate_feedback(transcript)

        # ━━ [4.5단계] 피드백 품질 검토 (인용 정확성, 화자 혼동, 누락 보완) ━━
        feedback = review_feedback(transcript, feedback)

        # ━━ [5단계] 복습 페이지 생성 & 배포 ━━
        page_html = generate_review_page(transcript, feedback, filename, duration, date_str)
        review_url = deploy_review_page(page_html, date_str, lesson_date)

        # ━━ [6단계] 이메일 발송 ━━
        send_email(feedback, filename, duration, review_url)

        # ━━ [7단계] 완료 파일 이동 ━━
        move_to_done_folder(file_id)

        # ━━ [8단계] 처리 완료 기록 저장 ━━
        save_processed_id(file_id, filename)
        commit_processed_record()

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
