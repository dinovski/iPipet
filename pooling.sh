#!/bin/sh

## Start a "flask" application using "gunicorn".
## See here:
##  http://flask.pocoo.org/docs/deploying/wsgi-standalone/

##
## NOTE!
##   This is the "production" version startup script,
##   It uses TCP port 5105.
##   accessible with http://ipipet.teamerlich.org/
##   See /etc/lighttpd/conf-enabled/90-5-vhost-ipipet.teamerlich.org.conf

gunicorn --access-logfile pooling.access.log \
	 --error-logfile pooling.gunicorn.error.log \
	 --bind 127.0.0.1:5105 \
	 --pid pooling.pid \
	 --workers 2 \
	 --log-level error \
	 --daemon \
	pooling:app
