# A flask app to browse, add and edit files in a gitea repository.
This is a proof of concept of a web app to browse and edit files (survey files from carlson survpc) in a gitea repository.

## .env
Add this secrets and enviroment variables in a .env file or insert them in another way into the app:
```
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
```

## docker-compose.yml
Example of docker compose file for running the app
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

When everything is up and running, you should be able to access the app at `http://your.domain.for.this.app:8000` and if you have a nginx proxy in front of it, you can access it at after updating the nginx config.