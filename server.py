#!/usr/bin/python3

import flask                                                                                        
import io
import subprocess
import json
import argparse
import os
import datetime
import os.path
import werkzeug.utils
import datetime
import sys
import secrets

from sqlalchemy import Column, Integer, String, Boolean, or_, and_
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func, text
import sqlalchemy
from flask_sqlalchemy import SQLAlchemy
import markupsafe
import pathlib

import boto3
import humanize

import loader

app = flask.Flask("Soundlib Interface", static_folder=None)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.sqlite"
db = SQLAlchemy(app)

@app.route("/") 
def root():
    '''Display Index site'''

    cache_size = sum(p.stat().st_size for p in pathlib.Path("tmp").rglob('*'))
    cache_size_str = humanize.naturalsize(cache_size)

    header = ["File", "Play", "Download"]
    render = flask.render_template("index.html", header_col=header, cache_size_str=cache_size_str)
    response = flask.Response(render, 200)
    response.headers.add('Access-Control-Allow-Headers', '*')
    response.headers.add('Access-Control-Allow-Origin', '*')

    return response

@app.route("/data-source", methods=["POST"])
def data_source():
    dt = DataTable(flask.request.form.to_dict(), ["path", "tags"])
    jsonDict = dt.get()
    return flask.Response(json.dumps(jsonDict), 200, mimetype='application/json')

@app.route('/static/<path:path>')
def static(path):
    '''Return an unmodified file from S3 or FS'''

    dbpath = "./" + path.replace("static/","")

    # try it without ./ #
    result = db.session.query(File).filter(File.path==dbpath).first()

    # try witout #
    if not result:
        result = db.session.query(File).filter(File.path==dbpath[2:]).first()

    if not result:
        return ("NOT FOUND", 404)

    if result.source and result.source.startswith("s3://"):
        filebuffer = io.BytesIO()
        bucket_name = result.source.replace("s3://", "", 1)
        s3_client = boto3.client('s3', endpoint_url=os.environ["S3_ENDPOINT"])
        s3_client.download_fileobj(bucket_name, result.path, filebuffer)
        filebuffer.seek(0)
        return flask.send_file(filebuffer, as_attachment=True,
                    download_name=os.path.basename(result.path), mimetype="audio/wav")
    else:
        response = flask.send_from_directory('static', result.path)
        return response

@app.route('/tmp/<path:path>')
def small(path):
    '''Return a small version of the file for a short listen'''

    # verify valid path #
    dbpath = "./" + path.replace("static/","")

    # try it without ./ #
    result = db.session.query(File).filter(File.path==dbpath).first()

    # try witout #
    if not result:
        result = db.session.query(File).filter(File.path==dbpath[2:]).first()


    if result:

        tmpfile = path.replace("/", "--") + ".mp3"
        tmpfileFP = "tmp/" + tmpfile

        if not os.path.isfile(tmpfileFP):

            # download file from s3 #
            target_path_s3 = None
            if result.source.startswith("s3://"):

                bucket_name = result.source.replace("s3://", "", 1)

                # download path & name #
                if not os.path.isdir("./downloads/"):
                    os.mkdir("./downloads/")

                basename = os.path.basename(path)
                target_path_s3 = os.path.join("./downloads/", "{}--{}".format(
                                    secrets.token_urlsafe(20), basename))

                # download file #
                s3_client = boto3.client('s3', endpoint_url=os.environ["S3_ENDPOINT"])
                s3_client.download_file(bucket_name, result.path, target_path_s3)
                path = target_path_s3
           
            else:
                pass # fs nothing to do here

            # minimize file #
            subprocess.run(["./small.sh", path, tmpfileFP])

            # remove tmp file #
            if target_path_s3:
                os.remove(target_path_s3)

        response = flask.send_from_directory('tmp', tmpfile)
        return response
    else:
        return ("BAD PATH", 404)

def create_app():
    '''init app and execute loader'''

    dbpath = "sqlite:///instance/database.sqlite"
    if os.path.isfile(dbpath.replace("sqlite:///", "./", 1)):
        print("Loader not run - database already exists", file=sys.stderr)
        return
    else:
        loader.init(dbpath=dbpath, s3_bucket=os.environ.get("S3_BUCKET"), fs_path=os.environ.get("FS_PATH"))

class File(db.Model):

    __tablename__ = "files"

    path = Column(String, primary_key=True)
    tags = Column(String)
    source = Column(String)

    def toDict(self):
        return { "path" : self.path, "tags" : self.tags }

class DataTable():
    
    def __init__(self, d, cols):
        self.draw  = int(d["draw"])
        self.start = int(d["start"])
        self.length = int(d["length"])
        self.trueLength = -1
        self.searchValue = d["search[value]"]
        self.searchIsRegex = d["search[regex]"]
        self.cols = ["path", "tags"]
        self.orderByCol = int(d["order[0][column]"])
        self.orderDirection = d["order[0][dir]"]

        # order variable for use with pythong sorted etc #
        self.orderAsc = self.orderDirection == "asc"

        # oder variable for use with sqlalchemy
        if self.orderAsc:
            self.orderAscDbClass = sqlalchemy.asc
            self.orderAscDbClassReverse = sqlalchemy.desc
        else:
            self.orderAscDbClass = sqlalchemy.desc
            self.orderAscDbClassReverse = sqlalchemy.asc

    def __build(self, results, total, filtered):

        self.cacheResults = results
        
        count = 0
        resultDicts = [ r.toDict() for r in results ]

        # data list must have the correct order (same as table scheme) #
        rows = []
        for r in resultDicts:
            singleRow = []
            path = r["path"]
            tags = r["tags"]
            singleRow.append(os.path.basename(path))
            singleRow.append(markupsafe.Markup(path))
            singleRow.append(path)
            rows.append(singleRow)


        d = dict()
        d.update({ "draw" : self.draw })
        d.update({ "recordsTotal" : total })
        d.update({ "recordsFiltered" :  filtered })
        d.update({ "data" : rows })

        return d

    def get(self):

        filtered = 0
        total    = 0

        if self.searchValue:

            # base query
            query         = db.session.query(File)
            total         = query.count()

            # search string (search for all substrings individually #
            filterQuery = query
            for substr in self.searchValue.split(" "):
                searchSubstr = "%{}%".format(substr.strip())
                filterQuery  = filterQuery.filter(File.tags.like(searchSubstr))

            filtered    = filterQuery.count()
            results = filterQuery.offset(self.start).limit(self.length).all()

        else:

            query = db.session.query(File)
            query  = query.order_by(self.orderAscDbClassReverse(File.path))
            results  = query.offset(self.start).limit(self.length).all()
            total    = query.count()
            filtered = total

        return self.__build(results, total, filtered)

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Start SoundLib')
    parser.add_argument('--interface', default="localhost", help='Interface to run on')
    parser.add_argument('--port', default="5000", help='Port to run on')
    args = parser.parse_args()

    with app.app_context():
        create_app()

    app.run(host=args.interface, port=args.port, debug=True)
