# Kubernetes Deployment for Ringmaster

This directory contains Kubernetes manifests for deploying Ringmaster to a Kubernetes cluster.

## Prerequisites

- Kubernetes cluster (v1.24+)
- kubectl configured
- NGINX Ingress Controller (optional, for Ingress)
- cert-manager (optional, for TLS)

## Quick Start

### Deploy to cluster

```bash
kubectl apply -k k8s/base
```

### Check deployment status

```bash
kubectl get pods -n ringmaster
kubectl get svc -n ringmaster
```

### View logs

```bash
# API logs
kubectl logs -f deployment/ringmaster-api -n ringmaster

# Scheduler logs
kubectl logs -f deployment/ringmaster-scheduler -n ringmaster
```

## Architecture

The deployment includes:

- **ringmaster-api**: FastAPI server handling HTTP requests and WebSocket connections
- **ringmaster-scheduler**: Background scheduler for task assignment and worker management
- **Services**: ClusterIP services for internal communication
- **Ingress**: External access (configure host in ingress.yaml)
- **PVCs**: Persistent storage for database, logs, and project code

## Storage

- **ringmaster-data-pvc** (5Gi): SQLite database storage
- **ringmaster-logs-pvc** (2Gi): Application logs
- **ringmaster-projects-pvc** (20Gi): Shared project code for workers

## Scaling

### Scale API replicas

```bash
kubectl scale deployment ringmaster-api --replicas=3 -n ringmaster
```

Note: SQLite does not support multiple writers. For horizontal scaling, use PostgreSQL instead.

### Scale scheduler

The scheduler runs as a single replica. Multiple schedulers are not supported.

## Configuration

Edit `k8s/base/configmap.yaml` to configure:

- `RINGMASTER_LOG_LEVEL`: DEBUG, INFO, WARNING, ERROR
- `RINGMASTER_FRONTEND_DIST`: Path to frontend assets
- `RINGMASTER_OUTPUT_DIR`: Worker output directory

## Production Considerations

1. **Database**: Replace SQLite with PostgreSQL for production
2. **Image Registry**: Update image name in kustomization.yaml
3. **Ingress**: Configure host and TLS certificates
4. **Resource Limits**: Adjust CPU/memory based on workload
5. **Monitoring**: Add Prometheus scraping endpoints
6. **Secrets**: Use Kubernetes Secrets for sensitive data

## Upgrades

```bash
# Build and push new image
docker build -t ghcr.io/jedarden/ringmaster:v1.0.0 .
docker push ghcr.io/jedarden/ringmaster:v1.0.0

# Update deployment
kubectl set image deployment/ringmaster-api api=ghcr.io/jedarden/ringmaster:v1.0.0 -n ringmaster
kubectl set image deployment/ringmaster-scheduler scheduler=ghcr.io/jedarden/ringmaster:v1.0.0 -n ringmaster
```

## Troubleshooting

### Pod not starting

```bash
kubectl describe pod <pod-name> -n ringmaster
kubectl logs <pod-name> -n ringmaster
```

### Database locked

SQLite has limited concurrency. For production, switch to PostgreSQL.

### Worker output missing

Check PVC mounting and worker permissions on `/app/output`.
