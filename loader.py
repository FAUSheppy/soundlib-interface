#!/usr/bin/python3
import argparse

import os
import sys
import datetime
import boto3

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
    source = Column(String)

def fileToFileobject(path, source=""):

    basename = os.path.basename(path)
    return File(path=path, tags=basename, source=source)

def list_objects(client, bucket_name, prefix=''):

    paginator = client.get_paginator('list_objects_v2')
    response_iterator = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

    for response in response_iterator:
        for content in response.get('Contents', []):
            yield content['Key']

def list_all_files_s3(bucket_name):

    s3_client = boto3.client('s3', endpoint_url=os.environ["S3_ENDPOINT"])
    for file_key in list_objects(s3_client, bucket_name):
        yield file_key

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Create soundlib db')
    parser.add_argument('--db', default="sqlite:///database.sqlite",
                                    help='DB String to feed to sqlalchemy create engine')
    parser.add_argument('--path', help='Path to read recursively')
    parser.add_argument('--s3-bucket', help='Use S3 backend with params from env')
    args = parser.parse_args()

    # database #
    engine = sqlalchemy.create_engine(args.db)
    base.metadata.create_all(engine)
    session = Session(engine)

    # load filename list from backend #
    if args.path:
        filenames = glob.iglob(args.path + '**/**', recursive=True)
        source = "file://{}".format(args.path)
    elif args.s3_bucket:
        filenames = list_all_files_s3(args.s3_bucket)
        source = "s3://{}".format(args.s3_bucket)
    else:
        print("Either --s3-bucket must be enabled or --path must be set", file=sys.stderr)
        sys.exit(1)

    # iterate filenames #
    for filename in filenames:

        if not filename.endswith(".wav"):
            continue

        f = fileToFileobject(filename, source)
        session.merge(f)
    
    session.commit()
