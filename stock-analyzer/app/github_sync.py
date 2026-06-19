"""GitHub 자동 동기화 — 리포트와 모델 상태를 저장소에 커밋해 영구 보관한다.

Render 무료 티어는 디스크가 휘발성이라 재배포 시 데이터가 사라진다.
이 모듈은 사이클 ④ 완료 시마다 리포트(.md)와 모델 가중치 스냅샷(.json)을
GitHub API로 직접 커밋한다. 표준 라이브러리만 사용한다.

필요한 환경변수:
  SA_GITHUB_TOKEN   GitHub Personal Access Token (repo Contents 쓰기 권한)
  SA_GITHUB_REPO    저장소 (기본: kabuden/kms)
  SA_GITHUB_BRANCH  커밋 대상 브랜치 (기본: main)
  SA_GITHUB_DIR     리포트 저장 경로 (기본: stock-analyzer/data/reports)
"""
from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger(__name__)
_API = "https://api.github.com"
_TIMEOUT = 20


def _token() -> str:
    return os.environ.get("SA_GITHUB_TOKEN", "")


def _repo() -> str:
    return os.environ.get("SA_GITHUB_REPO", "kabuden/kms")


def _branch() -> str:
    return os.environ.get("SA_GITHUB_BRANCH", "main")


def _reports_dir() -> str:
    return os.environ.get("SA_GITHUB_DIR", "stock-analyzer/data/reports")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }


def _get_sha(path: str) -> str | None:
    """현재 파일의 SHA를 가져온다 (파일이 없으면 None)."""
    url = f"{_API}/repos/{_repo()}/contents/{path}?ref={_branch()}"
    req = urllib.request.Request(url, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read()).get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def _put_file(path: str, content_str: str, message: str) -> bool:
    """문자열을 path에 커밋한다. 성공하면 True."""
    sha = _get_sha(path)
    body: dict = {
        "message": message,
        "content": base64.b64encode(content_str.encode()).decode(),
        "branch": _branch(),
    }
    if sha:
        body["sha"] = sha

    url = f"{_API}/repos/{_repo()}/contents/{path}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers=_headers(),
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT):
            return True
    except Exception as exc:
        log.warning("github_sync: PUT %s 실패 — %s", path, exc)
        return False


def push_report(cycle_date: str, markdown: str) -> bool:
    """일일 리포트 마크다운을 GitHub에 저장한다."""
    if not _token():
        return False
    path = f"{_reports_dir()}/{cycle_date}.md"
    ok = _put_file(
        path, markdown,
        f"chore(stock-analyzer): daily report {cycle_date}",
    )
    if ok:
        log.info("github_sync: 리포트 커밋 완료 → %s", path)
    return ok


def push_model_state(cycle_date: str, state: dict) -> bool:
    """가중치·정확도 스냅샷을 JSON으로 저장한다 (재시작 후 열람용).

    state = {
      "cycle_date": ...,
      "weights": {predictor_name: weight, ...},
      "rolling_accuracy": ...,
      "calibrated_confidence": ...,
      "trade_ready": ...,
    }
    """
    if not _token():
        return False
    repo_dir = os.environ.get("SA_GITHUB_SNAPSHOT_DIR",
                              "stock-analyzer/data/snapshots")
    path = f"{repo_dir}/{cycle_date}_state.json"
    ok = _put_file(
        path, json.dumps(state, ensure_ascii=False, indent=2),
        f"chore(stock-analyzer): model state {cycle_date}",
    )
    if ok:
        log.info("github_sync: 모델 상태 커밋 완료 → %s", path)
    return ok
