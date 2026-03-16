# Tistory to WordPress Migration Tool

티스토리 블로그를 워드프레스로 완벽하게 이전하는 마이그레이션 도구입니다.

글, 이미지, 카테고리, 태그, 내부 링크를 자동 변환하고 티스토리 스타일의 UI까지 워드프레스에 적용합니다.

## Demo

| Before (Tistory) | After (WordPress) |
|---|---|
| https://jr-drew.tistory.com/ | https://jrdrew.xyz |

## Features

- 티스토리 백업 HTML 파싱 (제목, 날짜, 카테고리, 태그, 본문)
- WordPress REST API를 통한 고속 업로드 (이미지 병렬 10스레드)
- 내부 링크 자동 변환 (`your-blog.tistory.com/135` → `your-site.com/135-2/`)
- OG 카드 블록 → WordPress embed 블록 변환
- 대표 이미지(Featured Image) 자동 설정
- 티스토리 스타일 UI (햄버거 메뉴, 슬라이드 사이드바, 검색)
- 이미지 클릭 시 라이트박스(확대) 기능
- 반응형 디자인

## Requirements

```
Python 3.10+
pip install requests beautifulsoup4
```

워드프레스 요구사항:
- WordPress 6.0+ (REST API 지원)
- 애플리케이션 비밀번호 활성화 (사용자 → 프로필에서 생성)

## Quick Start

### 1. 티스토리 백업 다운로드

티스토리 관리자 → 블로그 → 데이터 관리 → 백업에서 백업 파일을 다운로드합니다.

백업 폴더 구조:
```
your-backup/
├── 2/
│   ├── 2-인사동-거리-걸어보기.html
│   └── img/
│       ├── img.jpg
│       └── img_1.jpg
├── 3/
│   ├── 3-시크릿-위치.html
│   └── img/
├── ...
└── style.css
```

### 2. 스크립트 설정

`wp_upload.py` 상단의 설정값을 수정합니다:

```python
WP_URL = "https://your-site.com"        # 워드프레스 주소
WP_USER = "your_username"               # 워드프레스 사용자명
WP_APP_PASSWORD = "xxxx xxxx xxxx xxxx" # 애플리케이션 비밀번호
BACKUP_DIR = "/path/to/your-backup"     # 티스토리 백업 폴더 경로
```

애플리케이션 비밀번호는 워드프레스 관리자 → 사용자 → 프로필 → 애플리케이션 비밀번호에서 생성합니다.

### 3. 워드프레스 설정

```
설정 → 고유주소 → "글 이름" (/%postname%/) 선택 → 저장
```

### 4. 기존 콘텐츠 삭제 (필요시)

```bash
# wp_manage.py 설정 수정 후:
python3 wp_manage.py --delete-all
```

### 5. 업로드 실행

```bash
python3 wp_upload.py
```

136개 글 + 433개 이미지 기준 약 10분 소요됩니다.

### 6. 티스토리 스타일 UI 적용 (선택)

#### 플러그인 설치

워드프레스 관리자 → 플러그인 → 새로 추가에서 **WPCode (Insert Headers and Footers)** 설치 및 활성화

#### CSS/JS 적용

관리자 → Code Snippets → Header & Footer에서:

| 위치 | 파일 | 설명 |
|------|------|------|
| **Header** | [`HEADER-PASTE-THIS.txt`](HEADER-PASTE-THIS.txt) | CSS (폰트, 레이아웃, 사이드바, 라이트박스) |
| **Footer** | [`FOOTER-PASTE-THIS.txt`](FOOTER-PASTE-THIS.txt) | JS (사이드바 토글, 검색, 라이트박스) |

각 파일의 내용을 복사해서 해당 칸에 붙여넣고 저장합니다.

#### 홈페이지 템플릿 수정

`wp_upload.py` 실행 후 REST API로 홈 템플릿을 업데이트하면 티스토리 스타일의 글 목록 레이아웃이 적용됩니다. 상세 내용은 `README-personal.md`를 참고하세요.

## File Structure

```
├── README.md                 ← 이 파일 (가이드)
├── README-personal.md        ← 실제 마이그레이션 상세 기록
├── migrate_to_wordpress.py   ← HTML → WXR XML 변환 (대안 방식)
├── wp_upload.py              ← REST API 업로드 (권장 방식)
├── wp_manage.py              ← WP 콘텐츠 삭제/관리
├── upload_images.py          ← 이미지 폴더 구조 준비 (SCP용)
├── HEADER-PASTE-THIS.txt     ← 티스토리 스타일 CSS
├── FOOTER-PASTE-THIS.txt     ← 라이트박스 + 사이드바 JS
├── tistory-style.css         ← CSS 참고용
├── header-css-final.html     ← CSS 중간 버전 참고용
└── lightbox-widget.html      ← 라이트박스 JS 참고용
```

## How It Works

### 업로드 방식 (wp_upload.py, 권장)

WordPress REST API를 사용하여 직접 업로드합니다.

```
티스토리 HTML 파싱 → 이미지 병렬 업로드 → 콘텐츠 변환 → 글 생성
```

장점: 이미지가 워드프레스 미디어 라이브러리에 등록됨, 대표 이미지 자동 설정

### WXR 방식 (migrate_to_wordpress.py, 대안)

WordPress eXtended RSS(WXR) XML 파일을 생성하여 워드프레스 가져오기 도구로 임포트합니다.

```bash
python3 migrate_to_wordpress.py
# → wordpress-import.xml 생성
# → 관리자 → 도구 → 가져오기 → WordPress에서 업로드
```

장점: API 접근 불필요. 단점: 이미지를 별도로 업로드해야 함

## URL Mapping

WordPress는 순수 숫자 슬러그를 허용하지 않아 `-2` 접미사가 자동 추가됩니다.

```
tistory:   https://your-blog.tistory.com/135
wordpress: https://your-site.com/135-2/
```

숫자 슬러그를 허용하려면 테마의 `functions.php`에 추가:
```php
add_filter('wp_unique_post_slug_is_bad_flat_slug', '__return_false');
```

## Customization

### 사이드바 카테고리 수정

`HEADER-PASTE-THIS.txt`와 홈 템플릿의 카테고리 HTML을 본인 블로그에 맞게 수정하세요.

### SNS 링크 수정

홈 템플릿의 `.ts-sns` 영역에서 링크를 변경하세요.

### 색상/폰트 변경

`HEADER-PASTE-THIS.txt`의 CSS를 수정하세요:
- 메인 색상: `#333`
- 구분선: `rgba(51,51,51,.1)`
- 폰트: `Noto Sans`, `Noto Sans KR`

## Server Migration

워드프레스를 다른 서버로 이전할 경우:

1. **DB 백업**: `mysqldump -u [user] -p [dbname] > backup.sql`
2. **wp-content 복사**: 테마, 플러그인, 업로드 이미지 모두 포함
3. 새 서버에서 복원 후 `wp-config.php` DB 정보 수정

또는 **All-in-One WP Migration** 플러그인으로 원클릭 이전 가능

## License

MIT
