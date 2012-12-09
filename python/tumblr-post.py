#!/usr/bin/python

# Build a series of posts drawing from the Parse API, then post to Tumblr as
# drafts; run as a chron job
import ParsePy
from PIL import Image
import os
import datetime
import random
import requests
from StringIO import StringIO
import boto
from boto.s3.key import Key
import re
from subprocess import call
import sys

# Major global variables
PARSE_APP_ID = "***"
PARSE_MASTER_ID = "***"
TEMP_DIR = "tempDir/"
IMAGE_SIZE = (480, 350)
AMAZON_ACCESS_KEY = "***"
AMAZON_SECRET_KEY = "***"
BUCKET_NAME = "juxtapoesie"
QUALITY = 90

# Connect to Amazon S3
S3 = boto.connect_s3(AMAZON_ACCESS_KEY, AMAZON_SECRET_KEY)
BUCKET = S3.get_bucket(BUCKET_NAME)
k = Key(BUCKET)

# Grab the Parse records from the last hour
ParsePy.APPLICATION_ID = PARSE_APP_ID
ParsePy.MASTER_KEY = PARSE_MASTER_ID

timeNow = datetime.datetime.utcnow()
time1hr = timeNow - datetime.timedelta(0, 60*60*1)
time1hrISO = time1hr.strftime("%Y-%m-%dT%H:%M:%S.%f")[0:-3] + 'Z'
time1hrISO = {"__type": "Date", "iso": time1hrISO}

query = ParsePy.ParseQuery("Juxta")
query = query.gt("updatedAt", time1hrISO)
Juxtas = query.fetch()

# Create a top-level temporary folder for the job
TEMP_DIR_PATH = os.path.join(os.getcwd(), TEMP_DIR)
os.chdir(TEMP_DIR_PATH)
randTopDir = ''.join(str(random.randint(0, 9)) for _ in range(20))
os.mkdir(randTopDir)
os.chdir(os.path.join(os.getcwd(), randTopDir))

# Iterate through the images to be juxtaposed
for j in Juxtas:
    # Change to a new subdirectory
    randSubDir = ''.join(str(random.randint(0, 9)) for _ in range(20))
    os.mkdir(randSubDir)
    os.chdir(randSubDir)

    # Download the images
    r1 = requests.get(j.url1)
    i1 = Image.open(StringIO(r1.content))
    r2 = requests.get(j.url2)
    i2 = Image.open(StringIO(r2.content))

    # Crop the images
    cropW = j.crop1['cropW']
    cropH = j.crop1['cropH']
    cropX1 = j.crop1['cropX']
    cropY1 = j.crop1['cropY']
    cropX2 = cropX1 + cropW
    cropY2 = cropY1 + cropH
    cropBox = (cropX1, cropY1, cropX2, cropY2)
    region1 = i1.crop(cropBox)

    cropW = j.crop2['cropW']
    cropH = j.crop2['cropH']
    cropX1 = j.crop2['cropX']
    cropY1 = j.crop2['cropY']
    cropX2 = cropX1 + cropW
    cropY2 = cropY1 + cropH
    cropBox = (cropX1, cropY1, cropX2, cropY2)
    region2 = i2.crop(cropBox)

    # Resize as necessary
    region1 = region1.resize(IMAGE_SIZE)
    region2 = region2.resize(IMAGE_SIZE)

    # Export images
    outfile1 = ('crop_' + str(random.randint(1000, 9999)) + '_' +
                os.path.split(j.url1)[1])
    outfile2 = ('crop_' + str(random.randint(1000, 9999)) + '_' +
                os.path.split(j.url2)[1])

    if i1.format == "PNG":
        QUALITYUSE = 75
    else:
        QUALITYUSE = QUALITY

    region1.save(outfile1, i1.format, quality=QUALITY)
    region2.save(outfile2, i2.format, quality=QUALITY)

    # Upload images to S3, get new URL (hold old url for post)
    k.key = outfile1
    k.set_contents_from_filename(outfile1)
    k.make_public()
    k.key = outfile2
    k.set_contents_from_filename(outfile2)
    k.make_public()

    # Get S3 urls
    url1az = "http://s3.amazonaws.com/" + BUCKET_NAME + "/" + outfile1
    url2az = "http://s3.amazonaws.com/" + BUCKET_NAME + "/" + outfile2

    # Build a post and post
    yamlBegin =  "---" + "\n" + "type: text" + "\n"
    title = "title: " + j.title + "\n"
    body1 = "body: "
    body2 = ("<div class=\"juxta\">" +
            "<div class=\"left-image\">" +
            "<a target=\"_blank\" href=\"" + j.url1 + "\">" +
            "<img src=\"" + url1az + "\" width=" + str(IMAGE_SIZE[0]) +
            " />" + "</a>" + "</div>" +
            "<div class=\"right-image\">" +
            "<a target=\"_blank\" href=\"" + j.url2 + "\">" +
            "<img src=\"" + url2az + "\" width=" + str(IMAGE_SIZE[0]) +
            " />" + "</a>" + "</div>" +
            "<p class=\"top-info\">" + "Left: " + j.leftcredit + " / " +
                    " Right: " + j.rightcredit + " / " +
                    " Posted by: " + j.postcredit + "</p>" +
            "<p class=\"left-caption\">" + j.subleft + "</p>" +
            "<p class=\"right-caption\">" + j.subright + "</p>" +
            "</div>")
    body = body1 + "| " + body2 + "\n"
    yamlEnd = "state: draft" + "\n" + "---"
    yamlWhole = yamlBegin + title + body + yamlEnd
    yamlWholeU = yamlWhole.encode('UTF-8')

    # Write the post to a YAML file
    with open("post.yaml", "w") as text_file:
        text_file.write(yamlWholeU)

    # Push the post
    try:
        retcode = call("/usr/local/bin/tumblr post post.yaml --host=\"juxtapoet.tumblr.com\"", shell=True)
        if retcode != 0:
            print >>sys.stderr, "Error", -retcode
    except OSError as e:
        print >>sys.stderr, "Execution failed:", e

    # Remove the files
    os.remove(outfile1)
    os.remove(outfile2)
    os.remove("post.yaml")

    # Change back to the top-level directory
    os.chdir(os.path.join(TEMP_DIR_PATH, randTopDir))

    # Remove the temporary directory
    os.rmdir(randSubDir)


os.chdir(TEMP_DIR_PATH)
os.rmdir(randTopDir)

