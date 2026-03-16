#!/usr/bin/env python3
"""
워드프레스 관리 스크립트 - 기존 콘텐츠 삭제 + REST API로 글/이미지 업로드

사용법:
  1. 워드프레스 관리자 → 사용자 → 프로필 → 애플리케이션 비밀번호 생성
  2. 아래 설정에 사용자명과 앱 비밀번호 입력
  3. python3 wp_manage.py --delete-all   (기존 콘텐츠 전체 삭제)
  4. python3 wp_manage.py --upload       (글 + 이미지 업로드)
  5. python3 wp_manage.py --all          (삭제 → 업로드 한번에)
"""

import os
import re
import sys
import json
import time
import base64
import mimetypes
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import quote
from bs4 import BeautifulSoup

# ─── 설정 (여기만 수정하면 됩니다) ───────────────────────
WP_URL = "https://your-site.com"          # 워드프레스 주소
WP_USER = "your_username"                 # 워드프레스 사용자명
WP_APP_PASSWORD = ""                      # 애플리케이션 비밀번호 (사용자→프로필에서 생성)
BACKUP_DIR = "./your-tistory-backup"      # 티스토리 백업 폴더 경로
# ────────────────────────────────────────────────────────

API = f"{WP_URL}/wp-json/wp/v2"


def get_credentials():
    """인증 정보 반환."""
    global WP_APP_PASSWORD
    if not WP_APP_PASSWORD:
        WP_APP_PASSWORD = input("워드프레스 애플리케이션 비밀번호 입력: ").strip()
    token = base64.b64encode(f"{WP_USER}:{WP_APP_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def api_request(method, endpoint, headers, data=None, files=None):
    """WordPress REST API 요청."""
    url = f"{API}/{endpoint}"

    if files:
        # 파일 업로드 (multipart)
        import io
        boundary = "----WPBoundary" + str(int(time.time()))
        body = io.BytesIO()

        for key, (filename, filedata, content_type) in files.items():
            body.write(f"--{boundary}\r\n".encode())
            body.write(f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode())
            body.write(f"Content-Type: {content_type}\r\n\r\n".encode())
            body.write(filedata)
            body.write(b"\r\n")

        if data:
            for key, value in data.items():
                body.write(f"--{boundary}\r\n".encode())
                body.write(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
                body.write(str(value).encode())
                body.write(b"\r\n")

        body.write(f"--{boundary}--\r\n".encode())
        body_bytes = body.getvalue()

        req = Request(url, data=body_bytes, method=method)
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    elif data:
        body_bytes = json.dumps(data).encode('utf-8')
        req = Request(url, data=body_bytes, method=method)
        req.add_header("Content-Type", "application/json")
    else:
        req = Request(url, method=method)

    for k, v in headers.items():
        req.add_header(k, v)

    try:
        with urlopen(req) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else ""
        print(f"  API 오류 {e.code}: {error_body[:200]}")
        return None


def delete_all_content(headers):
    """모든 글, 페이지, 미디어 삭제."""
    print("\n" + "=" * 60)
    print("기존 워드프레스 콘텐츠 전체 삭제")
    print("=" * 60)

    for post_type in ["posts", "pages", "media"]:
        print(f"\n[{post_type}] 삭제 중...")
        page = 1
        total_deleted = 0

        while True:
            # status=any로 모든 상태의 글 가져오기
            params = "per_page=100&page={}&status=any".format(page)
            if post_type == "media":
                params = "per_page=100&page={}".format(page)

            try:
                url = f"{API}/{post_type}?{params}"
                req = Request(url)
                for k, v in headers.items():
                    req.add_header(k, v)
                with urlopen(req) as resp:
                    items = json.loads(resp.read().decode('utf-8'))
            except HTTPError:
                break

            if not items:
                break

            for item in items:
                item_id = item['id']
                result = api_request("DELETE", f"{post_type}/{item_id}?force=true", headers)
                if result:
                    total_deleted += 1
                    print(f"  삭제: {post_type}/{item_id}", end="\r")

            page += 1

        print(f"  → {post_type}: {total_deleted}개 삭제 완료")

    # 카테고리 삭제 (기본 카테고리 제외)
    print(f"\n[categories] 삭제 중...")
    try:
        url = f"{API}/categories?per_page=100"
        req = Request(url)
        for k, v in headers.items():
            req.add_header(k, v)
        with urlopen(req) as resp:
            cats = json.loads(resp.read().decode('utf-8'))
        cat_deleted = 0
        for cat in cats:
            if cat['id'] != 1:  # 기본 카테고리(미분류) 제외
                api_request("DELETE", f"categories/{cat['id']}?force=true", headers)
                cat_deleted += 1
        print(f"  → categories: {cat_deleted}개 삭제 완료")
    except HTTPError:
        print("  → categories: 삭제 실패")

    # 태그 삭제
    print(f"\n[tags] 삭제 중...")
    page = 1
    tag_deleted = 0
    while True:
        try:
            url = f"{API}/tags?per_page=100&page={page}"
            req = Request(url)
            for k, v in headers.items():
                req.add_header(k, v)
            with urlopen(req) as resp:
                tags = json.loads(resp.read().decode('utf-8'))
        except HTTPError:
            break
        if not tags:
            break
        for tag in tags:
            api_request("DELETE", f"tags/{tag['id']}?force=true", headers)
            tag_deleted += 1
        page += 1
    print(f"  → tags: {tag_deleted}개 삭제 완료")

    print("\n전체 삭제 완료!")


def extract_post_info(html_content, post_id):
    """HTML에서 메타데이터 + 본문 추출."""
    soup = BeautifulSoup(html_content, 'html.parser')

    title_el = soup.find('h2', class_='title-article')
    title = title_el.get_text(strip=True) if title_el else "Untitled"

    date_el = soup.find('p', class_='date')
    date_str = date_el.get_text(strip=True) if date_el else "2020-01-01 00:00:00"

    cat_el = soup.find('p', class_='category')
    category = cat_el.get_text(strip=True) if cat_el else ""

    tags_el = soup.find('div', class_='tags')
    tags = []
    if tags_el:
        tag_text = tags_el.get_text(strip=True)
        tags = [t.strip() for t in tag_text.split('#') if t.strip()]

    content_el = soup.find('div', class_='contents_style')
    content = content_el.decode_contents().strip() if content_el else ""

    return {
        'id': post_id,
        'title': title,
        'date': date_str,
        'category': category,
        'tags': tags,
        'content': content,
    }


def clean_content_for_wp(content, post_id, image_url_map):
    """본문 정리: OG카드 변환, 링크 변환, 이미지 URL 변환."""
    # OG 카드 → 심플 링크
    soup = BeautifulSoup(content, 'html.parser')
    for fig in soup.find_all('figure', attrs={'data-ke-type': 'opengraph'}):
        title = fig.get('data-og-title', '')
        url = fig.get('data-og-url', '') or fig.get('data-og-source-url', '')
        if title and url:
            new_tag = soup.new_tag('p')
            link = soup.new_tag('a', href=url, target='_blank')
            link.string = title
            new_tag.append(link)
            fig.replace_with(new_tag)
        else:
            fig.decompose()
    content = str(soup)

    # 가로줄 figure → <hr>
    content = re.sub(
        r'<figure[^>]*data-ke-type="horizontalRule"[^>]*>.*?</figure>',
        '<hr/>', content, flags=re.DOTALL
    )

    # 내부 링크 변환: your-blog.tistory.com/{id} → your-site.com/{id}/
    def replace_link(match):
        pid = match.group(1)
        return f"https://your-site.com/{pid}/"

    content = re.sub(
        r'https?://your-blog\.tistory\.com/(\d+)(?:\?[^"<\s]*)?',
        replace_link, content
    )
    content = re.sub(
        r'(?<!/)your-blog\.tistory\.com/(\d+)(?:\?[^"<\s]*)?',
        replace_link, content
    )

    # 이미지 경로 변환 (업로드된 이미지 URL로 교체)
    for local_name, wp_url in image_url_map.items():
        content = content.replace(f'./img/{local_name}', wp_url)

    # og-host 잔여물 제거
    content = re.sub(r'<p class="og-host">.*?</p>', '', content, flags=re.DOTALL)

    return content.strip()


def upload_image(filepath, post_id, headers):
    """이미지를 워드프레스 미디어 라이브러리에 업로드."""
    filename = os.path.basename(filepath)
    content_type = mimetypes.guess_type(filepath)[0] or 'image/jpeg'

    with open(filepath, 'rb') as f:
        file_data = f.read()

    # 파일명에 post_id 포함시켜 구분
    wp_filename = f"tistory-{post_id}-{filename}"

    result = api_request("POST", "media", headers,
                         files={"file": (wp_filename, file_data, content_type)})

    if result and 'source_url' in result:
        return result['source_url'], result['id']
    return None, None


def get_or_create_category(name, parent_id, headers, cache):
    """카테고리 가져오기 또는 생성."""
    if name in cache:
        return cache[name]

    # 검색
    try:
        url = f"{API}/categories?search={quote(name)}&per_page=10"
        req = Request(url)
        for k, v in headers.items():
            req.add_header(k, v)
        with urlopen(req) as resp:
            cats = json.loads(resp.read().decode('utf-8'))
        for cat in cats:
            if cat['name'] == name:
                cache[name] = cat['id']
                return cat['id']
    except HTTPError:
        pass

    # 생성
    data = {"name": name}
    if parent_id:
        data["parent"] = parent_id
    result = api_request("POST", "categories", headers, data=data)
    if result:
        cache[name] = result['id']
        return result['id']
    return None


def get_or_create_tag(name, headers, cache):
    """태그 가져오기 또는 생성."""
    if name in cache:
        return cache[name]

    # 검색
    try:
        url = f"{API}/tags?search={quote(name)}&per_page=10"
        req = Request(url)
        for k, v in headers.items():
            req.add_header(k, v)
        with urlopen(req) as resp:
            tags = json.loads(resp.read().decode('utf-8'))
        for tag in tags:
            if tag['name'] == name:
                cache[name] = tag['id']
                return tag['id']
    except HTTPError:
        pass

    # 생성
    result = api_request("POST", "tags", headers, data={"name": name})
    if result:
        cache[name] = result['id']
        return result['id']
    return None


def upload_all(headers):
    """모든 글과 이미지를 워드프레스에 업로드."""
    print("\n" + "=" * 60)
    print("티스토리 → 워드프레스 업로드")
    print("=" * 60)

    cat_cache = {}
    tag_cache = {}

    folders = sorted(
        [f for f in os.listdir(BACKUP_DIR)
         if os.path.isdir(os.path.join(BACKUP_DIR, f)) and f.isdigit()],
        key=int
    )

    total = len(folders)
    success = 0
    errors = []

    for i, folder in enumerate(folders, 1):
        folder_path = os.path.join(BACKUP_DIR, folder)
        post_id = int(folder)

        html_files = [f for f in os.listdir(folder_path) if f.endswith('.html')]
        if not html_files:
            continue

        html_file = html_files[0]
        with open(os.path.join(folder_path, html_file), 'r', encoding='utf-8') as f:
            html_content = f.read()

        post_info = extract_post_info(html_content, post_id)
        print(f"\n[{i}/{total}] 글 #{post_id}: {post_info['title'][:40]}...")

        # 1. 이미지 업로드
        image_url_map = {}
        img_dir = os.path.join(folder_path, 'img')
        if os.path.isdir(img_dir):
            for img_file in sorted(os.listdir(img_dir)):
                if img_file.startswith('.'):
                    continue
                img_path = os.path.join(img_dir, img_file)
                wp_url, media_id = upload_image(img_path, post_id, headers)
                if wp_url:
                    image_url_map[img_file] = wp_url
                    print(f"  이미지: {img_file} → 업로드 완료")
                else:
                    print(f"  이미지: {img_file} → 업로드 실패!")

        # 2. 콘텐츠 정리
        content = clean_content_for_wp(post_info['content'], post_id, image_url_map)

        # 3. 카테고리 처리
        category_ids = []
        if post_info['category']:
            parts = post_info['category'].split('/')
            parent_id = None
            for part in parts:
                cat_id = get_or_create_category(part.strip(), parent_id, headers, cat_cache)
                if cat_id:
                    category_ids.append(cat_id)
                    parent_id = cat_id

        # 4. 태그 처리
        tag_ids = []
        for tag_name in post_info['tags']:
            tag_id = get_or_create_tag(tag_name, headers, tag_cache)
            if tag_id:
                tag_ids.append(tag_id)

        # 5. 글 생성
        post_data = {
            "title": post_info['title'],
            "content": content,
            "status": "publish",
            "slug": str(post_id),  # 슬러그 = 티스토리 번호
            "date": post_info['date'].replace(' ', 'T'),
            "categories": category_ids,
            "tags": tag_ids,
        }

        result = api_request("POST", "posts", headers, data=post_data)
        if result:
            success += 1
            wp_id = result['id']
            print(f"  → 글 생성 완료 (WP ID: {wp_id}, 슬러그: /{post_id}/)")
        else:
            errors.append(f"글 #{post_id}: 생성 실패")
            print(f"  → 글 생성 실패!")

        # API 속도 제한 방지
        time.sleep(0.3)

    print("\n" + "=" * 60)
    print("업로드 결과")
    print("=" * 60)
    print(f"  성공: {success}/{total}")
    if errors:
        print(f"  실패: {len(errors)}건")
        for err in errors:
            print(f"    - {err}")

    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
마지막 단계: 고유주소(Permalink) 설정
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  워드프레스 관리자 → 설정 → 고유주소
  → '글 이름' (/%postname%/) 선택 → 변경사항 저장

  이렇게 하면:
    your-blog.tistory.com/135  →  your-site.com/135/
    your-blog.tistory.com/20   →  your-site.com/20/
  동일한 번호 체계로 URL이 작동합니다!
""")


def main():
    if len(sys.argv) < 2:
        print("""
워드프레스 관리 스크립트
========================

사용법:
  python3 wp_manage.py --delete-all    기존 콘텐츠 전체 삭제
  python3 wp_manage.py --upload        티스토리 글/이미지 업로드
  python3 wp_manage.py --all           삭제 → 업로드 한번에

사전 준비:
  1. 워드프레스 관리자 → 사용자 → 프로필
  2. '애플리케이션 비밀번호' 섹션에서 새 비밀번호 생성
  3. 이 스크립트 상단의 WP_APP_PASSWORD에 입력
     (또는 실행 시 입력 프롬프트에서 입력)
""")
        return

    headers = get_credentials()

    # API 연결 테스트
    print("워드프레스 API 연결 테스트 중...")
    try:
        url = f"{API}/users/me"
        req = Request(url)
        for k, v in headers.items():
            req.add_header(k, v)
        with urlopen(req) as resp:
            user = json.loads(resp.read().decode('utf-8'))
        print(f"  → 연결 성공! 사용자: {user.get('name', 'unknown')}")
    except HTTPError as e:
        print(f"  → 연결 실패! (HTTP {e.code})")
        print("  → 사용자명과 애플리케이션 비밀번호를 확인하세요.")
        return

    if sys.argv[1] in ("--delete-all", "--all"):
        if "--force" not in sys.argv:
            confirm = input("\n⚠ 기존 워드프레스 콘텐츠를 전부 삭제합니다. 계속하시겠습니까? (yes/no): ")
            if confirm.lower() != 'yes':
                print("취소되었습니다.")
                return
        delete_all_content(headers)

    if sys.argv[1] in ("--upload", "--all"):
        upload_all(headers)


if __name__ == '__main__':
    main()
