#!/bin/bash
# =============================================================================
# fix_kfp_artifact_store.sh
# Fix permanent : redirige le KFP v2 Launcher de SeaweedFS → MinIO
#
# Problème : le KFP Launcher cherche seaweedfs.kubeflow:9000 (inexistant)
#            et le workflow-controller-configmap pointe sur
#            minio-service.kubeflow:9000 (mauvais namespace, MinIO est dans default)
#
# Solution : 1) Service "seaweedfs"    → alias DNS vers MinIO (default)
#            2) Service "minio-service" → alias DNS vers MinIO (default)
#            3) Patch workflow-controller-configmap → bon endpoint
#            4) Secret mlpipeline-minio-artifact dans kubeflow
#            5) Bucket mlpipeline dans MinIO
# =============================================================================

set -e

MINIO_ENDPOINT="minio-service.default.svc.cluster.local"
MINIO_PORT="9000"
MINIO_ACCESS_KEY="minioadmin"
MINIO_SECRET_KEY="minioadmin"
BUCKET="mlpipeline"

echo "======================================================================"
echo "  KFP Artifact Store — Fix permanent (SeaweedFS → MinIO)"
echo "======================================================================"

# ── 1. Service alias "seaweedfs" dans kubeflow → MinIO ────────────────────
echo ""
echo "[1/5] Création du Service 'seaweedfs' (alias DNS → MinIO)..."
kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: seaweedfs
  namespace: kubeflow
  labels:
    app: seaweedfs-minio-alias
  annotations:
    description: "Alias DNS permanent : seaweedfs.kubeflow:9000 → MinIO (default)"
spec:
  type: ExternalName
  externalName: ${MINIO_ENDPOINT}
  ports:
  - name: s3
    port: ${MINIO_PORT}
    targetPort: ${MINIO_PORT}
    protocol: TCP
EOF
echo "  ✓ seaweedfs.kubeflow:9000 → ${MINIO_ENDPOINT}:${MINIO_PORT}"

# ── 2. Service alias "minio-service" dans kubeflow → MinIO ────────────────
echo ""
echo "[2/5] Création du Service 'minio-service' dans kubeflow (alias DNS)..."
kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: minio-service
  namespace: kubeflow
  labels:
    app: minio-kubeflow-alias
  annotations:
    description: "Alias DNS : minio-service.kubeflow:9000 → MinIO (default)"
spec:
  type: ExternalName
  externalName: ${MINIO_ENDPOINT}
  ports:
  - name: s3
    port: ${MINIO_PORT}
    targetPort: ${MINIO_PORT}
    protocol: TCP
EOF
echo "  ✓ minio-service.kubeflow:9000 → ${MINIO_ENDPOINT}:${MINIO_PORT}"

# ── 3. Secret mlpipeline-minio-artifact dans kubeflow ─────────────────────
echo ""
echo "[3/5] Création/mise à jour du Secret 'mlpipeline-minio-artifact'..."
kubectl create secret generic mlpipeline-minio-artifact \
  --from-literal=accesskey="${MINIO_ACCESS_KEY}" \
  --from-literal=secretkey="${MINIO_SECRET_KEY}" \
  -n kubeflow \
  --dry-run=client -o yaml | kubectl apply -f -
echo "  ✓ Secret prêt"

# ── 4. Patch workflow-controller-configmap ────────────────────────────────
echo ""
echo "[4/5] Patch du workflow-controller-configmap..."
kubectl patch configmap workflow-controller-configmap -n kubeflow --type=merge -p "$(cat <<PATCH
{
  "data": {
    "artifactRepository": "archiveLogs: true\ns3:\n  endpoint: \"seaweedfs.kubeflow:9000\"\n  bucket: \"${BUCKET}\"\n  keyFormat: \"v2/artifacts/{{workflow.name}}/{{pod.name}}\"\n  insecure: true\n  accessKeySecret:\n    name: mlpipeline-minio-artifact\n    key: accesskey\n  secretKeySecret:\n    name: mlpipeline-minio-artifact\n    key: secretkey\n"
  }
}
PATCH
)"
echo "  ✓ workflow-controller-configmap patché"

# ── 5. Bucket mlpipeline dans MinIO ───────────────────────────────────────
echo ""
echo "[5/5] Création du bucket '${BUCKET}' dans MinIO (si absent)..."
kubectl run mc-fix --rm -it \
  --image=minio/mc \
  --restart=Never \
  --timeout=60s \
  -- bash -c "
    mc alias set minio http://${MINIO_ENDPOINT}:${MINIO_PORT} ${MINIO_ACCESS_KEY} ${MINIO_SECRET_KEY} --api S3v4 && \
    mc mb --ignore-existing minio/${BUCKET} && \
    echo '  Bucket OK' && \
    mc ls minio/
  " 2>/dev/null || echo "  (mc pod terminé — vérifiez manuellement si nécessaire)"

# ── Restart workflow-controller ───────────────────────────────────────────
echo ""
echo "[+] Redémarrage du workflow-controller..."
kubectl rollout restart deployment workflow-controller -n kubeflow
kubectl rollout status deployment workflow-controller -n kubeflow --timeout=60s

# ── Vérification finale ───────────────────────────────────────────────────
echo ""
echo "======================================================================"
echo "  Vérification finale"
echo "======================================================================"
echo ""
echo "Services créés dans kubeflow :"
kubectl get service -n kubeflow | grep -E "seaweedfs|minio"
echo ""
echo "Secret :"
kubectl get secret mlpipeline-minio-artifact -n kubeflow -o jsonpath='{.data}' | python3 -c "
import sys, json, base64
d = json.load(sys.stdin)
for k,v in d.items(): print(f'  {k}: {base64.b64decode(v).decode()}')
"
echo ""
echo "======================================================================"
echo "  ✅ FIX PERMANENT APPLIQUÉ"
echo ""
echo "  seaweedfs.kubeflow:9000  → MinIO (${MINIO_ENDPOINT})"
echo "  minio-service.kubeflow:9000 → MinIO (${MINIO_ENDPOINT})"
echo ""
echo "  Relancez votre pipeline Kubeflow — l'erreur executor-logs"
echo "  ne se reproduira plus."
echo "======================================================================"
