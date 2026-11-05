#!/bin/sh
# Dev object storage (SeaweedFS, S3-compatible). Renders the S3 identity file from env so
# credentials stay in .env, then starts master+volume+filer+S3 in one process.
set -eu
: "${S3_ACCESS_KEY_ID:?}" "${S3_SECRET_ACCESS_KEY:?}" "${S3_BUCKET:?}"
mkdir -p /data /etc/seaweedfs
sed -e "s|\${S3_ACCESS_KEY_ID}|${S3_ACCESS_KEY_ID}|g" \
    -e "s|\${S3_SECRET_ACCESS_KEY}|${S3_SECRET_ACCESS_KEY}|g" \
    -e "s|\${S3_BUCKET}|${S3_BUCKET}|g" \
    /templates/s3.json.template > /etc/seaweedfs/s3.json
exec weed server -dir=/data -ip=objectstore -ip.bind=0.0.0.0 -volume.max=8 \
  -master.volumeSizeLimitMB=256 -s3 -s3.port=8333 -s3.config=/etc/seaweedfs/s3.json
