ipipet.teamerlich.org is no longer maintained. Below are instructions to run iPipet locally:

You can run the flask app locally from the 'heroku' branch.

**Local setup:**

Create system user 'ipipet':
```
sudo adduser --system --group --no-create-home ipipet
```

Create directories for ipipet:
```
sudo mkdir /var/{run,log}/ipipet
sudo chown ipipet:ipipet /var/{run,log}/ipipet
sudo chmod 0755 /var/{run,log}/ipipet
```

Run the flask app with gunicorn as user ipipet:
```
sudo ./pooling.sh start
```

