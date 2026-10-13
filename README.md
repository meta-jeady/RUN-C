# KCORP-TECH Bot

Bot Telegram public qui génère automatiquement des configurations **VLESS** à partir de liens SSO Google Skills.

## Fonctionnalités

- Reçoit un lien SSO Google Skills
- Déploie automatiquement un service Cloud Run avec l'image `docker.io/metajeady/kcorp1`
- Génère une config VLESS personnalisée
- Envoie aussi un fichier JSON
- Système de limite anti-abus (3/heure - 8/jour)

## Déploiement sur Render

### 1. Fichiers nécessaires
- `bot.py`
- `requirements.txt`
- `Dockerfile`

### 2. Variables d'environnement

Sur Render, ajoute uniquement :
