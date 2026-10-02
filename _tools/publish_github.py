# -*- coding: utf-8 -*-
"""
★ GitHub 发布器（第 53 轮建）：把 make_release 的产物直接发布成 GitHub 单提交

为什么不用 git push：
  1. github.com:443 在本机时常连不上（api.github.com 反而稳定）；
  2. 历史里冻着早期半脱敏的版本 —— 每次发布用 Git Data API 重建成
     **单个干净提交**（孤儿提交，force 更新 main），历史永远只有这一条。

用法：
    python _tools/publish_github.py                 # 默认提交信息
    python _tools/publish_github.py "自定义信息"
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGE = os.path.join(ROOT, "_release", "Taku")
REPO = "LIJUMN/taku"
API = "https://api.github.com"
EXEC_EXT = {".exe", ".dll", ".apk", ".whl", ".so", ".bin"}


def _token():
    """GitHub PAT 从 config.json 读（该文件在 .gitignore 里，永不进包）。
    ★ 第 52 轮教训：token 写死在脚本里 = 差点被自己推上开源库，
      GitHub 的 secret scanning 直接 422 拦下 —— 该谢谢它。"""
    with open(os.path.join(ROOT, "config", "config.json"), encoding="utf-8") as f:
        t = json.load(f).get("github_token")
    if not t:
        raise SystemExit("config.json 里没有 github_token —— 填上再发布")
    return t


def api(path, method="GET", body=None):
    req = urllib.request.Request(API + path,
                                 data=(json.dumps(body).encode() if body else None),
                                 method=method)
    req.add_header("Authorization", "Bearer " + _token())
    req.add_header("Accept", "application/vnd.github+json")
    for attempt in range(4):
        try:
            return json.load(urllib.request.urlopen(req, timeout=60))
        except urllib.error.HTTPError as e:
            if e.code >= 500 or e.code == 403:
                time.sleep(6)
                continue
            raise
        except Exception:
            if attempt == 3:
                raise
            time.sleep(5)


def build_stage():
    print("① 构建发布目录（make_release）…", flush=True)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "_tools", "make_release.py")],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = (r.stdout or "").strip().splitlines()[-1:]
    print("   ", tail[0] if tail else "(无输出)", flush=True)


def collect_files():
    out = []
    for dirpath, _dirs, files in os.walk(STAGE):
        for fn in files:
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, STAGE).replace("\\", "/")
            out.append((rel, p))
    return sorted(out)


def publish(message):
    files = collect_files()
    print("② 共 %d 个文件，逐个上传 blob…" % len(files), flush=True)
    tree = []
    for i, (rel, p) in enumerate(files):
        with open(p, "rb") as f:
            data = f.read()
        ext = os.path.splitext(rel)[1].lower()
        try:
            data.decode("utf-8")
            body = {"content": data.decode("utf-8"), "encoding": "utf-8"}
        except Exception:
            body = {"content": base64.b64encode(data).decode(), "encoding": "base64"}
        try:
            blob = api("/repos/%s/git/blobs" % REPO, "POST", body)
        except urllib.error.HTTPError as e:
            detail = e.read()[:200].decode("utf-8", "replace")
            print("   ✘ blob 失败 [%s]: HTTP %d %s" % (rel, e.code, detail), flush=True)
            raise
        mode = "100755" if ext in EXEC_EXT else "100644"
        tree.append({"path": rel, "mode": mode, "type": "blob", "sha": blob["sha"]})
        if (i + 1) % 20 == 0:
            print("   %d/%d…" % (i + 1, len(files)), flush=True)
        time.sleep(0.15)

    print("③ 建树（%d 项）…" % len(tree), flush=True)
    try:
        t = api("/repos/%s/git/trees" % REPO, "POST", {"tree": tree})
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace")
        print("   ✘ 建树失败: HTTP %d %s" % (e.code, detail), flush=True)
        raise

    print("④ 建孤儿提交（历史重置为这一条）…", flush=True)
    try:
        c = api("/repos/%s/git/commits" % REPO, "POST",
                {"message": message, "tree": t["sha"], "parents": []})
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace")
        print("   ✘ 建提交失败: HTTP %d %s" % (e.code, detail), flush=True)
        raise

    print("⑤ 强制更新 main…", flush=True)
    try:
        api("/repos/%s/git/refs/heads/main" % REPO, "PATCH",
            {"sha": c["sha"], "force": True})
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace")
        print("   ✘ 更新 ref 失败: HTTP %d %s" % (e.code, detail), flush=True)
        raise

    print("⑥ 完成：%s | 提交 %s" % (REPO, c["sha"][:8]), flush=True)


def verify():
    commits = api("/repos/%s/commits" % REPO)
    print("⑦ 验证：历史提交数 =", len(commits), flush=True)
    tree = api("/repos/%s/git/trees/%s?recursive=1" % (REPO, commits[0]["commit"]["tree"]["sha"]))
    n = len([t for t in tree["tree"] if t["type"] == "blob"])
    print("   文件数 =", n, flush=True)
    return len(commits) == 1


if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "Taku 测试版更新（演示数据）"
    build_stage()
    publish(msg)
    ok = verify()
    sys.exit(0 if ok else 1)
