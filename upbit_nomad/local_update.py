"""이 PC에서 독립적으로 사이트를 갱신하는 스크립트 (GitHub 예약 실행이 빠질 때를 대비한 두 번째 경로).
Windows 작업 스케줄러가 매시간 실행합니다. 이미 최신 4시간봉으로 계산돼 있으면 몇 초 만에 끝납니다.
전용 복사본(.upbit-runner\\nomad)에서만 동작하며, 충돌이 나면 GitHub 쪽이 먼저 갱신한 것이므로 양보합니다."""
import os
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
LOG = os.path.join(os.path.dirname(REPO), "update.log")
GIT = ["git", "-c", "user.name=upbit-local-runner", "-c", "user.email=kachia84-blip@users.noreply.github.com"]


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    try:
        old = open(LOG, encoding="utf-8").read().splitlines()[-300:] if os.path.exists(LOG) else []
        open(LOG, "w", encoding="utf-8").write("\n".join(old + [line]) + "\n")
    except OSError:
        pass


def git(*args, cwd=REPO):
    return subprocess.run(GIT + list(args), cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")


def main():
    r = git("fetch", "-q", "origin")
    if r.returncode:
        return log(f"fetch 실패(네트워크?): {r.stderr.strip()[:200]}")
    git("reset", "--hard", "origin/main")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    s = subprocess.run([sys.executable, "scan.py", "--out", os.path.join(REPO, "docs", "upbit"), "--if-needed"], cwd=HERE,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=900)
    out = (s.stdout.strip().splitlines() or [""])[0]
    if s.returncode:
        return log(f"스캔 실패: {s.stderr.strip()[-300:]}")
    if git("status", "--porcelain", "docs/upbit").stdout.strip() == "":
        return log(f"변경 없음 - {out}")
    git("add", "docs/upbit")
    git("commit", "-q", "-m", "업비트 4시간봉 스캔 갱신 (PC)")
    p = git("push", "-q", "origin", "HEAD:main")
    if p.returncode:
        git("fetch", "-q", "origin")
        git("reset", "--hard", "origin/main")
        return log(f"push 충돌 - GitHub 쪽이 먼저 갱신한 것으로 보고 양보: {p.stderr.strip()[:120]}")
    log(f"갱신 후 push 완료 - {out}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:           # 스케줄러가 멈추지 않게 항상 정상 종료
        log(f"예외: {e!r}")
