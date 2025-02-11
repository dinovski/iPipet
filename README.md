ipipet.teamerlich.org is no longer maintained.

You can run the flask app in a contained environment using docker in heroku-docker branch:

```
git clone https://github.com/dinovski/iPipet.git
cd iPipet
git checkout heroku-docker
docker compose build
docker compose up
```

App will be accessible through port 5105

NOTE: some of the files are missing for the demos/examples.
