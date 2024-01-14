# Docker compose

    version: '3'
    services:
      soundlib:
        image: atlantis-soundlib:latest
        ports:
          - "5000:5000"
        environment:
          S3_BUCKET: <bucket>
          AWS_ACCESS_KEY_ID: <key_id>
          AWS_SECRET_ACCESS_KEY: <secret_key>
          S3_ENDPOINT: <endpoint>
        volumes:
          - /tmp/data:/app/instance/
