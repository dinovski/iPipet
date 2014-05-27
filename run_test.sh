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
## Poor man's test suite for this very specific website.
## Used until proper flask-compatible testing is implemented.
##

die()
{
	BASE=$(basename "$0")
	echo "$BASE error: $@" >&2
	exit 1
}

TYPE=$1
[ -z "$TYPE" ] && die "please specify 'dev' or 'prod' (which website to test)"

case "$TYPE" in
 prod) URL="http://ipipet.teamerlich.org" ;;
 dev)  URL="http://ipipetdev.teamerlich.org" ;;
 *) die "unknown type '$TYPE' (expecting 'dev' or 'prod')" ;;
esac

##
## Check the main page, ensure it works
##
wget -O /dev/null -q "$URL" || die "Can't access '$URL' - is the Flask application running?"


##
## Use "WGET" to visit all simple links in the website
##
DIR=$(mktemp -d -t ipipet_test.XXXXXXX) || die "failed to create temporary directory"
( cd "$DIR" && wget --spider --recursive "$URL" 1>wget.out.log 2>wget.err.log ) ||
	die "Found broken links in '$URL'. See logs in '$DIR'"

## Delete the temporary directory - if all links exist
rm -r "$DIR"

##
## Check <FORM> submission
##  "--location" will follow the redirection (after successful submission)
##  "-H Expect" is needed to avoid 417 error, see here:
##        http://stackoverflow.com/questions/9120760/curl-simple-file-upload-417-expectation-failed
##  "--write-out" will print the resuling URL after redirection - that's the only thing we care about
TESTURL=$(curl -o /dev/null --silent --location \
      --write-out "%{url_effective}\\n" \
      --fail \
      -H "Expect:" \
      -F pipet_type=single \
      -F email=agordon@wi.mit.edu \
      -F description=AutoUnitTest \
      -F"csv_file=@uploads/demolnk1.csv" \
      "$URL/create") || die "Form submission failed"

ID=$(echo "$TESTURL" | perl -ne 'm;/show/(\w{8})$; && print $1')
[ -z "$ID" ] && die "Failed to extract ID from URL '$TESTURL'"

##
## Now try to run this newly uploaded plate
##
wget -q -O /dev/null "$URL/run/$ID" || die "Failed to get url '$URL/run/$ID' for newly uploaded plate '$ID'"
wget -q -O /dev/null "$URL/data/$ID" || die "Failed to get url '$URL/data/$ID' for newly uploaded plate '$ID'"

