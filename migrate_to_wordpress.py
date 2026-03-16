#!/usr/bin/env python3
"""
티스토리 → 워드프레스 마이그레이션 스크립트

기능:
1. 티스토리 백업 HTML 파일 파싱 (제목, 날짜, 카테고리, 태그, 본문)
2. 내부 링크 your-blog.tistory.com → your-site.com 변환
3. OG 카드 블록 → 심플 링크 변환
4. 이미지 경로 → 워드프레스 업로드 경로로 변환
5. WordPress WXR (eXtended RSS) XML 파일 생성
"""

import os
import re
import html
from pathlib import Path
from datetime import datetime
from email.utils import format_datetime
from bs4 import BeautifulSoup

# ─── 설정 ───────────────────────────────────────────────
BACKUP_DIR = "./your-tistory-backup"              # 티스토리 백업 폴더 경로
OUTPUT_FILE = "./wordpress-import.xml"             # 출력 WXR 파일 경로
OLD_DOMAIN = "your-blog.tistory.com"               # 원본 티스토리 도메인
NEW_DOMAIN = "your-site.com"                       # 새 워드프레스 도메인
IMAGE_BASE_URL = f"https://{NEW_DOMAIN}/wp-content/uploads/tistory"
AUTHOR_LOGIN = "admin"                             # 워드프레스 사용자명
AUTHOR_DISPLAY = "Your Name"                       # 표시될 작성자 이름
# ────────────────────────────────────────────────────────


def build_post_mapping(backup_dir):
    """티스토리 글 ID 목록 구축. 슬러그는 티스토리 번호 그대로 사용."""
    mapping = {}
    for folder in os.listdir(backup_dir):
        folder_path = os.path.join(backup_dir, folder)
        if not os.path.isdir(folder_path) or not folder.isdigit():
            continue
        post_id = int(folder)
        # 슬러그 = 티스토리 글 번호 (your-blog.tistory.com/135 → your-site.com/135/)
        mapping[post_id] = str(post_id)
    return mapping


def extract_post_info(html_content, post_id, filename):
    """HTML에서 제목, 날짜, 카테고리, 태그, 본문 추출."""
    soup = BeautifulSoup(html_content, 'html.parser')

    # 제목
    title_el = soup.find('h2', class_='title-article')
    title = title_el.get_text(strip=True) if title_el else "Untitled"

    # 날짜
    date_el = soup.find('p', class_='date')
    date_str = date_el.get_text(strip=True) if date_el else "2020-01-01 00:00:00"

    # 카테고리
    cat_el = soup.find('p', class_='category')
    category = cat_el.get_text(strip=True) if cat_el else ""

    # 태그
    tags_el = soup.find('div', class_='tags')
    tags = []
    if tags_el:
        tag_text = tags_el.get_text(strip=True)
        tags = [t.strip() for t in tag_text.split('#') if t.strip()]

    # 본문 (contents_style div 내부)
    content_el = soup.find('div', class_='contents_style')
    content = str(content_el) if content_el else ""
    # contents_style div 태그 자체를 제거하고 내부만 추출
    if content_el:
        content = content_el.decode_contents().strip()

    # 슬러그 = 티스토리 번호 그대로 (your-site.com/135/ 형태)
    slug = str(post_id)

    return {
        'id': post_id,
        'title': title,
        'date': date_str,
        'category': category,
        'tags': tags,
        'content': content,
        'slug': slug,
    }


def replace_internal_links(content, post_mapping):
    """your-blog.tistory.com/{id} → your-site.com/{id}/ 로 변환 (티스토리 번호 유지)."""
    def replace_link(match):
        post_id = int(match.group(1))
        return f"https://{NEW_DOMAIN}/{post_id}/"

    # https:// 또는 http:// 포함된 링크 (?category= 등 쿼리 파라미터 제거)
    content = re.sub(
        r'https?://your-blog\.tistory\.com/(\d+)(?:\?[^"<\s]*)?',
        replace_link,
        content
    )
    # 프로토콜 없이 도메인만 있는 텍스트 (앵커 텍스트 등)
    content = re.sub(
        r'(?<!/)your-blog\.tistory\.com/(\d+)(?:\?[^"<\s]*)?',
        replace_link,
        content
    )
    return content


def convert_og_cards(content):
    """OG 카드 블록 → 심플 링크로 변환."""
    soup = BeautifulSoup(content, 'html.parser')
    og_figures = soup.find_all('figure', attrs={'data-ke-type': 'opengraph'})

    for fig in og_figures:
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

    return str(soup)


def convert_hr_figures(content):
    """티스토리 가로줄 figure → 단순 <hr> 변환."""
    content = re.sub(
        r'<figure[^>]*data-ke-type="horizontalRule"[^>]*>.*?</figure>',
        '<hr/>',
        content, flags=re.DOTALL
    )
    return content


def fix_image_paths(content, post_id):
    """상대 이미지 경로 → 워드프레스 업로드 경로로 변환."""
    content = content.replace('./img/', f'{IMAGE_BASE_URL}/{post_id}/')
    return content


def clean_og_host_text(content):
    """og-host 텍스트 제거 (변환 후 잔여물)."""
    content = re.sub(r'<p class="og-host">.*?</p>', '', content, flags=re.DOTALL)
    return content


def clean_content(content, post_id, post_mapping):
    """본문 정리: OG카드 변환, 링크 변환, 이미지 경로 변환."""
    content = convert_og_cards(content)
    content = convert_hr_figures(content)
    content = replace_internal_links(content, post_mapping)
    content = fix_image_paths(content, post_id)
    content = clean_og_host_text(content)
    return content.strip()


def parse_categories(categories_set):
    """카테고리 문자열 집합을 부모-자식 구조로 분리."""
    cat_list = []
    seen = set()

    for cat_str in sorted(categories_set):
        if not cat_str:
            continue
        parts = cat_str.split('/')
        # 부모 카테고리 등록
        parent = parts[0]
        if parent not in seen:
            cat_list.append({'name': parent, 'parent': '', 'nicename': parent})
            seen.add(parent)
        # 자식 카테고리 등록
        if len(parts) > 1:
            child = parts[1]
            full_name = f"{parent}/{child}"
            if full_name not in seen:
                cat_list.append({'name': child, 'parent': parent, 'nicename': child})
                seen.add(full_name)

    return cat_list


def date_to_rfc822(date_str):
    """'2020-12-24 17:27:58' → RFC 822 포맷."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        return format_datetime(dt)
    except ValueError:
        return date_str


def xml_cdata(text):
    """CDATA 블록 생성."""
    return f"<![CDATA[{text}]]>"


def generate_wxr(posts, categories):
    """WordPress WXR 1.2 XML 생성."""
    cat_items = parse_categories(categories)

    # WXR 헤더
    wxr = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0"
    xmlns:excerpt="http://wordpress.org/export/1.2/excerpt/"
    xmlns:content="http://purl.org/rss/1.0/modules/content/"
    xmlns:wfw="http://wellformedweb.org/CommentAPI/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:wp="http://wordpress.org/export/1.2/">
<channel>
    <title>My Blog</title>
    <link>https://{NEW_DOMAIN}</link>
    <description>티스토리에서 워드프레스로 이전된 블로그</description>
    <language>ko</language>
    <wp:wxr_version>1.2</wp:wxr_version>
    <wp:base_site_url>https://{NEW_DOMAIN}</wp:base_site_url>
    <wp:base_blog_url>https://{NEW_DOMAIN}</wp:base_blog_url>

    <wp:author>
        <wp:author_id>1</wp:author_id>
        <wp:author_login>{xml_cdata(AUTHOR_LOGIN)}</wp:author_login>
        <wp:author_email>{xml_cdata("admin@" + NEW_DOMAIN)}</wp:author_email>
        <wp:author_display_name>{xml_cdata(AUTHOR_DISPLAY)}</wp:author_display_name>
    </wp:author>

"""

    # 카테고리 정의
    for i, cat in enumerate(cat_items, start=1):
        wxr += f"""    <wp:category>
        <wp:term_id>{i}</wp:term_id>
        <wp:category_nicename>{xml_cdata(cat['nicename'])}</wp:category_nicename>
        <wp:category_parent>{xml_cdata(cat['parent'])}</wp:category_parent>
        <wp:cat_name>{xml_cdata(cat['name'])}</wp:cat_name>
    </wp:category>
"""

    # 각 글 (item)
    for post in sorted(posts, key=lambda p: p['id']):
        rfc_date = date_to_rfc822(post['date'])

        # 카테고리 (부모/자식 구조 처리)
        cat_xml = ""
        if post['category']:
            parts = post['category'].split('/')
            for part in parts:
                nicename = part.strip()
                cat_xml += f'        <category domain="category" nicename="{html.escape(nicename)}">{xml_cdata(nicename)}</category>\n'

        # 태그
        tag_xml = ""
        for tag in post['tags']:
            tag_xml += f'        <category domain="post_tag" nicename="{html.escape(tag)}">{xml_cdata(tag)}</category>\n'

        wxr += f"""    <item>
        <title>{xml_cdata(post['title'])}</title>
        <link>https://{NEW_DOMAIN}/{post['slug']}/</link>
        <pubDate>{rfc_date}</pubDate>
        <dc:creator>{xml_cdata(AUTHOR_LOGIN)}</dc:creator>
        <description></description>
        <content:encoded>{xml_cdata(post['content'])}</content:encoded>
        <excerpt:encoded>{xml_cdata("")}</excerpt:encoded>
        <wp:post_id>{post['id']}</wp:post_id>
        <wp:post_date>{xml_cdata(post['date'])}</wp:post_date>
        <wp:post_date_gmt>{xml_cdata(post['date'])}</wp:post_date_gmt>
        <wp:post_modified>{xml_cdata(post['date'])}</wp:post_modified>
        <wp:post_modified_gmt>{xml_cdata(post['date'])}</wp:post_modified_gmt>
        <wp:comment_status>{xml_cdata("open")}</wp:comment_status>
        <wp:ping_status>{xml_cdata("open")}</wp:ping_status>
        <wp:post_name>{xml_cdata(post['slug'])}</wp:post_name>
        <wp:status>{xml_cdata("publish")}</wp:status>
        <wp:post_parent>0</wp:post_parent>
        <wp:menu_order>0</wp:menu_order>
        <wp:post_type>{xml_cdata("post")}</wp:post_type>
        <wp:post_password>{xml_cdata("")}</wp:post_password>
        <wp:is_sticky>0</wp:is_sticky>
{cat_xml}{tag_xml}    </item>
"""

    wxr += """</channel>
</rss>
"""
    return wxr


def count_images(backup_dir):
    """이미지 총 개수 세기."""
    count = 0
    for folder in os.listdir(backup_dir):
        img_dir = os.path.join(backup_dir, folder, 'img')
        if os.path.isdir(img_dir):
            count += len([f for f in os.listdir(img_dir) if not f.startswith('.')])
    return count


def main():
    print("=" * 60)
    print("티스토리 → 워드프레스 마이그레이션")
    print("=" * 60)

    # 1단계: 글 ID → 슬러그 매핑 구축
    print("\n[1/4] 글 ID → 슬러그 매핑 구축 중...")
    post_mapping = build_post_mapping(BACKUP_DIR)
    print(f"  → {len(post_mapping)}개 글 매핑 완료")

    # 2단계: HTML 파일 파싱
    print("\n[2/4] HTML 파일 파싱 중...")
    posts = []
    categories = set()
    errors = []

    folders = sorted(
        [f for f in os.listdir(BACKUP_DIR)
         if os.path.isdir(os.path.join(BACKUP_DIR, f)) and f.isdigit()],
        key=int
    )

    for folder in folders:
        folder_path = os.path.join(BACKUP_DIR, folder)
        post_id = int(folder)

        html_files = [f for f in os.listdir(folder_path) if f.endswith('.html')]
        if not html_files:
            errors.append(f"폴더 {folder}: HTML 파일 없음")
            continue

        html_file = html_files[0]
        filepath = os.path.join(folder_path, html_file)

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                html_content = f.read()

            post_info = extract_post_info(html_content, post_id, html_file)
            posts.append(post_info)

            if post_info['category']:
                categories.add(post_info['category'])
                # 부모 카테고리도 추가
                parts = post_info['category'].split('/')
                if len(parts) > 1:
                    categories.add(parts[0])

        except Exception as e:
            errors.append(f"폴더 {folder}: {str(e)}")

    print(f"  → {len(posts)}개 글 파싱 완료")
    if errors:
        print(f"  ⚠ {len(errors)}개 오류:")
        for err in errors:
            print(f"    - {err}")

    # 3단계: 콘텐츠 변환
    print("\n[3/4] 콘텐츠 변환 중 (링크, 이미지, OG카드)...")
    link_replacements = 0
    for post in posts:
        original = post['content']
        post['content'] = clean_content(post['content'], post['id'], post_mapping)
        # 변환된 링크 수 대략 세기
        link_replacements += len(re.findall(
            rf'https://{re.escape(NEW_DOMAIN)}/[^/]+/',
            post['content']
        ))

    print(f"  → 내부 링크 약 {link_replacements}건 변환")

    # 4단계: WXR XML 생성
    print("\n[4/4] WXR XML 파일 생성 중...")
    wxr_content = generate_wxr(posts, categories)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(wxr_content)

    file_size = os.path.getsize(OUTPUT_FILE) / 1024
    print(f"  → {OUTPUT_FILE}")
    print(f"  → 파일 크기: {file_size:.1f} KB")

    # 요약
    img_count = count_images(BACKUP_DIR)
    print("\n" + "=" * 60)
    print("마이그레이션 요약")
    print("=" * 60)
    print(f"  총 글 수: {len(posts)}개")
    print(f"  카테고리: {len(categories)}개")
    all_tags = set()
    for p in posts:
        all_tags.update(p['tags'])
    print(f"  태그: {len(all_tags)}개")
    print(f"  이미지: {img_count}개")
    print(f"  출력 파일: {OUTPUT_FILE}")

    print("\n" + "=" * 60)
    print("다음 단계")
    print("=" * 60)
    print(f"""
1. 워드프레스 설정:
   - your-site.com에 워드프레스 설치
   - 고유주소(Permalink)를 /%postname%/ 으로 설정

2. WXR 파일 가져오기:
   - 워드프레스 관리자 → 도구 → 가져오기 → WordPress
   - {OUTPUT_FILE} 파일 업로드
   - "첨부 파일 다운로드 및 가져오기" 체크 해제

3. 이미지 업로드:
   - 서버의 wp-content/uploads/tistory/ 폴더에 이미지 업로드
   - 명령어 (SSH/SCP 사용 시):
     scp -r {BACKUP_DIR}/*/img/ user@서버:/path/to/wordpress/wp-content/uploads/tistory/
   - 또는 아래의 이미지 업로드 스크립트 사용

4. 이미지 폴더 구조:
   wp-content/uploads/tistory/
   ├── 2/         ← 글 ID
   │   ├── img.jpg
   │   └── img_1.jpg
   ├── 3/
   │   ├── img.jpg
   │   └── img_1.png
   └── ...
""")


if __name__ == '__main__':
    main()
