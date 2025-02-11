#!/bin/sh

#This file is part of iPipet.
#copyright (c) 2014 Dina Zielinski (dina@wi.mit.edu)

#iPipet is free software: you can redistribute it and/or modify
#it under the terms of the GNU Affero General Public License as published by
#the Free Software Foundation, either version 3 of the License, or any later version.

#iPipet is distributed in the hope that it will be useful,
#but WITHOUT ANY WARRANTY; without even the implied warranty of
#MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#GNU General Public License for more details.

#You should have received a copy of the GNU Affero General Public License
#along with iPipet.  If not, see <http://www.gnu.org/licenses/agpl-3.0.html>.


##
## A user-land script, based gunicorn init.d script here:
##    https://gist.github.com/suda/748450
##
## 1. Adapted to run one specific application.
## 2. Adapted to run as a non-system user (not ideal, but works)
## 3. Adapter to write logs and PID to the script's directory (not idael, but works)
## 4. minimal support for error reporting - not yet suitible for "/etc/init.d/" usage.

die()
{
    BASE=$(basename "$0")
    echo "$BASE: error: $@" >&2
    exit 1
}


DESC="iPipet"
## The application script name (e.g. "pooling.py")
## This will determine the name of the PID and LOG files, as well.
FLASK_APP_FILE=pooling.py
## The name of the variable containing the flask application ('app' in most cases)
FLASK_APP_VAR_NAME=app
## IP To bind to (commonly: 0.0.0.0 or 127.0.0.1)
BIND_IP=0.0.0.0
BIND_TCP_PORT=5105
## Number of thread for gunicorn
WORKERS=2

## Find the full path of the current directory
## (note: readlink -e only works on Linuxes with GNU Coreutils)
BASEDIR=$(readlink -e $(dirname "$0")) || exit 1

[ -e "$BASEDIR/$FLASK_APP_FILE" ] || die "Flask script '$BASEDIR/$FLASK_APP_FILE' not found"
FLASK_NAME=$(basename "$FLASK_APP_FILE" .py) || exit 1

PIDFILE=$BASEDIR/$FLASK_NAME.pid
ACCESSLOG=$BASEDIR/$FLASK_NAME.access.log
ERRORLOG=$BASEDIR/$FLASK_NAME.error.log

GUNICORN=$(which gunicorn) || die "'gunicorn' program not found"

## For non-root users, 'start-stop-daemon' might not be in the $PATH,
## so find it.
START_STOP_DAEMON=/sbin/start-stop-daemon
[ -x "$START_STOP_DAEMON" ] || die "'start-stop-daemon' not found ($START_STOP_DAEMON)"

start () {
    echo "Starting iPipet..."
    echo "Using Gunicorn at: $GUNICORN"
    echo "Flask app file: $FLASK_APP_FILE"
    echo "Binding to: $BIND_IP:$BIND_TCP_PORT"
    echo "Working directory: $BASEDIR"
    
    "$START_STOP_DAEMON" --start \
            --pidfile "$PIDFILE" \
            --chdir "$BASEDIR" \
            --exec "$GUNICORN" \
            -- \
            --bind "$BIND_IP:$BIND_TCP_PORT" \
            --workers "$WORKERS" \
            --daemon \
            --pid "$PIDFILE" \
            --preload \
            --log-level error \
            --access-logfile "$ACCESSLOG" \
            --error-logfile "$ERRORLOG" \
            "$FLASK_NAME:$FLASK_APP_VAR_NAME"

    ## Wait and check status
    sleep 2
    status
}

stop () {
	"$START_STOP_DAEMON" --stop \
			--pidfile "$PIDFILE"
}

status () {
	"$START_STOP_DAEMON" --status \
			--pidfile "$PIDFILE"
}

reload () {
	"$START_STOP_DAEMON" --stop \
			--signal HUP \
			--pidfile "$PIDFILE"
}

case "$1" in
	start)
		printf "Starting $DESC ..."
		start
		case "$?" in
			0) printf "OK\n" ;;
			*) printf "Failed\n" ;;
		esac
		;;
	stop)
		printf "Stopping $DESC ..."
		stop
		case "$?" in
			0|1) printf "OK\n" ;;
			2) printf "Failed\n" ;;
		esac
		;;
	status)
		printf "Status-check $DESC ..."
		status
		case "$?" in
			0) printf "Running.\n" ;;
			1) printf "Not running (but PID file exists)\n" ;;
			3) printf "Not running\n" ;;
			4) printf "Failed to check status\n" ;;
		esac
		;;
	reload)
		echo "Reloading $DESC"
		reload
		;;
	restart)
		echo "Restarting $DESC"
		stop
		sleep 1
		start
		;;
	*)
		echo "Usage: $(basename $0)  {start|stop|status|restart|reload}" >&2
		exit 1
		;;
esac

exit 0
