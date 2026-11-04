# Rigorlytics on Kubernetes

Local k3s deployment. Nothing here costs money and nothing touches AWS.

## 1. Install k3s

k3s is a CNCF-certified Kubernetes distribution in a single binary. It
ships with containerd, CoreDNS, Traefik as the ingress controller,
metrics-server (which the HPA needs) and a NetworkPolicy controller, so
the manifests in this directory work without add-ons.

The upstream instructions pipe a script from the internet into a shell.
For a security-focused project, download and read it first:

```bash
curl -sfL https://get.k3s.io -o /tmp/k3s-install.sh
less /tmp/k3s-install.sh          # read before running
sudo INSTALL_K3S_EXEC="--write-kubeconfig-mode 644" sh /tmp/k3s-install.sh
```

Then point kubectl at it:

```bash
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown "$USER:$USER" ~/.kube/config
chmod 600 ~/.kube/config
kubectl get nodes
```

## 2. Load the image into the cluster

k3s uses containerd, not Podman, so the image has to be imported. There is
no registry involved and nothing leaves the machine.

```bash
cd ~/rigorlytics
podman build --format docker -t rigorlytics:dev .
podman save localhost/rigorlytics:dev | sudo k3s ctr images import -
sudo k3s ctr images ls | grep rigorlytics
```

Re-run this after every code change, then `kubectl rollout restart` the
Deployment. `imagePullPolicy: Never` in the Deployment is what stops
Kubernetes trying to pull a tag that exists only locally.

## 3. Create the Secret from .env

Deliberately imperative. The two credentials never appear in a file that
git tracks, which is why there is no `secret.yaml` in this directory.

```bash
kubectl create namespace rigorlytics --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic rigorlytics-secrets \
  --namespace rigorlytics \
  --from-env-file=.env \
  --dry-run=client -o yaml | kubectl apply -f -
```

Verify the keys landed without printing their values:

```bash
kubectl -n rigorlytics get secret rigorlytics-secrets -o jsonpath='{.data}' | tr ',' '\n' | cut -d'"' -f2
```

Worth knowing and worth saying in an interview: a Kubernetes Secret is
base64-encoded, not encrypted, unless encryption at rest is enabled on
etcd. On EKS that means a KMS key in `cluster_encryption_config`. The
better pattern for production is the External Secrets Operator or the
Secrets Store CSI driver pulling from AWS Secrets Manager, so the secret
of record lives somewhere with rotation and an audit trail.

## 4. Apply

```bash
kubectl apply -f k8s/
kubectl -n rigorlytics rollout status deploy/rigorlytics-web --timeout=120s
```

## 5. Verify

```bash
kubectl -n rigorlytics get pods,svc,ingress,hpa,pdb
kubectl -n rigorlytics get networkpolicy
kubectl -n rigorlytics logs -l app.kubernetes.io/name=rigorlytics --tail=50
```

Reach the app:

```bash
kubectl -n rigorlytics port-forward svc/rigorlytics-web 8080:80
curl -i http://127.0.0.1:8080/health
```

Or through the Ingress:

```bash
curl -i -H 'Host: rigorlytics.localhost' http://127.0.0.1/health
```

## 6. Things worth breaking on purpose

These are the demos that prove the controls are real rather than decorative.

**Pod Security Admission rejects a privileged pod.** Delete
`runAsNonRoot: true` from `03-deployment.yaml` and reapply. The API server
refuses it and names the policy. Put it back.

```bash
kubectl -n rigorlytics apply -f k8s/03-deployment.yaml
```

**PodDisruptionBudget blocks an unsafe drain.** With 2 replicas and
`minAvailable: 1`, draining the only node cannot evict both:

```bash
kubectl drain "$(kubectl get nodes -o name | head -1 | cut -d/ -f2)" \
  --ignore-daemonsets --delete-emptydir-data --dry-run=server
```

**NetworkPolicy blocks lateral movement.** Open a shell in the pod and try
to reach the metadata endpoint, which is the first thing an attacker tries
because on a cloud node it hands out IAM credentials:

```bash
kubectl -n rigorlytics exec -it deploy/rigorlytics-web -- \
  sh -c 'curl -m 3 http://169.254.169.254/ ; echo "exit=$?"'
```

It should time out. Delete `06-networkpolicy.yaml`, try again, and watch
it connect. That before-and-after is the whole argument for
microsegmentation in one command.

**HPA scales under load.**

```bash
kubectl -n rigorlytics get hpa -w
```

## 7. Scan the manifests

```bash
trivy config k8s/
```

Expect findings, and expect some to be arguable. Triaging them is the
exercise, not driving the number to zero for its own sake.

## What maps to what on EKS

| Local (k3s) | EKS |
|---|---|
| `ingressClassName: traefik` | `alb` + AWS Load Balancer Controller |
| `imagePullPolicy: Never` | ECR image path + `IfNotPresent` |
| Secret from `.env` | External Secrets Operator + Secrets Manager |
| k3s netpol controller | VPC CNI with NetworkPolicy enabled |
| Single node | Managed node groups across three AZs |
| `emptyDir` volumes | unchanged |

Everything else in these files applies unchanged. That portability is the
point of the abstraction.
