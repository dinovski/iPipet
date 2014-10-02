#!/usr/bin/env python

"""
This file is part of iPipet. 
copyright (c) 2014 Dina Zielinski (dina@wi.mit.edu)

	iPipet is free software: you can redistribute it and/or modify
	it under the terms of the GNU Affero General Public License as published by
	the Free Software Foundation, either version 3 of the License, or any later version.

	iPipet is distributed in the hope that it will be useful,
	but WITHOUT ANY WARRANTY; without even the implied warranty of
	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
	GNU General Public License for more details.

	You should have received a copy of the GNU Affero General Public License
	along with iPipet.  If not, see <http://www.gnu.org/licenses/agpl-3.0.html>.
"""

from flask import Flask, url_for, request, redirect, jsonify, render_template, make_response
from werkzeug import secure_filename
from lockfile import LockFile
import markdown
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

community_public_file = os.path.join(app.config['UPLOAD_FOLDER'], "community.json")

# Default shared designs which are always available
default_shared_designs = [ { "description":"96-Wells, Single-Channel Demo","id":"demolnk1", "plate_type": 96, "pipet_type": "single"},
                         { "description":"96-Wells, 8-Channel Demo","id":"demolnk8", "plate_type": 96, "pipet_type": "multi8"},
                         { "description":"384-Wells, Single-Channel Demo","id":"384demo1", "plate_type":384, "pipet_type":"single" }]

#use csv sniffer to handle delimiters, spaces, quotes etc
def opencsv(filename):
	f = open(filename, 'rU') #U takes care of mac newline character
	dialect = csv.Sniffer().sniff(f.read()) 
	f.seek(0)
	reader = csv.reader(f, dialect)
	return reader
	
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

def well96_num_to_name(well):
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

def well384_num_to_name(well):
    """
    Given a Well number (1 to 384) returns its name (e.g. 17 => "A02")
    """
    try:
        well = int(well)
    except ValueError:
        raise Exception("Error: invalid well number '%s'" % ( well ))
    if well<1 or well>384:
        raise Exception("Error: invalid well value '%d'" % ( well ))
    row = chr( ord('A') + int((well-1)%16) )
    col = (well-1)/16+1;
    return "%s%02d" % ( row, col )

def add_shared_community_design(description,id,plate_type,pipet_type):
    """
    Add a plate-ID to the JSON list of shared designs.
    """
    try:
        if not valid_id(id):
            return
        if len(description)==0:
            return

        lock = LockFile(community_public_file)
        with lock:
            data = []
            try:
                data = json.load(file(community_public_file))
            except:
                pass
            data.append( { "description" : description, "id": id, "plate_type": plate_type, "pipet_type": pipet_type } )
            json.dump(data,open(community_public_file,"w"))
    except Exception as e:
        # silently ignore any errors - the new plate will simply not be added to the list
        sys.stderr.write("failed to add shared community (id = '%s', exception='%s')" % ( str(id), str(e) ))

def load_plating_csv(plate_type, filename):
    """
    Given a filename of a CSV containing manual plating instructions,
    loads the CSV and returns an array-of-array, containing the plating steps.

    The CSV is expected to have 6 fields:
        source plate,
        source well number (1-96 or 1-384)
        dest plate,
        dest well number (1-96 or 1-384)
        volume,
        specimen name.

    NOTE:
    The output data will have 11 elements, and is tightly coupled
    with the JavaScript parsing code.
    """
    well_num_to_name = "foo"
    if plate_type == 96:
        well_num_to_name = well96_num_to_name
    elif plate_type == 384:
        well_num_to_name = well384_num_to_name
    else:
        raise "Invalid plate_type %s" % ( plate_type )
    try:
        data = [ ]
        prev_src_plate = None
        prev_dst_plate = None
        try:
            rdr = opencsv(filename)
            for row_num,row in enumerate(rdr):
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

    if not 'plate_type' in request.form:
        return "Error: missing 'plate_type' parameter", 400
    plate_type = request.form['plate_type'].strip()

    if not (plate_type=='96' or plate_type=='384'):
        return "Error: invalid plate type %s" % (plate_type), 400

    share_design = False
    if 'share_design' in request.form:
        share_design = (request.form['share_design'].strip() == "yes")

    if (pipet_type=='multi8' and plate_type=='384'):
        return "Error: multi-channel pipetting is not currently supported for 384 well plates", 400

    if share_design and len(description)==0:
        return "Error: when sharing a design, Description must not be empty", 400

    ## Save the uploaded file, and the request parameters
    id = get_random_id()
    json_path,csv_path = files_from_id_unsafe(id)

    ## TODO: Validate CSV content
    file.save(csv_path)

    ## Read and analyze CSV file using opencsv function
    reader = opencsv(csv_path)
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
             "numsteps": numsteps,
             "srcplates": srcplates,
             "destplates": destplates,
             "pipet_type": pipet_type,
             "plate_type": int(plate_type),
             "share_design": share_design
             }
    json.dump(info,open(json_path,'w'))


    ## TODO: Now send an email with instructions
    link = url_for('show',id=id)
    if email:
         sendemail(email, description, link)

    if share_design:
        add_shared_community_design(description,id,int(plate_type),pipet_type)

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

    well_color = "red" # default color if none specified
    try:
        if 'well_color' in request.args:
            new_well_color = request.args.get('well_color')
            if new_well_color == "red" or new_well_color == "green":
                well_color = new_well_color
    except:
        well_color = "red"

    handedness = "right" # default right hand if not specified
    try:
        if 'handedness' in request.args:
            new_handedness = request.args.get('handedness')
            if new_handedness == "right" or new_handedness == "left":
                handedness = new_handedness
    except:
        handedness = "right"


    # We dont really need this info,
    # but the function will validate that the ID exists.
    json_path,csv_path = files_from_id(id)
    info = json.load(file(json_path))
    

    data_url = url_for("data",id=id)
    return render_template("run.html",data_url=data_url,id=id,dpi=dpi,info=info,well_color=well_color,handedness=handedness)

@app.route('/data/<id>')
def data(id):
    json_path,csv_path = files_from_id(id)
    info = json.load(file(json_path))
    foo = info[u"plate_type"];
    data = load_plating_csv(foo,csv_path)
    return jsonify(data=data)
    
@app.route('/csvdownload/<id>')
def csvdownload(id):
    json_path,csv_path = files_from_id(id)
    mycsv = open(csv_path).read()
    response =  make_response(mycsv)
    response.headers["Content-Disposition"] = "attachment; filename=%s.csv" % (id)
    response.headers["Content-Type"] = "text/csv"
    return response
    
@app.route('/community')
def community():
    data = []
    data.extend(default_shared_designs)
    try:
        tmp = json.load(file(community_public_file))
        data.extend(tmp)
    except:
        pass
    return render_template("community.html",data=data)


if __name__ == "__main__":
    ## NOTE: Running "./pooling.py" directly starts the DEVELOPMENT version,
    ##       Using TCP port 5106,
    ##       accessible with http://ipipetdev.teamerlich.org/
    ##       See /etc/lighttpd/conf-enabled/90-5-vhost-ipipet.teamerlich.org.conf
    app.run(host='0.0.0.0',port=5106)