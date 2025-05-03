#!/usr/bin/env python3

"""
Updated for Python 3 to maintain compatibility with Flask 2+, updated deprecated syntax, and improved security and maintainability.

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
from werkzeug.utils import secure_filename
from lockfile import LockFile
import string
import datetime
import random
import json
import re
import sys
import os
import csv
from subprocess import Popen, PIPE

app = Flask(__name__)
app.debug = True

# Flask File uploads:
# http://flask.pocoo.org/docs/patterns/fileuploads/
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

community_public_file = os.path.join(UPLOAD_FOLDER, "community.json")

# Default shared designs that are always available for testing/demo
default_shared_designs = [
    {"description": "96-Wells, Single-Channel Demo", "id": "demolnk1", "plate_type": 96, "pipet_type": "single"},
    {"description": "96-Wells, 8-Channel Demo", "id": "demolnk8", "plate_type": 96, "pipet_type": "multi8"},
    {"description": "384-Wells, Single-Channel Demo", "id": "384demo1", "plate_type": 384, "pipet_type": "single"}
]

def opencsv(filename):
    with open(filename, newline='') as f:
        dialect = csv.Sniffer().sniff(f.read(1024))
        f.seek(0)
        rows = list(csv.reader(f, dialect))
    return rows


def get_random_id(size=8, chars=string.ascii_letters + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


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
    return m is not None
    EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
    return EMAIL_REGEX.match(email) is not None


def valid_id(id_):
    """
    Given an ID string, returns TRUE if the ID is valid (only letters/digits)
    """
    return bool(re.fullmatch(r"[A-Za-z0-9]+", id_))

def files_from_id_unsafe(id_):
    """
    Given an ID string, returns a tuple of JSON-File-path, CSV-File-Path.

    The full-path is based on the UPLOAD_FOLDER setting.

    Raises an exception if the ID is invalid.
    Unsafe: because the returned filenames don't necessarily exist.

    Example:
      json_file, csv_file = files_from_id_unsafe('xT44MJHe')
    """
    if not valid_id(id_):
        raise ValueError(f"Invalid ID '{id_}'")
    base = os.path.join(UPLOAD_FOLDER, id_)
    return f"{base}.json", f"{base}.csv"

def files_from_id(id_):
    """
    Given an ID string, returns a tuple of JSON-File-path, CSV-File-Path.

    The full-path is based on the UPLOAD_FOLDER setting.

    Raises an exception if the ID is invalid, OR if the files don't exist.

    Example:
      json_file, csv_file = files_from_id('xT44MJHe')
    """
    json_path, csv_path = files_from_id_unsafe(id_)
    if not os.path.exists(csv_path) or not os.path.exists(json_path):
        raise FileNotFoundError(f"Missing files for ID '{id_}'")
    return json_path, csv_path

def well96_num_to_name(well):
    well = int(well)
    if not (1 <= well <= 96):
        raise ValueError(f"Invalid well number: {well}")
    row = chr(ord('A') + (well - 1) % 8)
    col = (well - 1) // 8 + 1
    return f"{row}{col:02}"

def well384_num_to_name(well):
    well = int(well)
    if not (1 <= well <= 384):
        raise ValueError(f"Invalid well number: {well}")
    row = chr(ord('A') + (well - 1) % 16)
    col = (well - 1) // 16 + 1
    return f"{row}{col:02}"

def add_shared_community_design(description, id_, plate_type, pipet_type):
    try:
        if not valid_id(id_) or not description:
            return
        lock = LockFile(community_public_file)
        with lock:
            data = []
            if os.path.exists(community_public_file):
                with open(community_public_file, "r") as f:
                    data = json.load(f)
            data.append({"description": description, "id": id_, "plate_type": plate_type, "pipet_type": pipet_type})
            with open(community_public_file, "w") as f:
                json.dump(data, f)
    except Exception as e:
        # silently ignore any errors - the new plate will simply not be added to the list
        sys.stderr.write(f"Failed to add shared community (id = '{id_}', exception='{e}')\n")

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

    well_map = well96_num_to_name if plate_type == 96 else well384_num_to_name
    try:
        data = []
        rdr = opencsv(filename)
        for row_num, row in enumerate(rdr):
            if row_num == 0:
                continue
            row = [x.strip() for x in row]
            if len(row) < 4:
                raise ValueError("Expecting at least 4 fields")
            entry = [row_num, row[0], int(row[1]), well_map(row[1]), row[2], int(row[3]), well_map(row[3])]
            if len(row) >= 5:
                entry.append(float(row[4]))
            if len(row) >= 6:
                entry.append(row[5])
            data.append(entry)
        return data
    except Exception as e:
        raise Exception(f"Error loading CSV file: {e}")

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

@app.route("/create", methods=["POST"])
def create():
    email = request.form.get("email", "").strip()
    if email and not valid_email(email):
        return f"Error: invalid email address '{email}'", 400

    description = request.form.get("description", "").strip()
    if not description:
        return "Error: missing 'description' parameter", 400

    file = request.files.get("csv_file")
    if not file:
        return "Error: no CSV file uploaded", 400

    pipet_type = request.form.get("pipet_type", "").strip()
    if pipet_type not in ["single", "multi8"]:
        return f"Error: invalid pipet type {pipet_type}", 400

    plate_type = request.form.get("plate_type", "").strip()
    if plate_type not in ["96", "384"]:
        return f"Error: invalid plate type {plate_type}", 400
    plate_type = int(plate_type)

    share_design = request.form.get("share_design", "") == "yes"

    if pipet_type == "multi8" and plate_type == 384:
        return "Error: multi-channel pipetting is not currently supported for 384 well plates", 400

    if share_design and not description:
        return "Error: when sharing a design, Description must not be empty", 400

    id_ = get_random_id()
    json_path, csv_path = files_from_id_unsafe(id_)
    file.save(csv_path)

    reader = opencsv(csv_path)
    numsteps, srcplates, destplates = 0, [], []
    for row in reader:
        numsteps += 1
        if numsteps == 1:
            continue
        srcplates.append(row[0])
        destplates.append(row[2])
    info = {
        "email": email,
        "description": description,
        "id": id_,
        "useragent": str(request.user_agent),
        "remote_addr": request.remote_addr,
        "time": str(datetime.datetime.now()),
        "numsteps": numsteps,
        "srcplates": list(set(srcplates)),
        "destplates": list(set(destplates)),
        "pipet_type": pipet_type,
        "plate_type": plate_type,
        "share_design": share_design,
    }
    with open(json_path, 'w') as f:
        json.dump(info, f)

    link = url_for('show', id=id_)
    if email:
        sendemail(email, description, link)
    if share_design:
        add_shared_community_design(description, id_, plate_type, pipet_type)
    return redirect(link)

def sendemail(email, description, link):
    args = ['mailx', '-s', 'ipipet file', '-r', 'ipipet admin <dina@wi.mit.edu>', '-b', 'dina@wi.mit.edu', email]
    msg = f"""
    Here's your link to start pipetting for your {description} project.

    Open this email on your tablet and click the link
    """
    p = Popen(args, stdin=PIPE)
    p.communicate(input=msg.encode('utf-8'))

@app.route("/show/<id>")
def show(id):
    json_path, _ = files_from_id(id)
    with open(json_path) as f:
        info = json.load(f)
    return render_template("show.html", info=info)

@app.route("/run/<id>")
def run(id):
    dpi = int(request.args.get("dpi", 96))
    well_color = request.args.get("well_color", "red")
    handedness = request.args.get("handedness", "right")

    json_path, _ = files_from_id(id)
    with open(json_path) as f:
        info = json.load(f)

    data_url = url_for("data", id=id)
    return render_template("run.html", data_url=data_url, id=id, dpi=dpi, info=info, well_color=well_color, handedness=handedness)

@app.route("/data/<id>")
def data(id):
    json_path, csv_path = files_from_id(id)
    with open(json_path) as f:
        info = json.load(f)
    data = load_plating_csv(info["plate_type"], csv_path)
    return jsonify(data=data)

@app.route("/csvdownload/<id>")
def csvdownload(id):
    _, csv_path = files_from_id(id)
    with open(csv_path) as f:
        csv_data = f.read()
    response = make_response(csv_data)
    response.headers["Content-Disposition"] = f"attachment; filename={id}.csv"
    response.headers["Content-Type"] = "text/csv"
    return response

@app.route("/community")
def community():
    data = default_shared_designs.copy()
    try:
        if os.path.exists(community_public_file):
            with open(community_public_file) as f:
                data.extend(json.load(f))
    except:
        pass
    return render_template("community.html", data=data)


if __name__ == "__main__":
    # Heroku uses gunicorn as HTTP server
    port = int(os.getenv("PORT", 5000))
    app.run(debug=True, port=port)
