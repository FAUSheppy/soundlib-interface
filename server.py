#!/usr/bin/python3

import flask                                                                                        
import subprocess
import json
import argparse
import os
import datetime
import os.path
import werkzeug.utils
import datetime
import sys

from sqlalchemy import Column, Integer, String, Boolean, or_, and_
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func, text
import sqlalchemy
from flask_sqlalchemy import SQLAlchemy

app = flask.Flask("Soundlib Interface", static_folder=None)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.sqlite'
#app.config['SECRET_KEY'] = "secret"
db = SQLAlchemy(app)

@app.route("/") 
def root():
    header = ["File", "Play", "Download"]
    render = flask.render_template("index.html", headerCol=header)
    response = flask.Response(render, 200)
    response.headers.add('Access-Control-Allow-Headers', '*')
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response

@app.route("/data-source", methods=["POST"])
def source():
    dt = DataTable(flask.request.form.to_dict(), ["path", "tags"])
    jsonDict = dt.get()
    return flask.Response(json.dumps(jsonDict), 200, mimetype='application/json')

@app.route('/static/<path:path>')
def static(path):
    response = flask.send_from_directory('static', path)
    #response.headers['Cache-Control'] = "max-age=2592000"
    return response

@app.route('/tmp/<path:path>')
def small(path):

    # verify valid path #
    dbpath = "./" + path.replace("static/","")
    result = db.session.query(File.path).filter(File.path == dbpath).first()
    if result:

        tmpfile = path.replace("/", "--") + ".mp3"
        tmpfileFP = "tmp/" + tmpfile

        if not os.path.isfile(tmpfileFP):
            subprocess.run(["./small.sh", path, tmpfileFP])

        response = flask.send_from_directory('tmp', tmpfile)
        return response
    else:
        return ("BAD PATH", 505)

@app.before_first_request
def init():
    app.config["DB"] = db
    #db.create_all() <- dont do this database must be created by loader

class File(db.Model):
    __tablename__ = "files"
    path = Column(String, primary_key=True)
    tags = Column(String)

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
            singleRow.append(flask.Markup(path))
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
    app.run(host=args.interface, port=args.port)
