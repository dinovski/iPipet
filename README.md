ipipet.teamerlich.org is no longer maintained.

You can run the flask app in a contained environment using docker in heroku-docker branch:

```
git clone 
cd iPipet
git fetch origin
git checkout -b heroku-docker origin/heroku-docker

docker compose build
docker compose up
```

```
# deploy via Heroku CLI
# Docker images built with Apple Silicon can create issues when deploying the images to a Linux based *AMD64 environment
export DOCKER_DEFAULT_PLATFORM=linux/amd64

heroku login
heroku container:login

# push docker image to heroku
heroku container:push web -a ipipet

# release the container
heroku container:release web -a ipipet

# open deployed app
heroku open -a ipipet
```

App will be accessible through port 5105

NOTE: some of the files are missing for the demos/examples.
