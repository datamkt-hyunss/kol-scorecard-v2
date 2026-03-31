#!/bin/bash
# Playwright 브라우저 자동 설치 (Streamlit Cloud 배포 시 실행)
python -m playwright install chromium
python -m playwright install-deps chromium
