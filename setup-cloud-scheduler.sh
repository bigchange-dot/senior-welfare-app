#!/bin/bash
# Cloud Scheduler 설정 스크립트
# 실행 전: gcloud auth login && gcloud config set project senior-welfare-app
# 실행: bash setup-cloud-scheduler.sh

PROJECT_ID="senior-welfare-app"
REGION="asia-northeast3"
FUNCTION_URL="https://${REGION}-${PROJECT_ID}.cloudfunctions.net/scraping_function"

echo "🔧 Cloud Scheduler 작업 등록 중..."

# 오전 9시 KST
gcloud scheduler jobs create http scraping-morning \
  --location="${REGION}" \
  --schedule="0 9 * * *" \
  --time-zone="Asia/Seoul" \
  --uri="${FUNCTION_URL}" \
  --http-method=POST \
  --message-body='{"trigger":"scheduler"}' \
  --headers="Content-Type=application/json" \
  --attempt-deadline=600s \
  --description="노인복지 공고 수집 — 오전 9시 (KST)"

echo "✅ 오전 9시 스케줄러 등록 완료"

# 오후 6시 KST
gcloud scheduler jobs create http scraping-evening \
  --location="${REGION}" \
  --schedule="0 18 * * *" \
  --time-zone="Asia/Seoul" \
  --uri="${FUNCTION_URL}" \
  --http-method=POST \
  --message-body='{"trigger":"scheduler"}' \
  --headers="Content-Type=application/json" \
  --attempt-deadline=600s \
  --description="노인복지 공고 수집 — 오후 6시 (KST)"

echo "✅ 오후 6시 스케줄러 등록 완료"
echo ""
echo "📋 등록된 스케줄러 확인:"
gcloud scheduler jobs list --location="${REGION}"
