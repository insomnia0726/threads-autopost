#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
毎日09:00 JSTにqueue.jsonから投稿するスクリプト
GitHub Actionsから実行される（毎日 0:00 UTC = 9:00 JST）
"""
import os
import json
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

TOKEN = os.environ["THREADS_TOKEN"]
USER_ID = os.environ["THREADS_USER_ID"]
TOPIC_TAG = "自動車保険"
BASE = f"https://graph.threads.net/v1.0/{USER_ID}"
JST = timezone(timedelta(hours=9))

TOKEN_EXPIRY = datetime(2026, 8, 17, tzinfo=JST)


def check_token_expiry():
    days_left = (TOKEN_EXPIRY - datetime.now(JST)).days
    if days_left <= 14:
        print(f"⚠️ トークン期限まで残り{days_left}日（{TOKEN_EXPIRY.strftime('%Y/%m/%d')}）要更新")
    else:
        print(f"トークン有効期限まで残り{days_left}日")


def create_container(text, image_url=None):
    data = {
        "media_type": "IMAGE" if image_url else "TEXT",
        "text": text,
        "topic_tag": TOPIC_TAG,
        "access_token": TOKEN,
    }
    if image_url:
        data["image_url"] = image_url
    r = requests.post(f"{BASE}/threads", data=data)
    if r.status_code != 200:
        raise Exception(f"コンテナ作成失敗: {r.status_code} {r.text[:200]}")
    return r.json()["id"]


def wait_finished(container_id, max_wait=90):
    for _ in range(max_wait // 5):
        r = requests.get(
            f"https://graph.threads.net/v1.0/{container_id}",
            params={"fields": "status,error_message", "access_token": TOKEN}
        )
        d = r.json()
        status = d.get("status", "")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise Exception(f"コンテナエラー: {d}")
        time.sleep(5)
    raise Exception("タイムアウト")


def publish_container(container_id):
    r = requests.post(f"{BASE}/threads_publish", data={
        "creation_id": container_id,
        "access_token": TOKEN,
    })
    if r.status_code != 200:
        raise Exception(f"publish失敗: {r.status_code} {r.text[:200]}")
    return r.json()["id"]


def main():
    print("=== Threads Auto Post 開始 ===")
    check_token_expiry()

    today = datetime.now(JST).strftime("%Y-%m-%d")
    print(f"実行日: {today}")

    queue_path = Path("queue.json")
    if not queue_path.exists():
        print("queue.jsonが見つかりません")
        return

    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    pending = [p for p in queue if p.get("date") == today and p.get("status") == "pending"]

    if not pending:
        print(f"{today} の投稿はありません")
        return

    post = pending[0]
    print(f"投稿対象: {post.get('title', '')[:40]}")

    try:
        container_id = create_container(post["text"], post.get("image_url"))
        print(f"コンテナ作成: {container_id}")
        wait_finished(container_id)
        post_id = publish_container(container_id)
        print(f"✅ 投稿完了: {post_id}")

        post["status"] = "done"
        post["post_id"] = post_id
        queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")

    except Exception as e:
        print(f"❌ エラー: {e}")
        post["status"] = "error"
        post["error"] = str(e)
        queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
