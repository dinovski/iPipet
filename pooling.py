#!/usr/bin/env python

from flask import Flask, url_for, request, redirect, jsonify
from flask import render_template
from werkzeug import secure_filename
import string
import datetime
import random
import json
import re
import sys
import os
import csv
import datetime
from subprocess import Popen,PIPE

app = Flask(__name__)
app.debug = True

# Flask File uploads:
#   http://flask.pocoo.org/docs/patterns/fileuploads/
UPLOAD_FOLDER = os.path.dirname(os.path.abspath(__file__)) + '/uploads/'
if not os.path.isdir(UPLOAD_FOLDER):
	sys.exit("Internal error: UPLOAD_FOLDER (%s) is not a valid directory. Please create it or change the script (%s)" % ( UPLOAD_FOLDER, __file__ ) )

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

def get_random_id(size=8, chars=string.ascii_uppercase + string.digits + string.ascii_lowercase):
    return ''.join(random.choice(chars) for x in range(size))

def valid_email(email):
    """
        given an email string,
        returns True if the string represents a "mostly" valid email.
        Some exotic email address will not properly validate here.

        See:
        http://stackoverflow.com/questions/8022530/python-check-for-valid-email-address
    """
    EMAIL_REGEX = re.compile("^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,4}$")
    m = EMAIL_REGEX.search(email)
    return (m is not None)

def valid_id(id):
    """
    Given an ID string, returns TRUE if the ID is valid (only letters/digits)
    """
    if len(id)==0:
        return False
    ID_REGEX = re.compile("^[A-Za-z0-9]+$")
    m = ID_REGEX.search(id)
    return (m is not None)

def files_from_id_unsafe(id):
    """
    Given an ID string, returns a tuple of JSON-File-path, CSV-File-Path.

    The full-path is based on the UPLOAD_FOLDER setting.

    Raises an exception if the ID is invalid.
    Unsafe: because the returned filenames don't necessarily exist.

    Example:
      json_file, csv_file = files_from_id_unsafe('xT44MJHe')
    """
    if not valid_id(id):
        raise Exception("Invalid ID '%s' (invalid string)" % ( id ) )

    basepath = os.path.join(app.config['UPLOAD_FOLDER'], id)
    csv_path = basepath + ".csv"
    json_path = basepath + ".json"
    return json_path,csv_path

def files_from_id(id):
    """
    Given an ID string, returns a tuple of JSON-File-path, CSV-File-Path.

    The full-path is based on the UPLOAD_FOLDER setting.

    Raises an exception if the ID is invalid, OR if the files don't exist.

    Example:
      json_file, csv_file = files_from_id('xT44MJHe')
    """
    json_path, csv_path = files_from_id_unsafe(id)
    if not os.path.exists(csv_path):
        raise Exception("Error: invalid id '%s' (no such entry/csv)" % ( id ))
    if not os.path.exists(json_path):
        raise Exception("Error: invalid id '%s' (no such entry/json)" % ( id ))
    return json_path,csv_path

def well_num_to_name(well):
    """
    Given a Well number (1 to 96) returns its name (e.g. 14 => "B02")
    """
    try:
        well = int(well)
    except ValueError:
        raise Exception("Error: invalid well number '%s'" % ( well ))
    if well<1 or well>96:
        raise Exception("Error: invalid well value '%d'" % ( well ))
    row = chr( ord('A') + int((well-1)%8) )
    col = (well-1)/8+1;
    return "%s%02d" % ( row, col )

def load_plating_csv(filename):
    """
    Given a filename of a CSV containing manual plating instructions,
    loads the CSV and returns an array-of-array, containing the plating steps.

    The CSV is expected to have 6 fields:
        source plate,
        source well number (1-96)
        dest plate,
        dest well number (1-96)
        volume,
        specimen name.

    NOTE:
    The output data will have 11 elements, and is tightly coupled
    with the JavaScript parsing code.
    """
    try:
        data = [ ]
        prev_src_plate = None
        prev_dst_plate = None
        try:
            for row_num,row in enumerate(csv.reader(open(filename))):
                if row_num==0: # skip header line
                    continue
                if len(row) < 4:
                    raise Exception("expecting at least 4 fields")
                row = [ x.strip() for x in row ]

                # The columns are tightly-coupled to the JavaScript code
                # in XXXXXXXX.js
                temp = [row_num,                 # 1. Step/Stroke number
                        row[0],                  # 2. Source Plate
                        int(row[1]),             # 3. Source Well number (1-96)
                        well_num_to_name(row[1]),# 4. Source Well Name (e.g. "B02")
                        row[2],                  # 5. Destination Plate
                        int(row[3]),             # 6. Destination Well number (1-96)
                        well_num_to_name(row[3])]# 7. Destination Well Name (e.g. "F11")

		if len(row) >= 5:
			temp.append(float(row[4]))           # 8. volume
		if len(row) >= 6:
			temp.append(row[5])      # 9. Specimen Name

                data.append(temp)
            return data

        except Exception as e:
            raise Exception("invalid CSV content at line '%s': %s" % ( row_num, str(e) ) )

    except Exception as e:
        raise Exception("Error loading CSV file: " + str(e))

@app.route("/")
def splash():
    return render_template("splash.html")

@app.route("/splash2")
def splash2():
    return render_template("splash2.html")

@app.route("/splash3")
def splash3():
    return render_template("splash3.html")
    
@app.route("/home")
def home():
    return render_template("home.html")
    
@app.route("/usage")
def usage():
    return render_template("about.html")
    
@app.route("/create", methods=['POST'])
def create():
    ## Get parameters from the user.
    ## Validate them, or show an error if they're invalid.
         
    email = request.form['email'].strip()
    if len(email)>0:
        if not valid_email(email):
            return "Error: invalid email address '%s'" % ( email ), 400

    if not 'description' in request.form:
        return "Error: missing 'description' parameter", 400
    description = request.form['description'].strip()

    if not 'csv_file' in request.files:
        return "Error: missing CSV file", 400
    file = request.files['csv_file']
    if not file:
        return "Error: no CSV file uploaded", 400

    if not 'pipet_type' in request.form:
        return "Error: missing 'pipet_type' parameter", 400
    pipet_type = request.form['pipet_type'].strip()

    if not (pipet_type=='single' or pipet_type=='multi8'):
        return "Error: invalid pipet type %s" % (pipet_type), 400

    ## Save the uploaded file, and the request parameters
    id = get_random_id()
    json_path,csv_path = files_from_id_unsafe(id)

    ## TODO: Validate CSV content
    file.save(csv_path)

    ## TODO: Read and analyze CSV file
    f = open(csv_path,"r")
    reader = csv.reader(f)
    numsteps = 0
    srcplates = []
    destplates = []

    for row in reader:
        numsteps += 1
        #skip header: continue skips rest of loop and returns to beginning
        if numsteps == 1:
            continue
        srcplates.append(row[0])
        destplates.append(row[2])

    #set module allows manipulation of unordered collections of unique elements
    srcplates = list(set(srcplates))
    destplates = list(set(destplates))

    # send email   
    info = { "email" : email,
             "description" : description,
             "id" : id,
             "useragent": str(request.user_agent),
             "remote_addr": request.remote_addr,
             "time": str(datetime.datetime.now()),
             "numsteps": numsteps-1,
             "srcplates": srcplates,
             "destplates": destplates,
             "pipet_type": pipet_type
             }
    json.dump(info,open(json_path,'w'))


    ## TODO: Now send an email with instructions
    link = url_for('show',id=id)
    if email:
         sendemail(email, description, link)

    ## Redirect User to Plate summary page
    return redirect(link)


def sendemail(email,description,link):
    args = [ 'mailx' ]

    # Subject
    args.append('-s')
    args.append('ipipet file')

    # From
    args.append('-r')
    args.append('ipipet admin <dina@wi.mit.edu>')

    # Bcc
    args.append('-b')
    args.append('dina@wi.mit.edu')

    # TO
    args.append(email)

    msg = """
    here's your link to start pipetting, based on the input file for your %s project.
    
    Open this email on your tablet, and click this link:
    http://ipipet.teamerlich.org%s
    """ % ( description, link )
    
    p = Popen(args, stdin=PIPE)
    p.communicate(input=msg)


@app.route('/show/<id>')
def show(id):
    json_path,csv_path = files_from_id(id)
    info = json.load(file(json_path))
    return render_template('show.html', info=info)

@app.route('/run/<id>')
def run(id):
    dpi = 96 # Default DPI if none specified
    try:
        if 'dpi' in request.args:
            newdpi = int(request.args.get('dpi'))
            if newdpi>10:
                dpi = newdpi
    except:
        dpi = 96

    # We dont really need this info,
    # but the function will validate that the ID exists.
    json_path,csv_path = files_from_id(id)
    info = json.load(file(json_path))

    data_url = url_for("data",id=id)
    return render_template("run.html",data_url=data_url,id=id,dpi=dpi,info=info)

@app.route('/data/<id>')
def data(id):
    json_path,csv_path = files_from_id(id)
    data = load_plating_csv(csv_path)
    return jsonify(data=data)


if __name__ == "__main__":
    ## NOTE: Running "./pooling.py" directly starts the DEVELOPMENT version,
    ##       Using TCP port 5106,
    ##       accessible with http://ipipetdev.teamerlich.org/
    ##       See /etc/lighttpd/conf-enabled/90-5-vhost-ipipet.teamerlich.org.conf
    app.run(host='127.0.0.1',port=5106)
