#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
毎日09:00 JSTにThreadsへ投稿するスクリプト
GitHub Actionsから実行される
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

def load_queue():
    path = Path("queue.json")
    if not path.exists():
        print("queue.json が見つかりません")
        return []
    return json.loads(path.read_text(encoding="utf-8"))

def save_queue(queue):
    Path("queue.json").write_text(
        json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8"
    )

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
        raise Exception(f"コンテナ作成失敗: {r.status_code} {r.text}")
    return r.json()["id"]

def wait_for_finished(container_id, max_wait=60):
    for _ in range(max_wait // 5):
        r = requests.get(
            f"https://graph.threads.net/v1.0/{container_id}",
            params={"fields": "status,error_message", "access_token": TOKEN}
        )
        status = r.json().get("status", "")
        if status == "FINISHED":
            return True
        if status in ("ERROR", "EXPIRED"):
            raise Exception(f"コンテナエラー: {r.json()}")
        time.sleep(5)
    raise Exception("タイムアウト: コンテナがFINISHEDになりませんでした")

def publish(container_id):
    r = requests.post(f"{BASE}/threads_publish", data={
        "creation_id": container_id,
        "access_token": TOKEN,
    })
    if r.status_code != 200:
        raise Exception(f"publish失敗: {r.status_code} {r.text}")
    return r.json()["id"]

def main():
    today = datetime.now(JST).strftime("%Y-%m-%d")
    print(f"実行日: {today}")

    queue = load_queue()
    pending = [p for p in queue if p.get("date") == today and p.get("status") == "pending"]

    if not pending:
        print(f"{today} の投稿はありません")
        return

    post = pending[0]
    print(f"投稿: {post.get('text', '')[:50]}")

    try:
        container_id = create_container(post["text"], post.get("image_url"))
        print(f"コンテナ作成: {container_id}")
        wait_for_finished(container_id)
        post_id = publish(container_id)
        print(f"投稿完了: {post_id}")

        post["status"] = "done"
        post["post_id"] = post_id
        save_queue(queue)

    except Exception as e:
        print(f"エラー: {e}")
        post["status"] = "error"
        post["error"] = str(e)
        save_queue(queue)
        raise

if __name__ == "__main__":
    main()
