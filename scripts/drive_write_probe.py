#!/usr/bin/env python3
"""
🔎 Drive 쓰기 가능 여부 점검 / Drive write probe.

서비스 계정이 '완료' 폴더에 작은 JSON 파일을 새로 만들 수 있는지 확인하고, 만든 파일은 바로 지운다.
서비스 계정은 저장 용량이 없어 새 파일 생성이 거부될 수 있다(storageQuotaExceeded) — 그 여부를 확인한다.
Checks whether the service account can create a small JSON file in the done folder, then deletes it.

종료 코드: 0=생성·삭제 성공 / 1=생성 실패(사유 출력) / 2=설정 누락
"""
import base64
import io
import json
import os
import sys

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload


def main():
    creds_b64 = os.environ.get("GOOGLE_CREDENTIALS", "")
    folder = os.environ.get("DRIVE_RAW_FOLDER_ID", "").strip() or os.environ.get("DRIVE_DONE_FOLDER_ID", "").strip()
    if not creds_b64 or not folder:
        print("설정 누락: GOOGLE_CREDENTIALS 또는 폴더 ID 없음")
        return 2
    creds = service_account.Credentials.from_service_account_info(
        json.loads(base64.b64decode(creds_b64)),
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    service = build("drive", "v3", credentials=creds, cache_discovery=False)

    # 폴더 정보: 공유 드라이브인지, 서비스 계정 권한이 무엇인지
    try:
        info = service.files().get(
            fileId=folder, fields="mimeType,driveId,capabilities(canAddChildren)", supportsAllDrives=True
        ).execute()
        print(f"폴더: shared_drive={'yes' if info.get('driveId') else 'no'} "
              f"canAddChildren={info.get('capabilities', {}).get('canAddChildren')}")
    except Exception as e:
        print(f"폴더 조회 실패: {type(e).__name__}: {str(e)[:300]}")

    def attempt(label, body, media=None):
        """한 가지 방식으로 만들어 보고, 만들어졌으면 바로 지운다 / try one way, then clean up."""
        try:
            kw = {"body": body, "fields": "id", "supportsAllDrives": True}
            if media is not None:
                kw["media_body"] = media
            created = service.files().create(**kw).execute()
        except Exception as e:
            print(f"{label}: FAIL {type(e).__name__}: {str(e)[:260]}")
            return False
        print(f"{label}: OK")
        try:
            service.files().delete(fileId=created["id"], supportsAllDrives=True).execute()
        except Exception as e:
            print(f"{label}: 삭제 실패 — 시험 항목이 남았을 수 있음: {str(e)[:200]}")
        return True

    payload = json.dumps({"probe": True}).encode("utf-8")
    name = "_whisper_raw_probe"
    r1 = attempt("A_json_file", {"name": name + ".json", "parents": [folder]},
                 MediaIoBaseUpload(io.BytesIO(payload), mimetype="application/json", resumable=False))
    r2 = attempt("B_google_doc_from_text", {"name": name, "parents": [folder],
                                            "mimeType": "application/vnd.google-apps.document"},
                 MediaIoBaseUpload(io.BytesIO(payload), mimetype="text/plain", resumable=False))
    r3 = attempt("C_empty_google_doc", {"name": name, "parents": [folder],
                                        "mimeType": "application/vnd.google-apps.document"})
    r4 = attempt("D_folder", {"name": name, "parents": [folder],
                              "mimeType": "application/vnd.google-apps.folder"})
    return 0 if (r1 or r2 or r3 or r4) else 1


if __name__ == "__main__":
    sys.exit(main())
