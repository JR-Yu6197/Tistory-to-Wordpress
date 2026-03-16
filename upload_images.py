#!/usr/bin/env python3
"""
이미지 업로드 보조 스크립트

티스토리 백업 이미지를 서버의 wp-content/uploads/tistory/ 경로에
맞는 폴더 구조로 복사합니다.

사용법 1 - 로컬에서 구조 맞춰 복사 후 FTP/SCP 업로드:
  python3 upload_images.py --prepare

사용법 2 - SCP로 직접 서버에 업로드:
  python3 upload_images.py --scp user@your-site.com:/var/www/html/wp-content/uploads/
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

BACKUP_DIR = "./your-tistory-backup"      # 티스토리 백업 폴더 경로
OUTPUT_DIR = "./tistory-images"           # 출력 폴더


def prepare_images():
    """이미지를 워드프레스 업로드 구조로 복사."""
    print("이미지를 워드프레스 업로드 구조로 복사 중...")

    dest_base = os.path.join(OUTPUT_DIR, "tistory")
    os.makedirs(dest_base, exist_ok=True)

    total = 0
    for folder in sorted(os.listdir(BACKUP_DIR)):
        src_img_dir = os.path.join(BACKUP_DIR, folder, "img")
        if not os.path.isdir(src_img_dir):
            continue

        dest_dir = os.path.join(dest_base, folder)
        os.makedirs(dest_dir, exist_ok=True)

        for img_file in os.listdir(src_img_dir):
            if img_file.startswith('.'):
                continue
            src = os.path.join(src_img_dir, img_file)
            dst = os.path.join(dest_dir, img_file)
            shutil.copy2(src, dst)
            total += 1

    print(f"완료! {total}개 이미지 → {dest_base}/")
    print(f"\n이 폴더를 서버의 wp-content/uploads/ 아래에 업로드하세요.")
    print(f"  scp -r {dest_base} user@your-site.com:/path/to/wp-content/uploads/")


def scp_upload(destination):
    """SCP로 서버에 직접 업로드."""
    prepare_images()

    src = os.path.join(OUTPUT_DIR, "tistory")
    print(f"\nSCP 업로드 중: {src} → {destination}")

    result = subprocess.run(
        ["scp", "-r", src, destination],
        capture_output=False
    )

    if result.returncode == 0:
        print("업로드 완료!")
    else:
        print(f"업로드 실패 (코드: {result.returncode})")


def main():
    if len(sys.argv) < 2:
        print("사용법:")
        print("  python3 upload_images.py --prepare")
        print("  python3 upload_images.py --scp user@server:/path/to/wp-content/uploads/")
        return

    if sys.argv[1] == "--prepare":
        prepare_images()
    elif sys.argv[1] == "--scp" and len(sys.argv) >= 3:
        scp_upload(sys.argv[2])
    else:
        print("잘못된 옵션입니다.")


if __name__ == '__main__':
    main()
