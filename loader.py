#!/usr/bin/python3
import argparse

import os
import sys
import datetime

from sqlalchemy import Column, Integer, String, Boolean, or_, and_, Table, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import func
import sqlalchemy
import glob

base   = declarative_base()

class File(base):
    __tablename__ = "files"
    
    path = Column(String, primary_key=True)
    tags = Column(String)

def fileToFileobject(path):

    basename = os.path.basename(path)
    return File(path=path, tags=basename)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Create soundlib db')
    parser.add_argument('--db', default="sqlite:///database.sqlite",
                                    help='DB String to feed to sqlalchemy create engine')
    parser.add_argument('--path', required=True, help='Path to read recursively')
    args = parser.parse_args()

    engine = sqlalchemy.create_engine(args.db)
    base.metadata.create_all(engine)

    
    session = Session(engine)
    for filename in glob.iglob(args.path + '**/**', recursive=True):
        if not filename.endswith(".wav"):
            continue
        f = fileToFileobject(filename)
        session.merge(f)
        print(filename)
    
    session.commit()
