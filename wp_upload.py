#!/usr/bin/env python3
"""티스토리 → 워드프레스 고속 업로드 (병렬 이미지 + 카드형 링크 + 라이트박스)"""

import os, re, json, time, base64, mimetypes
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from bs4 import BeautifulSoup

WP_URL = "https://your-site.com"          # 워드프레스 주소
WP_USER = "your_username"                 # 워드프레스 사용자명
WP_APP_PASSWORD = ""                      # 애플리케이션 비밀번호 (사용자→프로필에서 생성)
BACKUP_DIR = "./your-tistory-backup"      # 티스토리 백업 폴더 경로
API = f"{WP_URL}/wp-json/wp/v2"

SESSION = requests.Session()
SESSION.headers.update({
    "Authorization": f"Basic {base64.b64encode(f'{WP_USER}:{WP_APP_PASSWORD}'.encode()).decode()}"
})

IMAGE_WORKERS = 10


def api(method, endpoint, **kwargs):
    kwargs.setdefault('timeout', 120)
    try:
        resp = SESSION.request(method, f"{API}/{endpoint}", **kwargs)
        resp.raise_for_status()
        return resp.json()
    except requests.HTTPError as e:
        print(f"    ERR {e.response.status_code}: {e.response.text[:150]}")
        return None
    except Exception as e:
        print(f"    ERR: {e}")
        return None


# ─── 글 ID → 제목 매핑 (카드형 링크용) ────────────────
def build_title_map():
    mapping = {}
    for folder in os.listdir(BACKUP_DIR):
        fp = os.path.join(BACKUP_DIR, folder)
        if not os.path.isdir(fp) or not folder.isdigit():
            continue
        pid = int(folder)
        for f in os.listdir(fp):
            if f.endswith('.html'):
                with open(os.path.join(fp, f), 'r', encoding='utf-8') as fh:
                    html = fh.read()
                soup = BeautifulSoup(html, 'html.parser')
                te = soup.find('h2', class_='title-article')
                mapping[pid] = te.get_text(strip=True) if te else f"글 #{pid}"
                # 첫 이미지도 추출 (카드 썸네일용)
                img = soup.find('div', class_='contents_style')
                if img:
                    first_img = img.find('img')
                    if first_img and first_img.get('src'):
                        mapping[f"{pid}_img"] = first_img.get('data-filename', '')
                break
    return mapping


def extract_post(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    title = (soup.find('h2', class_='title-article') or type('X', (), {'get_text': lambda s, **k: 'Untitled'})()).get_text(strip=True)
    date = (soup.find('p', class_='date') or type('X', (), {'get_text': lambda s, **k: '2020-01-01 00:00:00'})()).get_text(strip=True)
    category = (soup.find('p', class_='category') or type('X', (), {'get_text': lambda s, **k: ''})()).get_text(strip=True)
    tags_el = soup.find('div', class_='tags')
    tags = [t.strip() for t in tags_el.get_text(strip=True).split('#') if t.strip()] if tags_el else []
    content_el = soup.find('div', class_='contents_style')
    content = content_el.decode_contents().strip() if content_el else ""
    return title, date, category, tags, content


def clean_content(content, post_id, image_map, title_map):
    soup = BeautifulSoup(content, 'html.parser')

    # OG 카드 → 워드프레스 카드형 링크 (wp:embed 블록)
    for fig in soup.find_all('figure', attrs={'data-ke-type': 'opengraph'}):
        og_title = fig.get('data-og-title', '')
        og_url = fig.get('data-og-url', '') or fig.get('data-og-source-url', '')
        og_desc = fig.get('data-og-description', '')

        if og_url:
            # 내부 링크인 경우 URL 변환
            m = re.search(r'your-blog\.tistory\.com/(\d+)', og_url)
            if m:
                pid = int(m.group(1))
                og_url = f"https://your-site.com/{pid}-2/"
                if not og_title and pid in title_map:
                    og_title = title_map[pid]

            # WordPress embed 블록 (카드형으로 표시됨)
            embed_html = f'\n<!-- wp:embed {{"url":"{og_url}","type":"rich","providerNameSlug":"wordpress"}} -->\n'
            embed_html += f'<figure class="wp-block-embed is-type-rich is-provider-wordpress wp-block-embed-wordpress">'
            embed_html += f'<div class="wp-block-embed__wrapper">\n{og_url}\n</div></figure>\n'
            embed_html += f'<!-- /wp:embed -->\n'

            new_tag = BeautifulSoup(embed_html, 'html.parser')
            fig.replace_with(new_tag)
        else:
            fig.decompose()

    content = str(soup)

    # 가로줄
    content = re.sub(r'<figure[^>]*data-ke-type="horizontalRule"[^>]*>.*?</figure>', '<hr/>', content, flags=re.DOTALL)

    # 내부 링크 URL 변환
    def repl(m):
        return f"https://your-site.com/{m.group(1)}-2/"
    content = re.sub(r'https?://your-blog\.tistory\.com/(\d+)(?:\?[^"<\s]*)?', repl, content)
    content = re.sub(r'(?<!/)your-blog\.tistory\.com/(\d+)(?:\?[^"<\s]*)?', repl, content)

    # 이미지: 라이트박스 + 적절한 사이즈
    for local_name, wp_url in image_map.items():
        # ./img/xxx → 클릭시 원본 열리는 링크 + 적절한 표시 사이즈
        old = f'./img/{local_name}'
        content = content.replace(old, wp_url)

    # 이미지에 라이트박스 기능 추가 (a 태그로 감싸기)
    soup2 = BeautifulSoup(content, 'html.parser')
    for img in soup2.find_all('img'):
        src = img.get('src', '')
        if not src or 'your-site.com' not in src:
            continue
        # 이미 a 태그 안에 있는지 확인
        parent = img.parent
        if parent and parent.name == 'a':
            continue
        # span[data-lightbox] 안에 있으면 그 span을 a로 교체
        if parent and parent.name == 'span' and parent.get('data-lightbox'):
            new_a = soup2.new_tag('a', href=src, **{'data-lightbox': 'gallery', 'target': '_blank'})
            img.extract()
            new_a.append(img)
            parent.replace_with(new_a)
        else:
            new_a = soup2.new_tag('a', href=src, **{'data-lightbox': 'gallery', 'target': '_blank'})
            img.replace_with(new_a)
            new_a.append(img)

    # 이미지 max-width 설정
    for img in soup2.find_all('img'):
        existing_style = img.get('style', '')
        img['style'] = f'{existing_style}; max-width: 100%; height: auto; cursor: zoom-in;'.strip('; ')
        # data-origin-width/height가 있으면 적절한 표시 사이즈
        ow = img.get('data-origin-width')
        if ow:
            try:
                w = min(int(ow), 700)
                img['width'] = str(w)
            except:
                pass

    content = str(soup2)

    # og-host 잔여물 제거
    content = re.sub(r'<p class="og-host">.*?</p>', '', content, flags=re.DOTALL)
    return content.strip()


def upload_image(filepath, post_id):
    fname = os.path.basename(filepath)
    ctype = mimetypes.guess_type(filepath)[0] or 'image/jpeg'
    wp_fname = f"tistory-{post_id}-{fname}"
    with open(filepath, 'rb') as f:
        result = api("POST", "media", files={"file": (wp_fname, f, ctype)})
    if result and 'source_url' in result:
        return fname, result['source_url']
    return fname, None


def upload_images_parallel(img_dir, post_id):
    image_map = {}
    if not os.path.isdir(img_dir):
        return image_map
    img_files = [f for f in sorted(os.listdir(img_dir)) if not f.startswith('.')]
    if not img_files:
        return image_map

    with ThreadPoolExecutor(max_workers=IMAGE_WORKERS) as pool:
        futs = {pool.submit(upload_image, os.path.join(img_dir, f), post_id): f for f in img_files}
        for fut in as_completed(futs):
            fname, wp_url = fut.result()
            if wp_url:
                image_map[fname] = wp_url
            else:
                print(f"  img FAIL: {fname}", flush=True)
    return image_map


def get_or_create(kind, name, extra=None):
    try:
        resp = SESSION.get(f"{API}/{kind}", params={"search": name, "per_page": 20}, timeout=30)
        for item in resp.json():
            if item['name'] == name:
                return item['id']
    except:
        pass
    data = {"name": name}
    if extra:
        data.update(extra)
    result = api("POST", kind, json=data)
    return result['id'] if result else None


def main():
    print("=" * 60)
    print("티스토리 → 워드프레스 고속 업로드")
    print("=" * 60, flush=True)

    print("\n제목 매핑 구축 중...", flush=True)
    title_map = build_title_map()
    print(f"  → {len([k for k in title_map if isinstance(k, int)])}개 글 매핑 완료", flush=True)

    cat_cache = {}
    tag_cache = {}

    folders = sorted(
        [f for f in os.listdir(BACKUP_DIR) if os.path.isdir(os.path.join(BACKUP_DIR, f)) and f.isdigit()],
        key=int
    )
    total = len(folders)
    success = 0
    errors = []
    start_time = time.time()

    for i, folder in enumerate(folders, 1):
        folder_path = os.path.join(BACKUP_DIR, folder)
        post_id = int(folder)

        html_files = [f for f in os.listdir(folder_path) if f.endswith('.html')]
        if not html_files:
            continue

        with open(os.path.join(folder_path, html_files[0]), 'r', encoding='utf-8') as f:
            html = f.read()

        title, date_str, category, tags, content = extract_post(html)
        elapsed = time.time() - start_time
        rate = i / elapsed if elapsed > 0 else 0
        eta = (total - i) / rate if rate > 0 else 0
        print(f"\n[{i}/{total}] #{post_id} {title[:35]}... (ETA: {eta:.0f}s)", flush=True)

        # 이미지 병렬 업로드
        img_dir = os.path.join(folder_path, 'img')
        image_map = upload_images_parallel(img_dir, post_id)
        if image_map:
            print(f"  이미지 {len(image_map)}개 업로드 완료", flush=True)

        # 콘텐츠 정리 (카드형 링크 + 라이트박스)
        content = clean_content(content, post_id, image_map, title_map)

        # 카테고리
        cat_ids = []
        if category:
            parts = category.split('/')
            parent_id = None
            for part in parts:
                key = f"{parent_id}:{part}"
                if key not in cat_cache:
                    extra = {"parent": parent_id} if parent_id else {}
                    cat_cache[key] = get_or_create("categories", part.strip(), extra)
                parent_id = cat_cache[key]
                if parent_id:
                    cat_ids.append(parent_id)

        # 태그
        tag_ids = []
        for tag in tags:
            if tag not in tag_cache:
                tag_cache[tag] = get_or_create("tags", tag)
            if tag_cache[tag]:
                tag_ids.append(tag_cache[tag])

        # 글 생성
        post_data = {
            "title": title,
            "content": content,
            "status": "publish",
            "slug": str(post_id),
            "date": date_str.replace(' ', 'T'),
            "categories": cat_ids,
            "tags": tag_ids,
        }
        result = api("POST", "posts", json=post_data)
        if result:
            success += 1
            print(f"  → /{result['slug']}/ OK", flush=True)
        else:
            errors.append(f"#{post_id}")
            print(f"  → FAIL!", flush=True)

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"완료! {success}/{total} 성공 ({elapsed:.0f}초 소요)")
    if errors:
        print(f"실패: {', '.join(errors)}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
