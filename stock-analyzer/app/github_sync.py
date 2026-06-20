"""GitHub 자동 동기화 — 리포트·모델 상태·학습 DB를 저장소에 커밋해 영구 보관.

Render 무료 티어는 디스크가 휘발성이라 재배포/재시작 시 데이터가 사라진다.
이 모듈은 사이클 ④ 완료 시마다 리포트(.md), 모델 가중치 스냅샷(.json),
그리고 학습 DB 전체(gzip 스냅샷)를 GitHub API로 직접 커밋한다. 또한 콜드
스타트 시 DB 스냅샷을 내려받아 학습을 그대로 이어간다. 표준 라이브러리만 사용.

⚠️ 데이터는 배포 브랜치가 아닌 **별도 데이터 브랜치**(기본 sa-data)에 쌓는다.
   배포 브랜치에 커밋하면 Render 가 매 커밋마다 재배포되는 루프가 생기기 때문.

필요한 환경변수:
  SA_GITHUB_TOKEN        GitHub Personal Access Token (repo Contents 읽기/쓰기)
  SA_GITHUB_REPO         저장소 (기본: kabuden/kms)
  SA_GITHUB_DATA_BRANCH  데이터 전용 브랜치 (기본: sa-data, 없으면 자동 생성)
  SA_GITHUB_DIR          리포트 저장 경로 (기본: stock-analyzer/data/reports)
  SA_GITHUB_SNAPSHOT_DIR 모델 상태 경로 (기본: stock-analyzer/data/snapshots)
  SA_GITHUB_DB_PATH      DB 스냅샷 경로 (기본: .../snapshots/stock.db.gz)
"""
from __future__ import annotations

import base64
import gzip
import json
import logging
import os
import pathlib
import urllib.error
import urllib.request

log = logging.getLogger(__name__)
_API = "https://api.github.com"
_TIMEOUT = 30
_branch_ready = False   # 데이터 브랜치 존재 보장 캐시


def _token() -> str:
    return os.environ.get("SA_GITHUB_TOKEN", "")


def _repo() -> str:
    return os.environ.get("SA_GITHUB_REPO", "kabuden/kms")


def _branch() -> str:
    # 데이터 전용 브랜치(배포 브랜치와 분리). 구버전 SA_GITHUB_BRANCH 도 인정.
    return (os.environ.get("SA_GITHUB_DATA_BRANCH")
            or os.environ.get("SA_GITHUB_BRANCH") or "sa-data")


def _reports_dir() -> str:
    return os.environ.get("SA_GITHUB_DIR", "stock-analyzer/data/reports")


def _db_path_in_repo() -> str:
    return os.environ.get("SA_GITHUB_DB_PATH",
                          "stock-analyzer/data/snapshots/stock.db.gz")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    }


def _ensure_branch() -> bool:
    """데이터 브랜치가 없으면 기본 브랜치 HEAD에서 만들어 둔다(1회)."""
    global _branch_ready
    if _branch_ready:
        return True
    branch = _branch()
    ref_url = f"{_API}/repos/{_repo()}/git/ref/heads/{branch}"
    try:
        with urllib.request.urlopen(
                urllib.request.Request(ref_url, headers=_headers()),
                timeout=_TIMEOUT):
            _branch_ready = True
            return True
    except urllib.error.HTTPError as e:
        if e.code != 404:
            log.warning("github_sync: 브랜치 조회 실패 — %s", e)
            return False
    # 없으면 기본 브랜치 HEAD sha 로 생성
    try:
        with urllib.request.urlopen(
                urllib.request.Request(f"{_API}/repos/{_repo()}",
                                       headers=_headers()),
                timeout=_TIMEOUT) as r:
            default = json.loads(r.read())["default_branch"]
        with urllib.request.urlopen(
                urllib.request.Request(
                    f"{_API}/repos/{_repo()}/git/ref/heads/{default}",
                    headers=_headers()), timeout=_TIMEOUT) as r:
            sha = json.loads(r.read())["object"]["sha"]
        body = {"ref": f"refs/heads/{branch}", "sha": sha}
        req = urllib.request.Request(
            f"{_API}/repos/{_repo()}/git/refs",
            data=json.dumps(body).encode(), headers=_headers(), method="POST")
        with urllib.request.urlopen(req, timeout=_TIMEOUT):
            log.info("github_sync: 데이터 브랜치 생성 → %s", branch)
            _branch_ready = True
            return True
    except Exception as exc:
        log.warning("github_sync: 데이터 브랜치 보장 실패 — %s", exc)
        return False


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


def _get_file_bytes(path: str) -> bytes | None:
    """파일의 원본 바이트를 내려받는다 (없으면 None)."""
    url = f"{_API}/repos/{_repo()}/contents/{path}?ref={_branch()}"
    headers = _headers()
    headers["Accept"] = "application/vnd.github.raw"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def _put_bytes(path: str, raw: bytes, message: str) -> bool:
    """바이트를 path에 커밋한다. 성공하면 True."""
    if not _ensure_branch():
        return False
    sha = _get_sha(path)
    body: dict = {
        "message": message,
        "content": base64.b64encode(raw).decode(),
        "branch": _branch(),
    }
    if sha:
        body["sha"] = sha
    url = f"{_API}/repos/{_repo()}/contents/{path}"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers=_headers(), method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT):
            return True
    except Exception as exc:
        log.warning("github_sync: PUT %s 실패 — %s", path, exc)
        return False


def _put_file(path: str, content_str: str, message: str) -> bool:
    """문자열을 path에 커밋한다. 성공하면 True."""
    return _put_bytes(path, content_str.encode(), message)


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


def push_db_snapshot(db_file, label: str = "") -> bool:
    """학습 DB 파일 전체를 gzip 으로 압축해 데이터 브랜치에 커밋한다."""
    if not _token():
        return False
    try:
        raw = pathlib.Path(db_file).read_bytes()
    except Exception as exc:
        log.warning("github_sync: DB 읽기 실패 — %s", exc)
        return False
    gz = gzip.compress(raw)
    msg = f"chore(stock-analyzer): db snapshot {label}".strip()
    ok = _put_bytes(_db_path_in_repo(), gz, msg)
    if ok:
        log.info("github_sync: DB 스냅샷 커밋 (%d→%d bytes)", len(raw), len(gz))
    return ok


def restore_db_snapshot(db_file) -> bool:
    """데이터 브랜치의 DB 스냅샷을 내려받아 로컬 DB로 복원한다.

    복원에 성공하면 True. 토큰이 없거나 스냅샷이 없으면 False.
    """
    if not _token():
        return False
    try:
        gz = _get_file_bytes(_db_path_in_repo())
    except Exception as exc:
        log.warning("github_sync: DB 스냅샷 조회 실패 — %s", exc)
        return False
    if not gz:
        return False
    try:
        raw = gzip.decompress(gz)
        p = pathlib.Path(db_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(raw)
        log.info("github_sync: DB 스냅샷 복원 완료 (%d bytes)", len(raw))
        return True
    except Exception as exc:
        log.warning("github_sync: DB 복원 실패 — %s", exc)
        return False


def selftest() -> str:
    """토큰·권한·브랜치 상태를 진단해 사람이 읽을 한 줄을 돌려준다(비밀 노출 없음).

    시작 시 로그에 찍어, 영구 보관이 왜 동작/미동작하는지 즉시 알 수 있게 한다.
    """
    tok = _token()
    if not tok:
        return ("github_sync 진단: SA_GITHUB_TOKEN 미설정 → 영구 보관 비활성. "
                "Render Environment 에 토큰을 추가하세요.")
    prefix_ok = tok.startswith(("github_pat_", "ghp_", "gho_", "ghs_"))
    head = tok[:11]
    # 1) 인증 + 저장소 접근 확인
    try:
        with urllib.request.urlopen(
                urllib.request.Request(f"{_API}/repos/{_repo()}",
                                       headers=_headers()),
                timeout=_TIMEOUT):
            pass
    except urllib.error.HTTPError as e:
        hint = ("토큰 무효/만료 또는 권한 부족" if e.code in (401, 403)
                else "저장소 접근 불가" if e.code == 404 else f"HTTP {e.code}")
        warn = ("" if prefix_ok
                else " (값이 'github_pat_'로 시작하지 않음 — prefix 누락 의심)")
        return (f"github_sync 진단: 인증 실패 [{hint}] repo={_repo()} "
                f"len={len(tok)} head='{head}…'{warn}")
    except Exception as exc:
        return f"github_sync 진단: 네트워크 오류 — {exc}"
    # 2) 데이터 브랜치 보장(없으면 생성 시도)
    branch_ok = _ensure_branch()
    snap = "있음" if _get_sha(_db_path_in_repo()) else "없음"
    return (f"github_sync 진단: ✅ 인증 OK repo={_repo()} "
            f"data_branch={_branch()}({'준비됨' if branch_ok else '생성실패'}) "
            f"기존 스냅샷={snap} len={len(tok)} head='{head}…'")


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

