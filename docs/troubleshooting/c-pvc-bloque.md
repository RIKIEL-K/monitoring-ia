# C — PVC / PV bloqué (suppression impossible)

## Symptôme

La commande `kubectl delete pvc ...` reste **bloquée indéfiniment** ou refuse de mettre à jour le chemin `hostPath`.

```bash
kubectl delete pvc training-data-pvc -n kubeflow
# [bloqué... aucune réponse]
```

## Cause

Kubernetes place un cadenas de sécurité (`finalizer`) sur les volumes lorsqu'il pense qu'un pod l'utilise encore — même si le pod a planté ou a été supprimé.

## Solution

Forcer la suppression du `finalizer` et supprimer le volume :

```bash
# 1. Supprimer le cadenas du PVC et le forcer
kubectl patch pvc training-data-pvc -n kubeflow -p '{"metadata":{"finalizers":null}}'
kubectl delete pvc training-data-pvc -n kubeflow --grace-period=0 --force

# 2. Supprimer le cadenas du PV et le forcer
kubectl patch pv training-data-pv -p '{"metadata":{"finalizers":null}}'
kubectl delete pv training-data-pv --grace-period=0 --force

# 3. Recréer le volume proprement
kubectl apply -f manifests/data-pv.yaml
```

## Vérification

```bash
kubectl get pvc,pv -n kubeflow | grep training
# Plus de ressource bloquée = suppression réussie
```

!!! tip "Astuce"
    Si le PVC cible un autre nom, remplacez `training-data-pvc` par le nom de votre ressource. Utilisez `kubectl get pvc -A` pour lister toutes les PVCs.
