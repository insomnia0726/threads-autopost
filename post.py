#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
毎日09:00 JSTにWordPress記事をThreadsへ自動投稿するスクリプト
GitHub Actionsから実行される（毎日 0:00 UTC = 9:00 JST）
"""
import os
import re
import time
import base64
import requests
from datetime import datetime, timezone, timedelta

TOKEN = os.environ["THREADS_TOKEN"]
USER_ID = os.environ["THREADS_USER_ID"]
WP_USER = os.environ["WP_USERNAME"]
WP_PASS = os.environ["WP_APP_PASSWORD"]

WP_URL = "https://car-mikata.com/wp-json/wp/v2"
SITE_URL = "https://car-mikata.com"
TOPIC_TAG = "自動車保険"
BASE = f"https://graph.threads.net/v1.0/{USER_ID}"
JST = timezone(timedelta(hours=9))

# Threadsトークン有効期限（2026/8/17）
TOKEN_EXPIRY = datetime(2026, 8, 17, tzinfo=JST)


def check_token_expiry():
    days_left = (TOKEN_EXPIRY - datetime.now(JST)).days
    if days_left <= 14:
        print(f"⚠️ 警告：Threadsトークンの有効期限まで残り{days_left}日（{TOKEN_EXPIRY.strftime('%Y/%m/%d')}）")
        print("⚠️ Meta Developersコンソール → ユーザートークン生成ツール でトークンを更新してください")
    else:
        print(f"トークン有効期限まで残り{days_left}日")


def get_wp_headers():
    token = base64.b64encode(f"{WP_USER}:{WP_PASS}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def get_today_posts():
    """今日09:00 JSTに公開予定の記事を取得"""
    today = datetime.now(JST).strftime("%Y-%m-%d")
    wp_h = get_wp_headers()

    r = requests.get(f"{WP_URL}/posts", headers=wp_h, params={
        "status": "publish,future",
        "after": f"{today}T00:00:00",
        "before": f"{today}T00:00:59",
        "per_page": 5,
        "fields": "id,title,slug,excerpt,featured_media,date_gmt",
    })

    if r.status_code != 200:
        print(f"WP APIエラー: {r.status_code} {r.text[:100]}")
        return []

    posts = r.json()
    # date_gmt が今日のT00:00:00に一致するものを抽出
    matched = [p for p in posts if p.get("date_gmt", "").startswith(f"{today}T00:00:0")]
    print(f"今日({today})の対象記事: {len(matched)}件")
    return matched


def get_image_url(media_id):
    if not media_id:
        return None
    wp_h = get_wp_headers()
    r = requests.get(f"{WP_URL}/media/{media_id}", headers=wp_h, params={"fields": "source_url"})
    if r.status_code == 200:
        return r.json().get("source_url")
    return None


def clean_html(text):
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def build_post_text(post):
    excerpt = clean_html(post.get("excerpt", {}).get("rendered", ""))
    slug = post["slug"]
    url = f"{SITE_URL}/{slug}/"

    # 抜粋を140文字以内に収める
    if len(excerpt) > 140:
        excerpt = excerpt[:137] + "..."

    return f"{excerpt}\n\n\U0001f449 {url}"


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
    raise Exception("タイムアウト: コンテナがFINISHEDになりませんでした")


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

    posts = get_today_posts()
    if not posts:
        today = datetime.now(JST).strftime("%Y-%m-%d")
        print(f"{today} に投稿する記事はありません")
        return

    # 1日1件（最初の1件のみ）
    post = posts[0]
    title = clean_html(post["title"]["rendered"])
    slug = post["slug"]
    print(f"投稿対象: [{post['id']}] {title}")

    image_url = get_image_url(post.get("featured_media"))
    text = build_post_text(post)

    print(f"テキスト:\n{text}")
    print(f"画像URL: {image_url}")

    container_id = create_container(text, image_url)
    print(f"コンテナ作成: {container_id}")

    wait_finished(container_id)
    post_id = publish_container(container_id)
    print(f"✅ 投稿完了: {post_id}")
    print(f"URL: {SITE_URL}/{slug}/")


if __name__ == "__main__":
    main()
