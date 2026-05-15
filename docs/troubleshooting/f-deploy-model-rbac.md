# F — Erreur 403 / 404 : étape `deploy-model`

Cette étape a nécessité **deux corrections successives** avant de fonctionner.

---

## F.1 — Erreur `403 Forbidden` : RBAC manquant

### Symptôme

```
kubernetes.client.exceptions.ApiException: (403)
Reason: Forbidden
message: "deployments.apps \"log-clustering-serving\" is forbidden:
  User \"system:serviceaccount:kubeflow:pipeline-runner\"
  cannot get resource \"deployments\" in API group \"apps\"
  in the namespace \"default\""
```

### Cause

Le composant `deploy_model` s'exécute avec l'identité du ServiceAccount `pipeline-runner` (namespace `kubeflow`). Ce SA n'a par défaut **aucun droit** sur les ressources du namespace `default`. Kubeflow k8s refuse toute lecture ou écriture sur les Deployments avec HTTP 403.

!!! important "Ce n'est pas un bug Python"
    C'est une restriction **RBAC** de Kubeflow k8s. Le fix se fait **une seule fois** au niveau du cluster, pas dans le code.

### Fix — Appliquer le manifeste RBAC

```bash
kubectl apply -f manifests/pipeline-runner-deploy-rbac.yaml
```

Contenu du manifeste `manifests/pipeline-runner-deploy-rbac.yaml` :

```yaml
# Role : droits sur les Deployments dans "default"
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pipeline-runner-deployer
  namespace: default
rules:
- apiGroups: ["apps"]
  resources: ["deployments"]
  verbs: ["get", "list", "create", "patch", "update"]

---

# RoleBinding : lie pipeline-runner (kubeflow) au Role ci-dessus
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: pipeline-runner-deployer-binding
  namespace: default
subjects:
- kind: ServiceAccount
  name: pipeline-runner
  namespace: kubeflow
roleRef:
  kind: Role
  name: pipeline-runner-deployer
  apiGroup: rbac.authorization.k8s.io
```

### Vérification des droits

```bash
kubectl get role,rolebinding -n default | grep pipeline-runner

kubectl auth can-i get deployments \
  --as=system:serviceaccount:kubeflow:pipeline-runner -n default
# → yes

kubectl auth can-i create deployments \
  --as=system:serviceaccount:kubeflow:pipeline-runner -n default
# → yes
```

---

## F.2 — Erreur `404 Not Found` : Deployment inexistant

### Symptôme (après correction du RBAC)

```
kubernetes.client.exceptions.ApiException: (404)
Reason: Not Found
message: "deployments.apps \"log-clustering-serving\" not found"
```

### Cause

Le code original effectuait un `read_namespaced_deployment()` puis un `patch_namespaced_deployment()`. Si le Deployment `log-clustering-serving` n'a jamais été créé dans le namespace `default`, la lecture retourne 404 et le composant plante — même avec les bons droits RBAC.

### Fix — Pattern Upsert dans `deploy_model.py`

Le composant a été réécrit pour gérer les deux cas (création + mise à jour) :

```python
try:
    dep = apps_v1.read_namespaced_deployment(deployment_name, deployment_namespace)

    # CAS 1 : Deployment existant → patch de l'image uniquement (rolling update)
    idx = next((i for i, c in enumerate(dep.spec.template.spec.containers)
                if c.name == container_name), None)
    patch = [{"op": "replace",
              "path": f"/spec/template/spec/containers/{idx}/image",
              "value": new_image}]
    apps_v1.patch_namespaced_deployment(
        name=deployment_name, namespace=deployment_namespace,
        body=patch, content_type="application/json-patch+json",
    )
    action = "patche (rolling update declenche)"

except ApiException as e:
    if e.status != 404:
        raise  # 403, 500... -> on propage

    # CAS 2 : Deployment absent → création complète avec toutes les env vars
    apps_v1.create_namespaced_deployment(
        namespace=deployment_namespace,
        body=client.V1Deployment(...)   # spec complète : image, ports, env MLflow/MinIO
    )
    action = "cree (premier deploiement)"
```

---

## Résumé des deux corrections

| Ordre | Erreur | Cause | Fix |
|---|---|---|---|
| **1** | `403 Forbidden` | SA `pipeline-runner` sans droits sur `deployments/default` | `kubectl apply -f manifests/pipeline-runner-deploy-rbac.yaml` |
| **2** | `404 Not Found` | Deployment `log-clustering-serving` inexistant | Pattern Upsert dans `deploy_model.py` |

```
Flux de decision du composant deploy_model (apres fix) :

  read_namespaced_deployment()
        |
        +-- 200 OK  --> Deployment existant
        |              --> patch image uniquement (rolling update)
        |
        +-- 404     --> Deployment absent
                       --> create_namespaced_deployment() (spec complete)

  Toute autre erreur (403, 500...) → propagee normalement
```

!!! note "Corrections permanentes"
    Le Role/RoleBinding RBAC persiste dans etcd, et le code upsert de `deploy_model.py` est versionné dans le dépôt. Le pipeline fonctionne quel que soit l'état initial du cluster.
