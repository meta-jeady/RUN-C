# DarkTunnel Decryptor Bot

Bot Telegram qui décrypte les fichiers `.dark` et génère un fichier `.txt` clair.

## Fonctionnalités

- Accepte fichier `.dark` ou lien `darktunnel://`
- Décrypte complètement la config
- Affiche : Target server, UUID, Path, SNI, Header Host
- Reconstruit le lien VLESS
- Envoie un fichier `.txt` téléchargeable

## Déploiement Render

1. Repo GitHub avec les fichiers
2. New → Background Worker
3. Build : `pip install -r requirements.txt`
4. Start : `python bot.py`
5. Environment :
