# Dockerfile for Camp Fitbitz Model Serving
# This Dockerfile packages the AI Chef's anomaly detection model for deployment
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir \
 mlflow==2.17.2 \
 scikit-learn==1.3.2 \
 pandas==2.1.4 \
 boto3==1.34.0
ENV MLFLOW_TRACKING_URI=http://mlflow-service:5000
ENV MLFLOW_S3_ENDPOINT_URL=http://minio-service:9000
ENV AWS_ACCESS_KEY_ID=minioadmin
ENV AWS_SECRET_ACCESS_KEY=minioadmin
EXPOSE 5001
CMD ["mlflow", "models", "serve", \
 "-m", "models:/log-clustering-kmeans/Production", \
 "-h", "0.0.0.0", \
 "-p", "5001", \
 "--env-manager=local"]
