A flask app to browse, add and edit files in a gitea repository.

Add this secrets in a .env file or insert them in another way into the app:
// Flask secret key
secret_key=

// Secrets to be able to login to gitea
client_id=
client_secret=

// Where your gitea instance is running, https://gitea.yourdomain/
gitea_instance=

// Celery broker and backend, e.g. redis://redis:6379/0
CELERY_BROKER_URL=
CELERY_RESULT_BACKEND=


# Example of docker compose file for running the app
```
services:
  repo_browser:
    # image: ghcr.io/joseffallman/repo_browser:main
    build: .
    container_name: repo_browser
    environment:
      secret_key: 123456
      client_id: 123456
      client_secret: 123456
      gitea_url: https://your.gitea.instance/
      app_url: https://your.domain.for.this.app/
      OAUTHLIB_INSECURE_TRANSPORT: true
    restart: always
    networks:
      - nginx_nginx
    depends_on:
      - redis

  celery_worker:
    image: mcr.microsoft.com/devcontainers/python:1-3.12-bullseye
    container_name: celery_worker
    depends_on:
      - jocoding_cloud
    networks:
      - nginx_nginx
    working_dir: /app
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/0
    command: >
      celery -A tasks.celery worker

  redis:
    image: redis:latest
    networks:
      - nginx_nginx

```