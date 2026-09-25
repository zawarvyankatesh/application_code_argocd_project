# Orbit Taskboard

Small CRUD app for the CodeBuild → ECR → Helm → Argo CD lab. This repo currently contains the app and a **local kind smoke-test manifest**. The GitOps Helm chart and AWS build resources come in the next phases.

- `frontend/`: static HTML/CSS/JS served by Nginx; `/api/` proxies to `taskboard-api`.
- `backend/`: FastAPI CRUD routes, with Redis used for task storage.
- `k8s/kind.yaml`: local deployment with a 1 GiB Redis PVC for validating the images before building the Helm chart.

Prerequisites: Docker running, `kind`, `kubectl`, and a kind cluster. Run commands from the repository root. On a Mac with Docker Desktop, give Docker enough memory for your existing cluster plus these three Pods.

## Try it with Docker Compose first (optional)

```bash
docker compose up --build -d
curl -i http://localhost:8080/healthz
curl -i http://localhost:8080/api/tasks
```

Open <http://localhost:8080> and add a task. Stop with `docker compose down` (add `-v` only if you want to erase the Compose Redis data).

## Build and test in kind

Check your cluster name with `kind get clusters`. If it is `k8s-live-demo`, use that value below; otherwise replace it. Confirm `kubectl config current-context` matches the cluster you want to use. On an existing installation, back up any tasks you want to keep **before** applying the changed Redis Deployment: the old Redis Pod used ephemeral storage and its in-memory tasks cannot move automatically onto the new volume. With a port-forward running, `curl -sS http://localhost:8080/api/tasks > tasks-backup.json` exports them; use `python3 scripts/restore_tasks.py tasks-backup.json` after the new Redis Pod is ready. The restore assigns new IDs and retains titles and statuses.

```bash
kind get clusters
kubectl config current-context
docker build -t taskboard-api:local ./backend
docker build -t taskboard-web:local ./frontend
kind load docker-image taskboard-api:local taskboard-web:local --name k8s-live-demo
kubectl apply -f k8s/kind.yaml
kubectl -n taskboard get pvc
kubectl -n taskboard rollout status deployment/taskboard-redis --timeout=120s
kubectl -n taskboard rollout status deployment/taskboard-api --timeout=120s
kubectl -n taskboard rollout status deployment/taskboard-web --timeout=120s
kubectl -n taskboard get pods,svc
kubectl -n taskboard port-forward service/taskboard-web 8080:80
```

Leave port-forward running in that terminal. In another terminal, open <http://localhost:8080> or run:

```bash
curl -i http://localhost:8080/healthz
curl -i http://localhost:8080/api/tasks
curl -i -X POST http://localhost:8080/api/tasks -H 'Content-Type: application/json' -d '{"title":"Ship my first GitOps app"}'
curl -i -X PATCH http://localhost:8080/api/tasks/1 -H 'Content-Type: application/json' -d '{"status":"doing"}'
curl -i http://localhost:8080/api/tasks
curl -i -X DELETE http://localhost:8080/api/tasks/1
```

IDs are assigned by Redis, so substitute the actual returned ID if you created tasks earlier.

## See the Redis readiness dependency

```bash
kubectl -n taskboard scale deployment/taskboard-redis --replicas=0
kubectl -n taskboard get pods -w
```

After the backend readiness probe fails, the backend Pod remains running but becomes **NotReady**. The frontend still serves its page, while `/api/tasks` fails until Redis is restored. Restore it and inspect the probes:

```bash
kubectl -n taskboard scale deployment/taskboard-redis --replicas=1
kubectl -n taskboard rollout status deployment/taskboard-redis --timeout=120s
kubectl -n taskboard get pods
kubectl -n taskboard describe pod -l app=taskboard-api
```

Redis writes append-only files to a PVC mounted at `/data`. Verify persistence by adding a task, then recreating the Redis Pod:

```bash
kubectl -n taskboard delete pod -l app=taskboard-redis
kubectl -n taskboard rollout status deployment/taskboard-redis --timeout=120s
curl -sS http://localhost:8080/api/tasks
kubectl -n taskboard get pvc
```

The task should still be present. If the PVC stays `Pending`, check `kubectl get storageclass` and `kubectl -n taskboard describe pvc taskboard-redis-data`; the cluster needs a default dynamic StorageClass. This volume is stored in your kind node and **will not survive deleting the kind cluster**. Redis uses `appendfsync everysec`, so a sudden host failure can lose roughly the last second of writes.

## Troubleshooting and cleanup

```bash
kubectl -n taskboard get pods,svc,endpoints
kubectl -n taskboard describe pod -l app=taskboard-web
kubectl -n taskboard logs deployment/taskboard-web
kubectl -n taskboard logs deployment/taskboard-api
kubectl -n taskboard logs deployment/taskboard-redis
kubectl delete -f k8s/kind.yaml
```

**Cleanup deletes the PVC and its data.** For routine app updates, use `kubectl apply -f k8s/kind.yaml` and keep the claim. `ErrImageNeverPull` means the local image is missing from that kind cluster; repeat `kind load docker-image ... --name <actual-cluster-name>`. If you rebuild an image under the same `:local` tag, reload it and run `kubectl -n taskboard rollout restart deployment/taskboard-api deployment/taskboard-web`.
