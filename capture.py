#!/usr/local/bin/python2.7

import numpy as np
import cv2
import boto3
import os
from sys import argv
from botocore.exceptions import BotoCoreError, ClientError
import json
import pyaudio
import inflect
from time import sleep

region = 'eu-west-1'  # change this to switch to another AWS region
colors = [
    ['green', 0, 255, 0],
    ['blue', 255, 0, 0],
    ['red', 0, 0, 255],
    ['purple', 255, 0, 255],
    ['silver', 192, 192, 192]
]


polly = boto3.client("polly", region_name=region)
reko = boto3.client('rekognition', region_name=region)
p = inflect.engine()
pya = pyaudio.PyAudio()


# Take a photo with USB webcam
# Set save to True if you want
# to save the image (in the current working directory)
# and open Preview to see the image
def take_photo(save=False):
    speak("Please point your external webcam at the subject")
    sleep(5)
    speak("Taking a photo")
    vidcap = cv2.VideoCapture()
    vidcap.open(0)
    retval, image = vidcap.retrieve()
    vidcap.release()
    small = cv2.resize(image, (0, 0), fx=0.75, fy=0.75)
    if save:
        cv2.imwrite('image.png', small)
        os.system('open -a Preview image.png')
    retval, encoded_image = cv2.imencode('.png', small)
    encoded_image_bytes = encoded_image.tobytes()
    return encoded_image_bytes


# Read image from file
def read_image(filename):
    with open(filename, 'r') as f:
        encoded_image_bytes = f.read()
        return encoded_image_bytes


# Provide a string and an optional voice attribute
# and play the streamed audio response
# Defaults to the Salli voice
def speak(text_string, voice="Joanna"):
    try:
        # Request speech synthesis
        response = polly.synthesize_speech(
            Text=text_string,
            TextType="text",
            OutputFormat="pcm",
            VoiceId=voice
        )
    except (BotoCoreError, ClientError) as error:
        # The service returned an error, exit gracefully
        print(error)
        exit(-1)
    # Access the audio stream from the response
    if "AudioStream" in response:
        stream = pya.open(
            format=pya.get_format_from_width(width=2),
            channels=1,
            rate=16000,
            output=True
        )
        stream.write(response['AudioStream'].read())
        sleep(1)
        stream.stop_stream()
        stream.close()
    else:
        # The response didn't contain audio data, return False
        print("Could not stream audio")
        return(False)


# Amazon Rekognition label detection
def reko_detect_labels(image_bytes):
    print("Calling Amazon Rekognition: detect_labels")
#   speak("Detecting labels with Amazon Recognition")
    response = reko.detect_labels(
        Image={
            'Bytes': image_bytes
        },
        MaxLabels=8,
        MinConfidence=60
    )
    return response


# rekognition facial detection
def reko_detect_faces(image_bytes):
    print("Calling Amazon Rekognition: detect_faces")
    response = reko.detect_faces(
        Image={
            'Bytes': image_bytes
        },
        Attributes=['ALL']
    )
    print(
        json.dumps(
            response,
            sort_keys=True,
            indent=4
        )
    )
    return response


# create verbal response describing the detected
# lables in the response from Rekognition
# there needs to be more than one lable right now,
# otherwise you'll get a leading 'and'
def create_verbal_response_labels(reko_response):
    verbal_response = "I detected the following labels: "
    humans = False
    len_labels = len(reko_response['Labels'])
    if len_labels == 0:
        verbal_response = "I cannot detect anything."
    else:
        i = 0
        for label in reko_response['Labels']:
            i += 1
            if label['Name'] == 'People':
                humans = True
                continue
            print "%s\t(%.2f)" % (label['Name'], label['Confidence'])
            if i < len_labels:
                newstring = "%s, " % (label['Name'].lower())
                verbal_response = verbal_response + newstring
            else:
                newstring = "and %s. " % (label['Name'].lower())
                verbal_response = verbal_response + newstring
            if ('Human' in label.values()) or ('Person' in label.values()):
                humans = True
    return humans, verbal_response


def create_verbal_response_face(reko_response):
    verbal_response = ""

    persons = len(reko_response['FaceDetails'])
    if persons == 1:
        verbal_response = "I can see one person. "
    else:
        verbal_response = "I can see {0} people. ".format(persons)
    i = 0
    for face_detail in reko_response['FaceDetails']:
        # Boolean True|False values for these facial features
        beard = face_detail['Beard']['Value']
        eyeglasses = face_detail['Eyeglasses']['Value']
        sunglasses = face_detail['Sunglasses']['Value']
        mustache = face_detail['Mustache']['Value']
        smile = face_detail['Smile']['Value']
        if persons == 1:
            verbal_response = verbal_response + "The person is {0}. ".format(
                face_detail['Gender']['Value'].lower()
            )
        else:
            verbal_response = verbal_response + "The {0} person is {1}. ".format(
                p.number_to_words(p.ordinal(str([i + 1]))),
                face_detail['Gender']['Value'].lower()
            )
        if face_detail['Gender']['Value'] == 'Male':
            he_she = 'he'
        else:
            he_she = 'she'
        print "Person %d (%s):" % (i+1, colors[i][0])
        print "\tGender: %s\t(%.2f)" % (
            face_detail['Gender']['Value'],
            face_detail['Gender']['Confidence']
        )
        print "\tEyeglasses: %s\t(%.2f)" % (
            eyeglasses,
            face_detail['Eyeglasses']['Confidence']
        )
        print "\tSunglasses: %s\t(%.2f)" % (
            sunglasses,
            face_detail['Sunglasses']['Confidence']
        )
        print "\tSmile: %s\t(%.2f)" % (smile, face_detail['Smile']['Confidence'])
        if eyeglasses is True and sunglasses is True:
            verbal_response = verbal_response + "%s is wearing glasses. " % (
                he_she.capitalize(),
            )
        elif eyeglasses is True and sunglasses is False:
            verbal_response = verbal_response + "%s is wearing spectacles. " % (
                he_she.capitalize(),
            )
        elif eyeglasses is False and sunglasses is True:
            verbal_response = verbal_response + "%s is wearing sunglasses. " % (
                he_she.capitalize(),
            )
        if smile:
            true_false = 'is'
        else:
            true_false = 'is not'
        verbal_response = verbal_response + "%s %s smiling. " % (
            he_she.capitalize(),
            true_false
        )
        print "\tEmotions:"
        j = 0
        for emotion in face_detail['Emotions']:
            if j == 0:
                verbal_response = verbal_response + "%s looks %s. " % (
                    he_she.capitalize(),
                    emotion['Type'].lower()
                )
            print "\t\t%s\t(%.2f)" % (emotion['Type'], emotion['Confidence'])
            j += 1
        # Find bounding box for this face
        height = face_detail['BoundingBox']['Height']
        left = face_detail['BoundingBox']['Left']
        top = face_detail['BoundingBox']['Top']
        width = face_detail['BoundingBox']['Width']
        i += 1

    return verbal_response


def save_image_with_bounding_boxes(encoded_image, reko_response):
    encoded_image = np.fromstring(
        encoded_image,
        np.uint8
    )
    image = cv2.imdecode(
        encoded_image,
        cv2.IMREAD_COLOR
    )
    image_height, image_width = image.shape[:2]
    i = 0
    for mydict in reko_response['FaceDetails']:
        # Find bounding box for this face
        height = mydict['BoundingBox']['Height']
        left = mydict['BoundingBox']['Left']
        top = mydict['BoundingBox']['Top']
        width = mydict['BoundingBox']['Width']
        # draw this bounding box
        image = draw_bounding_box(
            image,
            image_width,
            image_height,
            width,
            height,
            top,
            left,
            colors[i]
        )
        i += 1
    # write the image to a file
    cv2.imwrite('face_bounding_boxes.jpg', image)
    os.system('open -a Preview face_bounding_boxes.jpg')


# draw bounding boxe around one face
def draw_bounding_box(
    cv_img, cv_img_width, cv_img_height,
    width, height, top, left, color
):
    # calculate bounding box coordinates top-left - x,y, bottom-right - x,y
    width_pixels = int(width * cv_img_width)
    height_pixels = int(height * cv_img_height)
    left_pixel = int(left * cv_img_width)
    top_pixel = int(top * cv_img_height)
    cv2.rectangle(
        cv_img, (
            left_pixel,
            top_pixel
            ),
        (
            left_pixel + width_pixels,
            top_pixel + height_pixels
        ),
        (
            color[1],
            color[2],
            color[3]
        ),
        2
    )
    return cv_img


## START MAIN

# if no arguments take a photo
# if one argument open the image file and decode it
# if more than on argument exit gracefully and print usage guidance
if len(argv) == 1:
    encoded_image = take_photo(save=True)
elif len(argv) == 2:
    print "opening image in file: ", argv[1]
    encoded_image = read_image(argv[1])
else:
    print "Use with no arguments to take a photo with the camera, or one argument to use a saved image"
    exit(-1)

labels = reko_detect_labels(encoded_image)
humans, labels_response_string = create_verbal_response_labels(labels)
print labels_response_string
speak(labels_response_string)

if humans:
    print "Detected Human: ", humans, "\n"
    reko_response = reko_detect_faces(encoded_image)
    faces_response_string = create_verbal_response_face(reko_response)
    save_image_with_bounding_boxes(encoded_image, reko_response)
    print faces_response_string
    sleep(1)
    speak(faces_response_string)
else:
    print "No humans detected. Skipping facial recognition"
